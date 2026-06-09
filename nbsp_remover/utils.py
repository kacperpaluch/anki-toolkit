# -*- coding: utf-8 -*-
# 2022 - Matthias M. | @kleinerpirat

from aqt import mw
from aqt.utils import tooltip

from ..common import get_module_config
from .cleaning import NBSP, DIV_TAG_RE, DIV_WRAP_RE, TRAILING_BR_RE

NBSP_REMOVER_KEY = "nbsp_remover"

_NBSP_DEFAULTS = {
    "show_tooltip": True,
    "auto_run_startup": False,
    "skip_field": "ang",
}

def _get_config() -> dict:
    return get_module_config(NBSP_REMOVER_KEY, _NBSP_DEFAULTS)


def _get_skip_field() -> str:
    return _get_config().get("skip_field", "ang")


def _show_tooltip() -> bool:
    return _get_config().get("show_tooltip", True)


def purge_tooltip(parent, nbsp_count, div_count=0, div_br_count=0) -> None:
    if not _show_tooltip():
        return

    skip_field = _get_skip_field()
    total_count = nbsp_count + div_count + div_br_count

    if total_count > 0:
        message = f"Wyczyszczono elementy HTML: {total_count}<br>"
        if nbsp_count > 0:
            message += f"- Zamieniono &amp;nbsp; na spację: {nbsp_count}<br>"
        if div_count > 0:
            message += f"- Usunięto tagi &lt;div&gt; z pola '{skip_field}': {div_count}<br>"
        if div_br_count > 0:
            message += f"- Zamieniono bloki &lt;div&gt; na &lt;br&gt;: {div_br_count}<br>"
    else:
        message = "Nie znaleziono elementów HTML wymagających czyszczenia."

    tooltip(message, parent=parent)


def editing_tooltip(parent, nbsp_count, div_count=0, div_br_count=0) -> None:
    if not _show_tooltip():
        return

    skip_field = _get_skip_field()
    total_count = nbsp_count + div_count + div_br_count

    if total_count > 0:
        message = f"Wyczyszczono elementy HTML: {total_count}<br>"
        if nbsp_count > 0:
            message += f"- &amp;nbsp;: {nbsp_count}<br>"
        if div_count > 0:
            message += f"- &lt;div&gt; z pola '{skip_field}': {div_count}<br>"
        if div_br_count > 0:
            message += f"- &lt;div&gt; zamienione na &lt;br&gt;: {div_br_count}<br>"
        
        tooltip(message, parent=parent)
