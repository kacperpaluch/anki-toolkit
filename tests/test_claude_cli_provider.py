"""Claude CLI provider — izolacja wiersza poleceń, status logowania, błędy.

Ładuje moduł po ścieżce ze szkieletem pakietu, jak pozostałe testy tutaj:
wtyczka importuje aqt/anki, których w CI nie ma.
"""

import importlib.util
import json
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

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
        ("atc.ai_generator.providers.claude_cli", "ai_generator/providers/claude_cli.py"),
    ]:
        spec = importlib.util.spec_from_file_location(name, ROOT / rel)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules["atc.ai_generator.providers.claude_cli"]


cl = _load()


def _provider(**options):
    return cl.ClaudeCLIProvider(
        api_key="", model=options.pop("model", "haiku"),
        temperature=0.2, max_retries=3, timeout=30,
        reasoning_effort=None, options=options,
    )


class BuildArgsTests(unittest.TestCase):
    """Izolacja nie jest opcjonalna — pola notatki to dane niezaufane."""

    def test_all_tools_are_disabled(self):
        args = _provider()._build_args("/bin/claude")
        # Pusty łańcuch po --tools = zero narzędzi: brak shella, plików, sieci.
        self.assertEqual(args[args.index("--tools") + 1], "")

    def test_external_sources_are_cut_off(self):
        args = _provider()._build_args("/bin/claude")
        for flag in ("--strict-mcp-config", "--disable-slash-commands",
                     "--no-session-persistence"):
            self.assertIn(flag, args)

    def test_never_bypasses_permissions_or_kills_oauth(self):
        args = _provider()._build_args("/bin/claude")
        self.assertNotIn("--dangerously-skip-permissions", args)
        self.assertNotIn("--allow-dangerously-skip-permissions", args)
        self.assertNotIn("--add-dir", args)
        # --bare wymusza ANTHROPIC_API_KEY i nigdy nie czyta OAuth/keychaina,
        # więc rozwaliłoby uwierzytelnienie subskrypcją.
        self.assertNotIn("--bare", args)

    def test_json_output_and_print_mode(self):
        args = _provider()._build_args("/bin/claude")
        self.assertIn("-p", args)
        self.assertEqual(args[args.index("--output-format") + 1], "json")

    def test_default_system_prompt_replaces_the_coding_preamble(self):
        args = _provider()._build_args("/bin/claude")
        self.assertEqual(args[args.index("--system-prompt") + 1],
                         cl.DEFAULT_SYSTEM_PROMPT)

    def test_custom_system_prompt_wins(self):
        args = _provider(system_prompt="Tylko IPA.")._build_args("/bin/claude")
        self.assertEqual(args[args.index("--system-prompt") + 1], "Tylko IPA.")

    def test_blank_system_prompt_falls_back_to_default(self):
        args = _provider(system_prompt="   ")._build_args("/bin/claude")
        self.assertEqual(args[args.index("--system-prompt") + 1],
                         cl.DEFAULT_SYSTEM_PROMPT)


class CleanEnvTests(unittest.TestCase):
    def test_env_is_minimal(self):
        env = cl._clean_env()
        self.assertIn("HOME", env)  # bez niego nie ma dostępu do poświadczeń
        # Klucz API wymusiłby rozliczenie przez płatne API zamiast subskrypcji.
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_inherited_api_key_is_not_passed_through(self):
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-x"}):
            self.assertNotIn("ANTHROPIC_API_KEY", cl._clean_env())


class LoginStatusTests(unittest.TestCase):
    def _run(self, payload, returncode=0):
        proc = subprocess.CompletedProcess([], returncode,
                                           stdout=json.dumps(payload), stderr="")
        with mock.patch.object(cl, "find_binary", return_value="/bin/claude"), \
             mock.patch("subprocess.run", return_value=proc):
            return cl.login_status()

    def test_subscription_login_is_accepted(self):
        ok, detail = self._run({"loggedIn": True, "subscriptionType": "pro",
                                "email": "a@b.c", "authMethod": "claude.ai"})
        self.assertTrue(ok)
        self.assertIn("pro", detail)

    def test_logged_out_is_rejected(self):
        ok, detail = self._run({"loggedIn": False})
        self.assertFalse(ok)
        self.assertIn("claude auth login", detail)

    def test_api_key_login_is_rejected(self):
        # Do klucza API służy osobny dostawca `anthropic`.
        ok, _ = self._run({"loggedIn": True, "authMethod": "apiKey"})
        self.assertFalse(ok)

    def test_missing_binary_is_reported(self):
        with mock.patch.object(cl, "find_binary", return_value=None):
            ok, detail = cl.login_status()
        self.assertFalse(ok)
        self.assertIn("claude", detail)


class ResponseParsingTests(unittest.TestCase):
    def _run_once(self, stdout, stderr="", returncode=0):
        proc = subprocess.CompletedProcess([], returncode,
                                           stdout=stdout, stderr=stderr)
        with mock.patch("subprocess.run", return_value=proc):
            return _provider()._run_once("/bin/claude", "prompt", 120)

    def test_reads_the_result_field(self):
        text, err = self._run_once(json.dumps(
            {"is_error": False, "subtype": "success", "result": " apple "}))
        self.assertEqual(text, "apple")
        self.assertEqual(err, "")

    def test_cli_reported_error(self):
        text, err = self._run_once(json.dumps(
            {"is_error": True, "subtype": "error_max_turns",
             "result": "limit osiągnięty"}))
        self.assertIsNone(text)
        self.assertIn("limit osiągnięty", err)

    def test_empty_result(self):
        text, err = self._run_once(json.dumps(
            {"is_error": False, "subtype": "success", "result": ""}))
        self.assertIsNone(text)
        self.assertIn("pusta", err)

    def test_non_json_output_falls_back_to_stderr(self):
        text, err = self._run_once("", stderr="coś poszło nie tak", returncode=1)
        self.assertIsNone(text)
        self.assertIn("coś poszło nie tak", err)


class RetryClassificationTests(unittest.TestCase):
    def test_transient_errors_retry(self):
        self.assertTrue(cl._is_retryable("API Error 529 overloaded"))
        self.assertTrue(cl._is_retryable("request timed out"))

    def test_permanent_errors_do_not_retry(self):
        self.assertFalse(cl._is_retryable("invalid model name"))


class ProviderContractTests(unittest.TestCase):
    def test_local_provider_needs_no_api_key(self):
        self.assertFalse(cl.ClaudeCLIProvider.REQUIRES_API_KEY)

    def test_missing_binary_fails_without_running_anything(self):
        p = _provider(binary_path="/nie/ma/takiej/claude")
        self.assertIsNone(p.call_api("cokolwiek"))
        self.assertIn("claude", p.last_error)

    def test_model_aliases_do_not_go_stale(self):
        # CLI nie wystawia listy modeli; aliasy zawsze wskazują na najnowszą
        # wersję rodziny, więc nie trzeba ich aktualizować przy każdym wydaniu.
        self.assertIn("haiku", cl.fetch_models())
        self.assertIn("sonnet", cl.fetch_models())


if __name__ == "__main__":
    unittest.main()
