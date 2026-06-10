# -*- coding: utf-8 -*-
# 2022 - Matthias M. | @kleinerpirat

from anki.collection import Collection, OpChanges
from aqt import mw
from aqt.operations import CollectionOp

from .cleaning import clean_field
from .utils import purge_tooltip, _get_skip_field


def clean_collection() -> None:
    """Clean &nbsp; and <div> tags in all notes.

    Uses the same clean_field() logic as the add-cards hook, so collection-wide
    cleanup behaves identically (incl. multi-line divs and trailing <br>).
    """
    skip_field = _get_skip_field()
    counters = {"nbsp": 0, "div": 0, "div_br": 0}

    def op(col: Collection) -> OpChanges:
        changed_notes = []
        for nid in col.find_notes(""):
            note = col.get_note(nid)
            note_changed = False
            for name, value in note.items():
                cleaned, nbsp_c, div_c, div_br_c = clean_field(name, value, skip_field)
                if cleaned != value:
                    note[name] = cleaned
                    note_changed = True
                counters["nbsp"] += nbsp_c
                counters["div"] += div_c
                counters["div_br"] += div_br_c
            if note_changed:
                changed_notes.append(note)
        if changed_notes:
            return col.update_notes(changed_notes)
        return OpChanges()

    def on_success(_changes: OpChanges) -> None:
        purge_tooltip(mw, counters["nbsp"], counters["div"], counters["div_br"])

    CollectionOp(parent=mw, op=op).success(on_success).run_in_background()
