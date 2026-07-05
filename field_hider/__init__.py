"""Field Hider — ukrywa wybrane pola w edytorze, ale TYLKO przy dodawaniu nowych kart.

Natywnie Anki pokazuje wszystkie pola typu notatki. Ten moduł chowa wskazane
pola w oknie „Dodaj” (np. pomocnicze pola wypełniane później przez AI/TTS),
żeby nie rozpraszały przy wpisywaniu. W przeglądarce i przy edycji istniejących
kart pola pozostają widoczne — chowanie działa wyłącznie w trybie ADD_CARDS.

Konfiguracja: config.json → "field_hider":
    {"hidden_fields": {"NazwaTypuNotatki": ["Pole3", "Pole7"]}}

Przycisk 👁 w pasku edytora (tylko w oknie „Dodaj”) tymczasowo pokazuje schowane
pola bez zmiany konfiguracji.
"""

import json
import logging

try:  # pominięte przy uruchomieniu jako zwykły skrypt (self-check jądra)
    from ..common import get_module_config
except ImportError:
    get_module_config = None

log = logging.getLogger(__name__)

_MODULE_KEY = "field_hider"
_DEFAULTS = {"hidden_fields": {}}


def indices_to_hide(field_names, targets):
    """Czyste jądro: indeksy pól do ukrycia (0-based, w kolejności pól)."""
    targets = set(targets or [])
    return [i for i, name in enumerate(field_names) if name in targets]


def _hidden_fields() -> dict:
    return get_module_config(_MODULE_KEY, _DEFAULTS).get("hidden_fields") or {}


def on_editor_load_note(editor) -> None:
    """editor_did_load_note — wstrzykuje CSS chowający pola, tylko w trybie „Dodaj”."""
    # addMode = okno „Dodaj”. W przeglądarce/edycji istniejącej karty nie chowamy.
    if not getattr(editor, "addMode", False):
        return

    note = editor.note
    nt = note.note_type() if note else None
    if not nt:
        return

    targets = _hidden_fields().get(nt["name"], [])
    idx = indices_to_hide([f["name"] for f in nt["flds"]], targets)

    if idx:
        sel = ", ".join(
            f'body:not(.hf-reveal) .field-container[data-index="{i}"]' for i in idx
        )
        css = f"{sel} {{ display: none !important; }}"
    else:
        css = ""

    editor.web.eval(
        "(function(){"
        "let s=document.getElementById('hf-style');"
        "if(!s){s=document.createElement('style');s.id='hf-style';"
        "document.head.appendChild(s);}"
        f"s.textContent={json.dumps(css)};"
        "})();"
    )


def _on_toggle(editor) -> None:
    editor.web.eval("document.body.classList.toggle('hf-reveal');")


def on_editor_buttons_init(buttons, editor):
    """editor_did_init_buttons — przycisk 👁 tylko tam, gdzie pola są chowane."""
    if not getattr(editor, "addMode", False):
        return buttons
    buttons.append(
        editor.addButton(
            icon=None,
            cmd="hf_toggle",
            func=_on_toggle,
            tip="Pokaż/ukryj schowane pola",
            label="👁",
        )
    )
    return buttons


if __name__ == "__main__":
    # ponytail: jedyny check jaki tu ma sens — czyste jądro mapowania nazw->indeksy
    assert indices_to_hide(["A", "B", "C", "D"], ["B", "D"]) == [1, 3]
    assert indices_to_hide(["A", "B"], ["X"]) == []
    assert indices_to_hide(["A", "B"], []) == []
    print("ok")
