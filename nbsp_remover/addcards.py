# -*- coding: utf-8 -*-
# 2022 - Matthias M. | @kleinerpirat

import re
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
    NBSP, DIV_TAG_RE, DIV_WRAP_RE, TRAILING_BR_RE,
)

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
        nbsp_matches = value.count(NBSP)
        if nbsp_matches > 0:
            nbsp_count = nbsp_count + nbsp_matches
            value = value.replace(NBSP, " ")

        if name == skip_field:
            # Remove <div> tags (with or without attributes) and </div> from skip field
            div_matches = len(re.findall(DIV_TAG_RE, value))
            if div_matches > 0:
                div_count = div_count + div_matches
                value = re.sub(DIV_TAG_RE, "", value)
        else:
            # Replace <div>TEKST</div> with TEKST<br> in other fields
            div_br_matches = re.findall(DIV_WRAP_RE, value, re.DOTALL)
            if len(div_br_matches) > 0:
                div_br_count = div_br_count + len(div_br_matches)
                value = re.sub(DIV_WRAP_RE, r"\1<br>", value, flags=re.DOTALL)
                # Remove trailing <br> if it's at the end of the field
                value = re.sub(TRAILING_BR_RE, "", value)

        note[name] = value

    if nbsp_count > 0 or div_count > 0 or div_br_count > 0:
        mw.col.update_note(note)
        addcards = _addcards_ref() if _addcards_ref is not None else None
        editing_tooltip(addcards, nbsp_count, div_count, div_br_count)


def init_addcards() -> None:
    add_cards_did_init(store_addcards)
    add_cards_did_add_note.append(on_add)
