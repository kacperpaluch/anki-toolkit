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
