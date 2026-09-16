"""Unit checks plus an opt-in real, isolated official-server round trip.

WORKLOAD_INTEGRATION=1 python -m unittest discover -s tests -p test_workload_service.py
"""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from workload_service import worker


class ServiceTests(unittest.TestCase):
    def test_configuration_requires_explicit_scope_and_valid_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for overrides in ({"decks": []}, {"apply": "false"},
                              {"minutes_per_day": 40, "max_minutes_per_day": 30},
                              {"new_cards_per_day": -1}):
                path.write_text(json.dumps({"decks": ["English"], **overrides}))
                with self.assertRaises(worker.WorkloadError):
                    worker.settings_from(path)

    def test_compose_settings_and_dashboard_escape(self):
        from workload_service.dashboard import render
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"WORKLOAD_CONFIG": json.dumps({
                "decks": ["English"], "run_at": "06:30", "apply": True})}):
                settings = worker.settings_from(Path(folder) / "missing.json")
                self.assertEqual(settings["run_at"], "06:30")
                self.assertTrue(settings["apply"])
        html = render([{"status": "error", "error": "<script>bad</script>",
                        "changes": [], "command": "run"}], "test-token", True)
        self.assertNotIn("<script>bad</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("disabled", html)
        self.assertIn('action="/run"', html)
        self.assertNotIn("setInterval", html)
        self.assertNotIn('http-equiv="refresh"', html)

    def test_dashboard_summary_and_collapsed_history(self):
        from workload_service.dashboard import render, display_time
        self.assertEqual(display_time("2026-09-16T05:56:44+02:00"), "16.09.2026 · 05:56:44")
        self.assertEqual(display_time(""), "")
        event = {"command": "run", "status": "error", "apply": True,
                 "error": "<script>bad</script>", "email": "suppressed_duplicate"}
        html = render([event, {"command": "download", "status": "success"}],
                      intervention={"error": "<script>bad</script>"})
        self.assertIn("Wymagana interwencja", html)
        self.assertNotIn("Ostatnia operacja udana", html)
        self.assertEqual(html.count('class="event" open'), 1)
        self.assertIn("pominięto powtórzony alert", html)
        self.assertNotIn("<script>", html)
        self.assertIn("Przebieg trwa…", render([event], running=True))
        self.assertIn("Zacznij od połączenia z Anki", render([]))

    def test_email_every_run_and_secret_not_rendered(self):
        from workload_service import notifications
        from workload_service.dashboard import render
        config = notifications.settings_from({"enabled": ["on"], "host": ["smtp.test"],
            "sender": ["a@example.test"], "recipient": ["b@example.test"],
            "password": ["smtp-secret"], "username": ["login"]}, {})
        self.assertEqual(notifications.settings_from({"host": ["smtp.test"]}, config)["password"], "smtp-secret")
        self.assertNotIn("smtp-secret", render([], mail=config))
        event = {"status": "success", "apply": True, "command": "run", "finished": "2026-09-13",
                 "changes": [{"deck": "English", "before": {"newLimit": 3}, "after": {"newLimit": 0}}]}
        with patch.object(notifications.smtplib, "SMTP") as smtp:
            client = smtp.return_value.__enter__.return_value
            client.send_message.return_value = {}
            for override in ({"command": "init"}, {"command": "login"}):
                self.assertEqual(notifications.send_summary(config, {**event, **override}), "not_needed")
            smtp.assert_not_called()
            self.assertEqual(notifications.send_summary(config, event), "sent")
            client.starttls.assert_called_once()
            client.login.assert_called_once_with("login", "smtp-secret")
            message = client.send_message.call_args.args[0]
            self.assertEqual(message.get_content_type(), "multipart/alternative")
            self.assertIn("<table", message.get_body(preferencelist=("html",)).get_content())
            self.assertIn("English", message.get_body(preferencelist=("plain",)).get_content())
            self.assertIn("bazowy: 0", message.get_body(preferencelist=("plain",)).get_content())
            self.assertNotIn("smtp-secret", message.as_string())
            for override in ({"status": "error", "error": "Sync failed"}, {"apply": False}, {"changes": []}):
                self.assertEqual(notifications.send_summary(config, {**event, **override}), "sent")
                body = client.send_message.call_args.args[0].get_body(preferencelist=("plain",)).get_content()
                self.assertNotIn("Zmiany zostały zsynchronizowane", body)
                if override.get("status") == "error":
                    self.assertIn("Sync failed", body)
                if override.get("changes") == []:
                    self.assertIn("Brak zmian limitów", body)
            self.assertEqual(notifications.send_summary({**config, "enabled": False}, event), "not_needed")

    def test_html_email_escapes_names_and_preserves_limit_details(self):
        from workload_service.notifications import summary_html
        event = {"status": "success", "apply": True, "command": "run",
                 "finished": "2026-09-14T05:00:21+02:00", "reason": "<script>bad</script>",
                 "changes": [{"deck": name, "before": {"newLimit": 0, "newLimitToday": {"limit": 7}},
                              "after": {"newLimit": 0, "newLimitToday": {"limit": 9}}}
                             for name in ("English", "English::<b>child</b>")]}
        html = summary_html(event)
        self.assertIn("↳ &lt;b&gt;child&lt;/b&gt;", html)
        self.assertNotIn("<script>", html)
        self.assertIn("14.09.2026 · 05:00", html)
        self.assertIn("Limit bazowy wszystkich", html)
        event["changes"][0]["after"] = {"newLimit": 5}
        html = summary_html(event)
        self.assertIn("Bazowy: 5", html)
        self.assertNotIn("Limit bazowy wszystkich", html)
        self.assertIn("brak<br>", html)
        for override in ({"status": "error"}, {"apply": False}):
            self.assertNotIn("Zmiany potwierdzone", summary_html({**event, **override}))

    def test_mail_failure_does_not_fail_successful_sync(self):
        from workload_service import notifications
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            with patch.object(worker, "_run"), patch.object(notifications, "send_summary", side_effect=RuntimeError("secret")):
                worker.run(data, {"apply": True}, "run")
            history = worker.read_json(data / "history.json")
            self.assertEqual(history[-1]["status"], "success")
            self.assertEqual(history[-1]["email"], "error: RuntimeError")
            self.assertNotIn("secret", (data / "history.json").read_text())

    def test_repeated_error_is_suppressed_until_success_or_different_error(self):
        from workload_service import notifications
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            with patch.object(worker, "_run") as operation, patch.object(notifications, "send_summary", return_value="sent") as mail:
                operation.side_effect = worker.WorkloadError("full sync")
                for _ in range(2):
                    with self.assertRaises(worker.WorkloadError):
                        worker.run(data, {}, "run")
                self.assertEqual(mail.call_count, 1)
                self.assertEqual(worker.read_json(data / "history.json")[-1]["email"], "suppressed_duplicate")
                operation.side_effect = worker.WorkloadError("network")
                with self.assertRaises(worker.WorkloadError):
                    worker.run(data, {}, "run")
                self.assertEqual(mail.call_count, 2)
                operation.side_effect = None
                worker.run(data, {}, "run")
                operation.side_effect = worker.WorkloadError("network")
                with self.assertRaises(worker.WorkloadError):
                    worker.run(data, {}, "run")
                self.assertEqual(mail.call_count, 4)

    def test_upgrade_uses_previous_delivered_error(self):
        from workload_service import notifications
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            worker.write_json(data / "history.json", [{"command": "run", "status": "error", "error": "full sync", "email": "sent"}])
            with patch.object(worker, "_run", side_effect=worker.WorkloadError("full sync")), patch.object(notifications, "send_summary") as mail:
                with self.assertRaises(worker.WorkloadError):
                    worker.run(data, {}, "run")
                mail.assert_not_called()

    def test_credentials_do_not_accept_a_url_with_embedded_password(self):
        with patch.dict(os.environ, {"ANKI_SYNC_URL": "https://user:secret@example.com/"}):
            with self.assertRaises(worker.WorkloadError):
                worker.credentials()

    def test_ankiweb_selection_and_redirect_boundary(self):
        with patch.dict(os.environ, {"ANKI_SYNC_URL": "ankiweb", "ANKI_SYNC_USERNAME": "test"}):
            self.assertEqual(worker.credentials(), (None, "test"))
        self.assertEqual(worker.checked_endpoint("https://sync2.ankiweb.net/", None),
                         "https://sync2.ankiweb.net/")
        for url in ("http://sync2.ankiweb.net/", "https://ankiweb.net.evil.test/",
                    "https://evil.test/", "https://user@sync2.ankiweb.net/"):
            with self.assertRaises(worker.WorkloadError):
                worker.checked_endpoint(url, None)


@unittest.skipUnless(os.environ.get("WORKLOAD_INTEGRATION") == "1", "set WORKLOAD_INTEGRATION=1 with anki installed")
class OfficialServerTests(unittest.TestCase):
    def setUp(self):
        from anki.collection import Collection
        self.Collection = Collection
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/"
        server_env = {**os.environ, "SYNC_USER1": "workload-test:local-test-password",
                      "SYNC_BASE": str(self.folder / "server"), "SYNC_HOST": "127.0.0.1",
                      "SYNC_PORT": str(port)}
        self.server = subprocess.Popen([sys.executable, "-m", "anki.syncserver"], env=server_env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_server)
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("isolated sync server did not start")
        password = self.folder / "password.txt"
        password.write_text("local-test-password\n")
        env = patch.dict(os.environ, {"ANKI_SYNC_URL": self.url, "ANKI_SYNC_USERNAME": "workload-test",
                                     "ANKI_SYNC_PASSWORD_FILE": str(password)})
        env.start()
        self.addCleanup(env.stop)
        self.client = Collection(str(self.folder / "client.anki2"))
        self.addCleanup(self.client.close)
        self.root = self.client.decks.id("English")
        self.child = self.client.decks.id("English::Words")
        self.other = self.client.decks.id("Unmanaged")
        for did in (self.root, self.child, self.other):
            for i in range(10):
                note = self.client.new_note(self.client.models.by_name("Basic"))
                note["Front"], note["Back"] = f"test-{did}-{i}", "answer"
                self.client.add_note(note, did)
        self.auth = self.client.sync_login("workload-test", "local-test-password", self.url)
        self.client.close_for_full_sync()
        self.client.full_upload_or_download(auth=self.auth, server_usn=None, upload=True)
        self.client.reopen(after_full_sync=True)
        self.data = self.folder / "worker"
        self.settings = {**worker.read_json(worker.ROOT / "anki_toolkit_workload/config.json"),
                         "decks": ["English"], "apply": True}

    def stop_server(self):
        self.server.terminate()
        self.server.wait(timeout=10)

    def test_download_dry_run_apply_retry_restore_and_expiry(self):
        original = {did: copy.deepcopy(self.client.decks.get(did))
                    for did in (self.root, self.child, self.other)}
        original_cards = self.client.db.all("select id, queue, due, ivl from cards order by id")
        worker.run(self.data, self.settings, "init")
        worker.run(self.data, {**self.settings, "apply": False}, "run")
        worker.sync_normal(self.client, self.auth)
        self.assertEqual(worker.limits(self.client.decks.get(self.root)), worker.limits(original[self.root]))
        worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        first = self.client.decks.get(self.root)
        self.assertEqual(first["newLimit"], 0)
        self.assertEqual(first["newLimitToday"]["limit"], 3)
        self.assertEqual(worker.limits(self.client.decks.get(self.other)), worker.limits(original[self.other]))
        self.assertEqual(self.client.db.all("select id, queue, due, ivl from cards order by id"), original_cards)
        worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        self.assertEqual(worker.limits(self.client.decks.get(self.root)), worker.limits(first))
        # Backend honours the combined parent/child quota and falls back to zero
        # when today's override expires. No review/FSRS/card changes are needed.
        self.client.decks.select(self.root)
        self.assertEqual(self.client.sched.counts()[0], 3)
        for did in (self.root, self.child):
            deck = self.client.decks.get(did)
            deck["newLimitToday"]["today"] = self.client.sched.today - 1 if self.client.sched.today else 999999
            self.client.decks.update_dict(deck)
        self.assertEqual(self.client.sched.counts()[0], 0)
        # Discard only these test-client edits before testing restoration.
        self.client.close_for_full_sync()
        self.client.full_upload_or_download(auth=self.auth, server_usn=None, upload=False)
        self.client.reopen(after_full_sync=True)
        worker.run(self.data, self.settings, "restore")
        worker.sync_normal(self.client, self.auth)
        for did in (self.root, self.child, self.other):
            self.assertEqual(worker.limits(self.client.decks.get(did)), worker.limits(original[did]))

    def test_full_download_preserves_state_and_rejects_foreign_limits(self):
        worker.run(self.data, self.settings, "init")
        worker.run(self.data, self.settings, "run")
        state = worker.read_json(self.data / "state.json")
        with patch.object(worker, "sync_normal", side_effect=worker.FullSyncRequired("full sync")):
            with self.assertRaises(worker.FullSyncRequired):
                worker.run(self.data, self.settings, "run")
        self.assertTrue((self.data / "intervention.json").exists())
        worker.run(self.data, self.settings, "download")
        self.assertFalse((self.data / "intervention.json").exists())
        self.assertEqual(worker.read_json(self.data / "state.json"), state)
        self.assertEqual(len(list(self.data.glob("before-download-*/collection.anki2"))), 1)
        worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        deck = self.client.decks.get(self.root)
        deck["newLimit"] = 7
        self.client.decks.update_dict(deck)
        worker.sync_normal(self.client, self.auth)
        before = (self.data / "collection.anki2").read_bytes()
        with self.assertRaises(worker.WorkloadError):
            worker.run(self.data, self.settings, "download")
        self.assertEqual((self.data / "collection.anki2").read_bytes(), before)
        self.assertTrue((self.data / "intervention.json").exists())

    def test_offline_answer_survives_remote_limit_changes(self):
        worker.run(self.data, self.settings, "init")
        worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        self.client.decks.select(self.root)
        card = self.client.sched.getCard()
        self.client.sched.answerCard(card, 3)
        history = self.client.db.all("select id, cid, ease, ivl, lastIvl, factor, time, type from revlog order by id")
        card_state = self.client.db.first("select type, queue, due, ivl from cards where id = ?", card.id)
        worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        self.assertEqual(self.client.db.all("select id, cid, ease, ivl, lastIvl, factor, time, type from revlog order by id"), history)
        self.assertEqual(self.client.db.first("select type, queue, due, ivl from cards where id = ?", card.id), card_state)
        # Cached hkey suffices after the bootstrap password is removed.
        with patch.dict(os.environ, {"ANKI_SYNC_PASSWORD_FILE": ""}):
            worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        self.assertEqual(self.client.db.all("select id, cid, ease, ivl, lastIvl, factor, time, type from revlog order by id"), history)

    def test_external_edit_is_not_overwritten(self):
        worker.run(self.data, self.settings, "init")
        worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        time.sleep(1.1)  # native deck conflict timestamps have second precision
        deck = self.client.decks.get(self.root)
        deck["newLimit"] = 7
        self.client.decks.update_dict(deck)
        worker.sync_normal(self.client, self.auth)
        with self.assertRaises(worker.WorkloadError):
            worker.run(self.data, self.settings, "run")

    def test_retry_after_failed_upload_does_not_send_stale_local_changes(self):
        worker.run(self.data, self.settings, "init")
        sync = worker.sync_normal
        calls = 0
        def fail_second(col, auth):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise worker.WorkloadError("simulated upload failure")
            return sync(col, auth)
        with patch.object(worker, "sync_normal", side_effect=fail_second):
            with self.assertRaises(worker.WorkloadError):
                worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        self.assertIsNone(self.client.decks.get(self.root)["newLimit"])
        worker.run(self.data, self.settings, "run")
        worker.sync_normal(self.client, self.auth)
        self.assertEqual(self.client.decks.get(self.root)["newLimitToday"]["limit"], 3)
