"""Natywny pasek postępu Anki (mw.progress) dla operacji batch w tle.

Używamy `mw.progress` zamiast własnego `QProgressDialog` celowo: trzyma Anki
w stanie „busy", więc timer automatycznej kopii zapasowej / synchronizacji
odkłada się, zamiast wyskakiwać własnym modalem NAD naszym paskiem i blokować
przycisk Anuluj. Jest jeden pasek postępu, a Anuluj to natywny przycisk Anki —
zawsze na wierzchu, zawsze klikalny. Ceną jest zablokowanie całego okna Anki
na czas operacji (co przy długim batchu i tak nie przeszkadza).

Wzorzec użycia:

    cancel_flag = start_progress("TTS", total, "TTS")
    def task():
        for i, item in enumerate(items):
            if cancel_flag["cancelled"]:
                break
            ...  # praca w tle
            update_progress(cancel_flag, "TTS", i + 1, total)
    def on_done(fut):
        finish_progress()   # główny wątek, PRZED ewentualnym CollectionOp
        ...
    mw.taskman.run_in_background(task, on_done)

`update_progress` czyta `mw.progress.want_cancel()` na głównym wątku i ustawia
`cancel_flag["cancelled"]`; wątki robocze pollują tę flagę, żeby przerwać.
"""

from aqt import mw


def start_progress(label: str, total: int, title: str = "") -> dict:
    """Pokaż natywny pasek postępu i zwróć cancel_flag (poll w wątku roboczym)."""
    mw.progress.start(label=f"{label}...", max=total, immediate=True)
    if title:
        try:
            mw.progress.set_title(title)
        except Exception:
            pass
    return {"cancelled": False}


def update_progress(cancel_flag: dict, label: str, done: int, total: int) -> None:
    """Zaktualizuj pasek (na głównym wątku) i przenieś want_cancel() → cancel_flag."""
    def _update():
        if mw.progress.want_cancel():
            cancel_flag["cancelled"] = True
        mw.progress.update(label=f"{label}: {done}/{total}...", value=done, max=total)
    mw.taskman.run_on_main(_update)


def finish_progress() -> None:
    """Zamknij pasek. Wołaj na głównym wątku PRZED startem CollectionOp
    (dwa równoczesne mw.progress = „already busy")."""
    mw.progress.finish()


def load_notes(nids, label: str = "Wczytywanie notatek", load=None):
    """Read notes on the main thread; a big Browser selection gets a bar.

    Returns None when the user cancels. `load(nid)` defaults to get_note.
    """
    load = load or mw.col.get_note
    nids = list(nids)
    if len(nids) < 500:
        return [load(nid) for nid in nids]
    mw.progress.start(label=f"{label}...", max=len(nids), immediate=True)
    try:
        notes = []
        for i, nid in enumerate(nids):
            if i % 200 == 0:
                if mw.progress.want_cancel():
                    return None
                mw.progress.update(label=f"{label}: {i}/{len(nids)}...", value=i, max=len(nids))
                mw.app.processEvents()  # the loop holds the main thread: let the bar repaint
            notes.append(load(nid))
        return notes
    finally:
        mw.progress.finish()
