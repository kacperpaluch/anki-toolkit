from aqt import mw

from .consts import ADDON_NAME


def get_full_config() -> dict:
    return mw.addonManager.getConfig(ADDON_NAME) or {}


def save_full_config(cfg: dict) -> None:
    mw.addonManager.writeConfig(ADDON_NAME, cfg)


def get_module_config(module_key: str, defaults: dict | None = None) -> dict:
    full = get_full_config()
    cfg = full.get(module_key, {})
    if defaults:
        # Merge instead of filtering to defaults' keys — otherwise any key
        # missing from the defaults dict silently disappears from the config.
        return {**defaults, **cfg}
    return cfg


def save_module_config(module_key: str, cfg: dict) -> None:
    full = get_full_config()
    full[module_key] = cfg
    save_full_config(full)


def update_module_config(module_key: str, changes: dict) -> None:
    """Merge `changes` into one section, keeping keys this caller doesn't know."""
    full = get_full_config()
    full[module_key] = {**(full.get(module_key) or {}), **changes}
    save_full_config(full)


def check_config(parent=None) -> bool:
    """Name hand-edited values of the wrong type and offer their defaults.

    Returns False when the user keeps the broken config.
    """
    from aqt.utils import askUser
    from .config_check import describe, find_type_errors, reset_to_defaults
    cfg = get_full_config()
    errors = find_type_errors(cfg)
    if not errors:
        return True
    if not askUser(
        "Konfiguracja Anki Toolkit ma wartości złego typu (np. po ręcznej edycji):\n\n"
        + describe(errors)
        + "\n\nPrzywrócić dla nich wartości domyślne? Pozostałe ustawienia zostaną bez zmian.",
        parent=parent or mw, title="Anki Toolkit — konfiguracja",
    ):
        return False
    reset_to_defaults(cfg, errors)
    save_full_config(cfg)
    return True
