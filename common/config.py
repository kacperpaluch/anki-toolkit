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
