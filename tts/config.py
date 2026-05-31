"""TTS configuration helpers."""

from ..common import get_module_config, unique, normalize_float


_DEFAULTS = {
    "tts_provider":          "kokoro",
    "button_label":          "TTS",
    "api_url":               "http://localhost:8880/v1/audio/speech",
    "model":                 "kokoro",
    "openrouter_api_key":    "",
    "use_ai_openrouter_key": False,
    "openrouter_model":      "openai/gpt-4o-mini-tts-2025-12-15",
    "voices":                ["af_bella", "af_heart", "bm_lewis"],
    "speed":                 0.9,
    "ang_source_field":      "ang",
    "ang_target_field":      "audio",
    "przyklad_target_field": "przyklad",
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


def validate_config(config: dict) -> bool:
    from aqt.utils import showWarning

    provider = config.get("tts_provider", "kokoro")
    if provider == "openrouter":
        api_key = resolve_openrouter_key(config)
        if not api_key:
            showWarning(
                "Brak klucza API OpenRouter.\n"
                "Wpisz klucz w ustawieniach TTS lub zaznacz "
                "\"Użyj klucza z AI Generatora\"."
            )
            return False
    else:
        if not config.get("api_url", "").strip():
            showWarning("Brak adresu API Kokoro w ustawieniach TTS.")
            return False
    voices = unique(config.get("voices", []))
    if not voices:
        showWarning("Nie zaznaczono żadnego głosu w ustawieniach TTS.")
        return False
    return True


def get_tasks(config: dict) -> list[dict]:
    tasks = config.get("tasks")
    if tasks and isinstance(tasks, list):
        return [t for t in tasks if isinstance(t, dict) and t.get("label")]
    result = []
    ang_src = config.get("ang_source_field", "ang")
    ang_dst = config.get("ang_target_field", "audio")
    if ang_src and ang_dst:
        result.append({
            "label": "Generuj audio dla ang",
            "source_field": ang_src,
            "target_field": ang_dst,
            "mode": "single",
        })
    przykl = config.get("przyklad_target_field", "przyklad")
    if przykl:
        result.append({
            "label": "Generuj audio dla przykładów",
            "source_field": przykl,
            "target_field": przykl,
            "mode": "split",
            "split_separator": "<br><br>",
        })
    return result
