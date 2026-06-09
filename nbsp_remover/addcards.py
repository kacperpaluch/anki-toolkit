# -*- coding: utf-8 -*-
# 2022 - Matthias M. | @kleinerpirat

import weakref
from anki.notes import Note
from aqt.addcards import AddCards
from aqt.gui_hooks import (
    add_cards_did_init,
    add_cards_did_add_note,
)

from aqt import mw

from .utils import (
    editing_tooltip, _get_skip_field,
)
from .cleaning import clean_field

# Słabe referencje — nie blokują GC, bezpieczne przy wielu oknach AddCards
_addcards_ref: "weakref.ref[AddCards] | None" = None


def store_addcards(instance: AddCards) -> None:
    global _addcards_ref
    _addcards_ref = weakref.ref(instance)


def on_add(note: Note) -> None:
    nbsp_count = 0
    div_count = 0
    div_br_count = 0
    skip_field = _get_skip_field()

    for (name, value) in note.items():
        cleaned, field_nbsp, field_div, field_div_br = clean_field(name, value, skip_field)
        nbsp_count += field_nbsp
        div_count += field_div
        div_br_count += field_div_br
        note[name] = cleaned

    if nbsp_count > 0 or div_count > 0 or div_br_count > 0:
        mw.col.update_note(note)
        addcards = _addcards_ref() if _addcards_ref is not None else None
        editing_tooltip(addcards, nbsp_count, div_count, div_br_count)


def init_addcards() -> None:
    add_cards_did_init(store_addcards)
    add_cards_did_add_note.append(on_add)
