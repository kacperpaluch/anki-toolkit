# -*- coding: utf-8 -*-
# 2022 - Matthias M. | @kleinerpirat

from aqt import mw
from aqt.utils import tooltip

from ..common import get_module_config

NBSP_REMOVER_KEY = "nbsp_remover"

_NBSP_DEFAULTS = {
    "show_tooltip": True,
    "auto_run_startup": False,
    "skip_field": "ang",
}

NBSP = "&nbsp;"
DIV_TAG_RE = r"</?div[^>]*>"
DIV_WRAP_RE = r"<div[^>]*>(.*?)</div>"
TRAILING_BR_RE = r"<br>\s*$"


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
    notes = "note" if total_count == 1 else "notes"

    if total_count > 0:
        message = f"{total_count} {notes} updated:<br>"
        if nbsp_count > 0:
            message += f"- Removed {nbsp_count} &amp;nbsp;<br>"
        if div_count > 0:
            message += f"- Removed {div_count} &lt;div&gt; tags from '{skip_field}' field<br>"
        if div_br_count > 0:
            message += f"- Replaced {div_br_count} &lt;div&gt; tags with &lt;br&gt; in other fields<br>"
        message += "<div>! ̿̿ ̿̿ ̿̿ ̿'̿'\̵͇̿̿\з= ( ▀ ͜͞ʖ▀) =ε/̵͇̿̿/'̿'̿ ̿ ̿̿ ̿̿ ̿̿</div>"
    else:
        message = f"No unwanted tags found.<br><div>&amp;nbsp; and &lt;div&gt; tags are quiet today...\n(▀̿Ĺ̯▀̿ ̿)</div>"

    tooltip(message, parent=parent)


def editing_tooltip(parent, nbsp_count, div_count=0, div_br_count=0) -> None:
    if not _show_tooltip():
        return

    skip_field = _get_skip_field()
    total_count = nbsp_count + div_count + div_br_count

    if total_count > 0:
        message = f"Exterminated {total_count} unwanted tags!<br>"
        if nbsp_count > 0:
            message += f"- {nbsp_count} &amp;nbsp;<br>"
        if div_count > 0:
            message += f"- {div_count} &lt;div&gt; tags from '{skip_field}' field<br>"
        if div_br_count > 0:
            message += f"- {div_br_count} &lt;div&gt; tags replaced with &lt;br&gt;<br>"
        message += "<div>! ̿̿ ̿̿ ̿̿ ̿'̿'\̵͇̿̿\з= ( ▀ ͜͞ʖ▀) =ε/̵͇̿̿/'̿'̿ ̿ ̿̿ ̿̿ ̿̿</div>"
        
        tooltip(message, parent=parent)