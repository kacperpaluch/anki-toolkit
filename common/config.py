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
        return {k: cfg.get(k, v) for k, v in defaults.items()}
    return cfg


def save_module_config(module_key: str, cfg: dict) -> None:
    full = get_full_config()
    full[module_key] = cfg
    save_full_config(full)
