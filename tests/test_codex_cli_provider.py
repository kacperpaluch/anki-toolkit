"""Codex CLI provider — utwardzenie wiersza poleceń, status logowania, błędy.

Ładuje moduł po ścieżce ze szkieletem pakietu, jak pozostałe testy tutaj:
wtyczka importuje aqt/anki, których w CI nie ma.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent / "anki_toolkit_content"


def _load():
    pkg = types.ModuleType("atc"); pkg.__path__ = [str(ROOT)]
    sys.modules["atc"] = pkg
    common = types.ModuleType("atc.common"); common.__path__ = [str(ROOT / "common")]
    sys.modules["atc.common"] = common
    ag = types.ModuleType("atc.ai_generator"); ag.__path__ = [str(ROOT / "ai_generator")]
    sys.modules["atc.ai_generator"] = ag
    provs = types.ModuleType("atc.ai_generator.providers")
    provs.__path__ = [str(ROOT / "ai_generator" / "providers")]
    sys.modules["atc.ai_generator.providers"] = provs
    for name, rel in [
        ("atc.common.http", "common/http.py"),
        ("atc.ai_generator.providers.openai_compat", "ai_generator/providers/openai_compat.py"),
        ("atc.ai_generator.providers.base", "ai_generator/providers/base.py"),
        ("atc.ai_generator.providers.codex_cli", "ai_generator/providers/codex_cli.py"),
    ]:
        spec = importlib.util.spec_from_file_location(name, ROOT / rel)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules["atc.ai_generator.providers.codex_cli"]


cx = _load()


def _provider(**options):
    return cx.CodexCLIProvider(
        api_key="", model=options.pop("model", "gpt-5.4-mini"),
        temperature=0.2, max_retries=3, timeout=30,
        reasoning_effort=options.pop("reasoning_effort", None),
        options=options,
    )


class BuildArgsTests(unittest.TestCase):
    """Flagi utwardzenia nie są opcjonalne — pola notatki to dane niezaufane."""

    def test_hardening_flags_always_present(self):
        args = _provider()._build_args("/bin/codex", "/ws", "/out")
        for flag in ("--skip-git-repo-check", "--ephemeral",
                     "--ignore-user-config", "--ignore-rules"):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
        self.assertEqual(args[args.index("-C") + 1], "/ws")
        self.assertEqual(args[args.index("-o") + 1], "/out")

    def test_never_bypasses_the_sandbox(self):
        args = _provider()._build_args("/bin/codex", "/ws", "/out")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
        self.assertNotIn("--add-dir", args)
        self.assertNotIn("workspace-write", args)

    def test_prompt_goes_through_stdin(self):
        args = _provider()._build_args("/bin/codex", "/ws", "/out")
        self.assertEqual(args[-1], "-")

    def test_model_and_reasoning_effort(self):
        args = _provider(model="gpt-5.5", reasoning_effort="low")._build_args(
            "/bin/codex", "/ws", "/out")
        self.assertEqual(args[args.index("-m") + 1], "gpt-5.5")
        self.assertIn("model_reasoning_effort=low", args)

    def test_reasoning_effort_omitted_when_unset(self):
        args = _provider()._build_args("/bin/codex", "/ws", "/out")
        self.assertNotIn("-c", args)


class CleanEnvTests(unittest.TestCase):
    def test_env_is_minimal_and_pins_codex_home(self):
        env = cx._clean_env(Path("/home/u/.codex"))
        self.assertEqual(env["CODEX_HOME"], "/home/u/.codex")
        # Agent nie może zobaczyć pozostałych kluczy API z tej wtyczki.
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("ANTHROPIC_API_KEY", env)


class LoginStatusTests(unittest.TestCase):
    def _home_with(self, payload):
        tmp = tempfile.mkdtemp()
        (Path(tmp) / "auth.json").write_text(json.dumps(payload), encoding="utf-8")
        return Path(tmp)

    def test_chatgpt_login_is_accepted(self):
        ok, _ = cx.login_status(self._home_with({"auth_mode": "chatgpt"}))
        self.assertTrue(ok)

    def test_api_key_login_is_rejected(self):
        ok, detail = cx.login_status(self._home_with({"auth_mode": "apikey"}))
        self.assertFalse(ok)
        self.assertIn("apikey", detail)

    def test_missing_auth_file(self):
        ok, detail = cx.login_status(Path(tempfile.mkdtemp()))
        self.assertFalse(ok)
        self.assertIn("codex login", detail)

    def test_status_never_returns_the_token(self):
        home = self._home_with({"auth_mode": "chatgpt",
                                "tokens": {"access_token": "SECRET-TOKEN"}})
        _, detail = cx.login_status(home)
        self.assertNotIn("SECRET-TOKEN", detail)


class FailureMessageTests(unittest.TestCase):
    def _proc(self, stderr, code=1):
        return subprocess.CompletedProcess([], code, stdout="", stderr=stderr)

    def test_extracts_api_error_message(self):
        stderr = ('ERROR: {"type":"error","status":400,"error":'
                  '{"type":"invalid_request_error","message":"model not supported"}}')
        self.assertEqual(
            cx.CodexCLIProvider._describe_failure(self._proc(stderr)),
            "model not supported")

    def test_falls_back_to_stderr_tail(self):
        msg = cx.CodexCLIProvider._describe_failure(self._proc("coś poszło nie tak"))
        self.assertIn("coś poszło nie tak", msg)

    def test_reports_exit_code_when_stderr_empty(self):
        self.assertIn("2", cx.CodexCLIProvider._describe_failure(self._proc("", 2)))


class RetryClassificationTests(unittest.TestCase):
    def test_transient_errors_retry(self):
        self.assertTrue(cx._is_retryable("HTTP 503 Service Unavailable"))
        self.assertTrue(cx._is_retryable("request timed out"))

    def test_permanent_errors_do_not_retry(self):
        self.assertFalse(cx._is_retryable(
            "The 'gpt-5.1-codex-mini' model is not supported"))


class ProviderContractTests(unittest.TestCase):
    def test_local_provider_needs_no_api_key(self):
        self.assertFalse(cx.CodexCLIProvider.REQUIRES_API_KEY)

    def test_missing_binary_fails_without_running_anything(self):
        p = _provider(binary_path="/nie/ma/takiej/codex")
        self.assertIsNone(p.call_api("cokolwiek"))
        self.assertIn("codex", p.last_error)

    def test_timeout_floor_is_respected(self):
        # request_timeout 30 s jest liczony pod HTTP; rozumowanie trwa dłużej.
        self.assertGreaterEqual(cx.MIN_TIMEOUT, 120)


if __name__ == "__main__":
    unittest.main()
