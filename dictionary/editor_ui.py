from aqt import mw
from aqt.utils import tooltip
from aqt.qt import QTimer
from aqt.editor import Editor
from aqt.sound import av_player

from ..common import ADDON_NAME

from .service import process_note_group


def _get_config() -> dict:
    full_config = mw.addonManager.getConfig(ADDON_NAME)
    return full_config.get("dictionary", {})


# Tracks editor instances currently fetching — prevents double-click races.
_FETCHING: set[int] = set()


def _on_fetch_audio_editor(editor: Editor, dictionaries: list[str]):
    editor_id = id(editor)
    if editor_id in _FETCHING:
        tooltip("Pobieranie wymowy już trwa...", parent=mw, period=2000)
        return
    _FETCHING.add(editor_id)

    config = _get_config()

    def start():
        # saveNow synced the webview → editor.note, so the source field
        # reflects what the user just typed.
        note = editor.note
        if note is None:
            _FETCHING.discard(editor_id)
            return

        def task():
            return process_note_group(note, config, dictionaries)

        def on_done(fut):
            _FETCHING.discard(editor_id)
            try:
                result = fut.result()
            except Exception as e:
                tooltip(f"Błąd pobierania wymowy: {e}", parent=mw, period=5000)
                return

            if result.note_modified:
                # Only refresh the editor if it still shows the processed note;
                # otherwise persist directly so the fetched audio isn't lost.
                if editor.note is note:
                    editor.loadNote()
                elif note.id:
                    mw.col.update_note(note)

                audio_files = result.saved_filenames

                def play_next(files):
                    if not files:
                        return
                    file = files.pop(0)
                    av_player.play_file(file)
                    if files:
                        QTimer.singleShot(1200, lambda: play_next(files))

                if audio_files:
                    play_next(audio_files)
            elif result.audio_skipped:
                tooltip("Pole audio już zawiera treść.", parent=mw, period=3000)
            elif result.audio_requested and not result.audio_found:
                tooltip("Brak audio do pobrania dla tego hasła.", parent=mw, period=3000)

        mw.taskman.run_in_background(task, on_done)

    editor.saveNow(start)


def on_editor_buttons_init(buttons: list, editor: Editor):
    config = _get_config()

    enabled = [(b.get("label", "Audio"), b.get("dictionaries", []))
               for b in config.get("buttons", [])
               if b.get("enabled") and b.get("dictionaries")]

    if not enabled:
        return

    if len(enabled) == 1:
        # Single dictionary — simple button
        label, dicts = enabled[0]
        btn = editor.addButton(
            None,
            f"fetch_{'_'.join(dicts)}",
            lambda ed=editor, d=dicts: _on_fetch_audio_editor(ed, d),
            tip=label,
            label=label,
        )
        buttons.append(btn)
    else:
        # Multiple dictionaries — one button per dictionary group
        for label, dicts in enabled:
            btn = editor.addButton(
                None,
                f"fetch_{'_'.join(dicts)}",
                lambda ed=editor, d=dicts: _on_fetch_audio_editor(ed, d),
                tip=label,
                label=label,
            )
            buttons.append(btn)
