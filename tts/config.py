"""TTS configuration helpers."""

from ..common import get_module_config, unique, normalize_float


_DEFAULTS = {
    "button_label":          "TTS",
    "openrouter_api_key":    "",
    "use_ai_openrouter_key": False,
    "openrouter_model":      "openai/gpt-4o-mini-tts-2025-12-15",
    "openrouter_provider":   "",
    "voices":                ["af_bella", "af_heart", "bm_lewis"],
    "replacements":          {},
    "speed":                 0.9,
    "max_workers":           12,
    "max_retries":           3,
    "timeout":               60,
    "tasks": [
        {"label": "Generuj audio dla ang",    "source_field": "ang",      "target_field": "audio",    "mode": "single"},
        {"label": "Generuj audio dla przykł.", "source_field": "przyklad", "target_field": "przyklad", "mode": "split", "split_separator": "<br><br>"},
    ],
}


def get_tts_config() -> dict:
    return get_module_config("tts", _DEFAULTS)


def resolve_openrouter_key(config: dict) -> str:
    if config.get("use_ai_openrouter_key", False):
        from ..common import get_full_config
        full = get_full_config()
        ai = full.get("ai_generator", {})
        providers = ai.get("providers", {})
        or_provider = providers.get("openrouter", {})
        return or_provider.get("api_key", "").strip()
    return config.get("openrouter_api_key", "").strip()


def _warn(msg: str) -> None:
    # Qt UI calls must always happen on the main thread; workers use config_error().
    from aqt import mw
    from aqt.utils import showWarning
    mw.taskman.run_on_main(lambda: showWarning(msg))


def config_error(config: dict) -> str | None:
    """Why TTS cannot run, or None. No UI — safe from a worker thread."""
    if not resolve_openrouter_key(config):
        return (
            "Brak klucza API OpenRouter.\n"
            "Wpisz klucz w ustawieniach TTS lub zaznacz "
            "\"Użyj klucza z AI Generatora\"."
        )
    if not unique(config.get("voices", [])):
        return "Nie zaznaczono żadnego głosu w ustawieniach TTS."
    return None


def validate_config(config: dict) -> bool:
    error = config_error(config)
    if error:
        _warn(error)
    return not error


def get_tasks(config: dict) -> list[dict]:
    """Configured TTS tasks; an explicitly empty list means "no tasks"."""
    tasks = config.get("tasks")
    if not isinstance(tasks, list):
        return list(_DEFAULTS["tasks"])
    return [t for t in tasks if isinstance(t, dict) and t.get("label")]
