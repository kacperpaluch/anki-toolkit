from typing import Optional

from aqt import mw

from ..common import ADDON_NAME

from .field_generator import FieldGenerator

_generator: Optional[FieldGenerator] = None
_cached_config: Optional[dict] = None


def get_generator() -> FieldGenerator:
    global _generator, _cached_config
    config = get_config()
    if _generator is None or _cached_config != config:
        _generator = FieldGenerator(config)
        _cached_config = config
    return _generator


def reset_generator() -> None:
    global _generator, _cached_config
    _generator = None
    _cached_config = None


def get_config() -> dict:
    full_config = mw.addonManager.getConfig(ADDON_NAME)
    return full_config.get("ai_generator", {})
