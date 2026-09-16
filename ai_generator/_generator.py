from aqt import mw

from ..common import ADDON_NAME


def get_config() -> dict:
    full_config = mw.addonManager.getConfig(ADDON_NAME)
    return full_config.get("ai_generator", {})
