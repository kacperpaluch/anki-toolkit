"""Shared guard for asynchronous operations on one Anki editor.

Two responsibilities:
  * one Toolkit operation at a time per editor (begin/finish),
  * workers never touch the note the editor is showing (detach/merge).
"""

import copy

_ATTR = "_anki_toolkit_operation"


def begin_editor_operation(editor, label: str):
    """Acquire the editor guard, returning an ownership token or None."""
    if getattr(editor, _ATTR, None) is not None:
        return None
    token = object()
    setattr(editor, _ATTR, (token, label))
    return token


def active_editor_operation(editor) -> str:
    current = getattr(editor, _ATTR, None)
    return current[1] if current else "inna operacja"


def finish_editor_operation(editor, token) -> None:
    """Release the guard only when token still owns it."""
    current = getattr(editor, _ATTR, None)
    if current is not None and current[0] is token:
        delattr(editor, _ATTR)


# ---------------------------------------------------------------------------
# Detached work — the guard blocks a second Toolkit run, not the user's typing
# ---------------------------------------------------------------------------

def detach_note(note):
    """Return (clone, before) — a copy safe to mutate off the main thread.

    The user keeps typing while we generate, so a worker writing into the
    editor's own note either loses their edit or gets lost itself. Workers
    mutate the clone; merge_note() decides what may be written back.
    `before` is the field snapshot the merge compares against.
    """
    clone = copy.copy(note)
    clone.fields = list(note.fields)
    clone.tags = list(note.tags)
    clone._toolkit_field_names = note.keys()
    from aqt import mw
    clone._toolkit_collection = mw.col
    # Note.note_type() otherwise reaches the collection's model manager from
    # the worker. Freeze that lookup while still on the main thread.
    if hasattr(note, "note_type"):
        model = copy.deepcopy(note.note_type())
        clone.note_type = lambda: model
    return clone, list(note.fields)


def merge_note(note, clone, before) -> list:
    """Write fields the worker changed on *clone* back into *note*.

    If any field differs from `before`, inputs may be stale: skip this step's
    output and return its target names. Rebase the clone and snapshot to the
    user's current values before the next workflow step.
    """
    skipped: list = []
    names = note.keys()
    if names != clone._toolkit_field_names or getattr(note, "mid", None) != getattr(clone, "mid", None):
        raise RuntimeError("Typ lub pola notatki zmieniły się podczas generowania")
    # Any field can be an input to an AI prompt or workflow step. Without a
    # dependency graph, reject this step's output if its inputs changed.
    if list(note.fields) != before:
        skipped = [names[i] for i in range(len(before))
                   if clone.fields[i] != before[i]]
        clone.fields[:] = note.fields
        before[:] = note.fields
        return skipped
    for i in range(min(len(note.fields), len(clone.fields), len(before), len(names))):
        if clone.fields[i] == before[i]:
            continue                      # worker didn't touch this field
        note.fields[i] = clone.fields[i]
    clone.fields[:] = list(note.fields)
    before[:] = list(note.fields)
    return skipped


def merge_editor_note(editor, note, clone, before) -> list:
    """Commit one detached step after saveNow, then refresh before the next.

    When the editor moved away, merge into a freshly read note, never the old
    snapshot. A closed/replaced collection cannot receive a late result.
    """
    from aqt import mw
    from aqt.operations import on_op_finished
    col = clone._toolkit_collection
    if col is None or mw.col is not col:
        raise RuntimeError("Profil zmienił się podczas generowania")
    current = note if editor_shows_note(editor, note) else None
    if current is note:
        target = note
    elif note.id:
        target = col.get_note(note.id)
    else:
        raise RuntimeError("Nowa notatka została zamknięta podczas generowania")
    previous = list(target.fields)
    skipped = merge_note(target, clone, before)
    if target.id and target.fields != previous:
        changes = col.update_note(target)
        on_op_finished(mw, changes, editor)
    if editor_shows_note(editor, note):
        editor.loadNote()
    return skipped


# ---------------------------------------------------------------------------
# Browser batches — the same rule for notes that are not open in an editor
# ---------------------------------------------------------------------------

def snapshot_fields(notes) -> dict:
    """{note id: field values} taken on the main thread before the workers start."""
    return {note.id: list(note.fields) for note in notes}


def merge_detached_notes(col, expected_col, notes, before, skipped: list):
    """CollectionOp body: write the workers' field changes into fresh notes.

    A note that changed in the collection while the batch ran (another
    operation finished meanwhile) is left untouched and its id is appended to
    `skipped` — its fields may have been the inputs, so the result is stale.
    """
    if col is not expected_col:
        raise RuntimeError("Profil zmienił się podczas operacji — nic nie zapisano")
    fresh = []
    for note in notes:
        old = before[note.id]
        try:
            current = col.get_note(note.id)
        except Exception:
            skipped.append(note.id)  # deleted meanwhile
            continue
        if current.mid != note.mid or list(current.fields) != old:
            skipped.append(note.id)
            continue
        changed = False
        for i, value in enumerate(note.fields):
            if value != old[i]:
                current.fields[i] = value
                changed = True
        if changed:
            fresh.append(current)
    return col.update_notes(fresh)


def save_detached_notes(parent, col, notes, before, summary: str) -> None:
    """Persist a Browser batch as one undoable op, then show the summary."""
    from aqt import mw
    from aqt.operations import CollectionOp
    from aqt.utils import tooltip
    if mw.col is not col:
        tooltip("Profil zmienił się podczas operacji — wyników nie zapisano.", period=8000)
        return
    if not notes:
        tooltip(summary, period=8000)
        return
    skipped: list = []

    def done(_changes):
        text = summary
        if skipped:
            text += f" · pominięto {len(skipped)} notatek zmienionych w trakcie"
        tooltip(text, period=8000)

    CollectionOp(
        parent=parent,
        op=lambda active: merge_detached_notes(active, col, notes, before, skipped),
    ).success(done).run_in_background()


def editor_shows_note(editor, note) -> bool:
    """A closed webview must not receive saveNow/loadNote callbacks."""
    if getattr(editor, "note", None) is not note:
        return False
    if hasattr(editor, "web"):
        from aqt.qt import sip
        if editor.web is None or sip.isdeleted(editor.web):
            return False
    return True
