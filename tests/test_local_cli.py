"""Wspólna warstwa dostawców lokalnych — wykrywanie binarki i środowisko.

Regresja, którą te testy pilnują: aplikacja GUI na macOS nie dziedziczy PATH-u
z powłoki, więc Anki uruchomione z Findera nie widziało `claude` ani `codex`
z Homebrew; a zbyt ciasne środowisko procesu potomnego blokowało odczyt
keychaina, przez co zalogowane CLI raportowało brak logowania.
"""

import importlib.util
import os
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent.parent / "anki_toolkit_content"


def _load():
    pkg = types.ModuleType("atc"); pkg.__path__ = [str(ROOT)]
    sys.modules["atc"] = pkg
    ag = types.ModuleType("atc.ai_generator"); ag.__path__ = [str(ROOT / "ai_generator")]
    sys.modules["atc.ai_generator"] = ag
    provs = types.ModuleType("atc.ai_generator.providers")
    provs.__path__ = [str(ROOT / "ai_generator" / "providers")]
    sys.modules["atc.ai_generator.providers"] = provs
    spec = importlib.util.spec_from_file_location(
        "atc.ai_generator.providers.local_cli",
        ROOT / "ai_generator/providers/local_cli.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lc = _load()

# PATH, jaki launchd daje aplikacji GUI na macOS — bez Homebrew.
FINDER_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _executable(directory: str, name: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


class SearchPathTests(unittest.TestCase):
    def test_homebrew_is_added_to_a_finder_style_path(self):
        with mock.patch.dict(os.environ, {"PATH": FINDER_PATH}):
            parts = lc.search_path().split(os.pathsep)
        self.assertIn("/opt/homebrew/bin", parts)
        self.assertIn("/usr/local/bin", parts)

    def test_existing_path_entries_come_first(self):
        with mock.patch.dict(os.environ, {"PATH": FINDER_PATH}):
            parts = lc.search_path().split(os.pathsep)
        self.assertEqual(parts[:4], FINDER_PATH.split(os.pathsep))

    def test_no_duplicates_when_already_present(self):
        with mock.patch.dict(os.environ, {"PATH": "/opt/homebrew/bin:/bin"}):
            parts = lc.search_path().split(os.pathsep)
        self.assertEqual(parts.count("/opt/homebrew/bin"), 1)


class FindExecutableTests(unittest.TestCase):
    def test_found_via_augmented_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = _executable(tmp, "somecli")
            with mock.patch.dict(os.environ, {"PATH": FINDER_PATH}), \
                 mock.patch.object(lc, "EXTRA_BIN_DIRS", (tmp,)):
                self.assertEqual(lc.find_executable("somecli"), target)

    def test_falls_back_to_extra_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = _executable(tmp, "bundled")
            with mock.patch.dict(os.environ, {"PATH": FINDER_PATH}):
                self.assertEqual(
                    lc.find_executable("niema", extra_candidates=(target,)),
                    target)

    def test_configured_path_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = _executable(tmp, "chosen")
            self.assertEqual(lc.find_executable("somecli", target), target)

    def test_bad_configured_path_is_not_silently_replaced(self):
        # Skoro użytkownik wskazał ścieżkę, cicha podmiana na inną instalację
        # byłaby myląca — lepiej zgłosić brak.
        with tempfile.TemporaryDirectory() as tmp:
            _executable(tmp, "somecli")
            with mock.patch.object(lc, "EXTRA_BIN_DIRS", (tmp,)):
                self.assertIsNone(
                    lc.find_executable("somecli", "/nie/ma/takiej/binarki"))

    def test_missing_binary_returns_none(self):
        self.assertIsNone(lc.find_executable("na-pewno-nie-ma-takiej-binarki"))


class CleanEnvTests(unittest.TestCase):
    def test_keeps_identity_vars_needed_for_the_keychain(self):
        with mock.patch.dict(os.environ, {"USER": "u", "LOGNAME": "u"}):
            env = lc.clean_env()
        self.assertEqual(env["USER"], "u")
        self.assertEqual(env["LOGNAME"], "u")

    def test_child_path_is_the_augmented_one(self):
        with mock.patch.dict(os.environ, {"PATH": FINDER_PATH}):
            env = lc.clean_env()
        self.assertIn("/opt/homebrew/bin", env["PATH"].split(os.pathsep))

    def test_api_keys_are_not_inherited(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-x",
                                          "OPENAI_API_KEY": "sk-x"}):
            env = lc.clean_env()
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertNotIn("OPENAI_API_KEY", env)

    def test_extra_entries_are_merged(self):
        self.assertEqual(lc.clean_env({"CODEX_HOME": "/h"})["CODEX_HOME"], "/h")


if __name__ == "__main__":
    unittest.main()
