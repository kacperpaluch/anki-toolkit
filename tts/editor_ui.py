"""TTS editor button — generate audio for the current note."""

import concurrent.futures
import logging
import random
import re

from aqt import mw
from aqt.editor import Editor
from aqt.utils import tooltip

from .config import get_tts_config, get_tasks, validate_config
from .api import generate_audio
from ..common import unique_filename, clean_html, unique

logger = logging.getLogger(__name__)

# Tracks editor instances currently generating TTS — prevents double-click races.
_GENERATING: set[int] = set()


def on_editor_buttons_init(buttons: list, editor: Editor):
    config = get_tts_config()
    tasks = get_tasks(config)
    if not tasks:
        return

    label = config.get("button_label", "TTS")

    btn = editor.addButton(
        None,
        "tts_gen",
        lambda ed=editor: _on_tts_editor(ed),
        tip="Generuj audio TTS dla tej notatki",
        label=label,
    )
    buttons.append(btn)


def _on_tts_editor(editor: Editor):
    editor_id = id(editor)
    if editor_id in _GENERATING:
        tooltip("TTS: generowanie już trwa...", period=2000)
        return
    _GENERATING.add(editor_id)

    def start():
        _start_tts_editor(editor, editor_id)

    editor.saveNow(start)


def _start_tts_editor(editor: Editor, editor_id: int):
    note = editor.note
    if not note:
        _GENERATING.discard(editor_id)
        tooltip("Brak notatki w edytorze.")
        return

    config = get_tts_config()
    if not validate_config(config):
        _GENERATING.discard(editor_id)
        return

    voices = unique(config.get("voices", []))
    if not voices:
        _GENERATING.discard(editor_id)
        tooltip("Brak skonfigurowanych głosów TTS.")
        return

    tasks = get_tasks(config)
    if not tasks:
        _GENERATING.discard(editor_id)
        return

    work_items = []
    for task_i, task in enumerate(tasks):
        mode = task.get("mode", "single")
        source_field = task.get("source_field", "")
        target_field = task.get("target_field", "")
        split_sep = task.get("split_separator", "<br><br>")

        if mode == "split":
            if source_field not in note:
                continue
            sep_pattern = re.escape(split_sep).replace(r"\ ", r"\s*")
            sep_re = re.compile(f"(?:{sep_pattern}){{1,}}")
            raw_segments = sep_re.split(note[source_field])
            note_voices = list(voices)
            random.shuffle(note_voices)
            for seg_i, seg in enumerate(raw_segments):
                if "[sound:" in seg:
                    continue
                text = clean_html(seg)
                if not text:
                    continue
                voice = note_voices[seg_i % len(note_voices)]
                work_items.append({
                    "task_i": task_i,
                    "mode": "split",
                    "source_field": source_field,
                    "target_field": target_field,
                    "split_sep": split_sep,
                    "seg_i": seg_i,
                    "text": text,
                    "voice": voice,
                })
        else:
            if source_field not in note or target_field not in note:
                continue
            if "[sound:" in note[target_field]:
                continue
            text = clean_html(note[source_field])
            if not text:
                continue
            voice = random.choice(voices)
            work_items.append({
                "task_i": task_i,
                "mode": "single",
                "source_field": source_field,
                "target_field": target_field,
                "text": text,
                "voice": voice,
            })

    if not work_items:
        _GENERATING.discard(editor_id)
        tooltip("TTS: brak pól do wygenerowania.", period=5000)
        return

    def bg_task():
        results = {}
        errors = 0

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=int(config.get("max_workers", 8))
        ) as pool:
            future_map = {}
            for idx, item in enumerate(work_items):
                future = pool.submit(
                    generate_audio, item["text"], config, item["voice"]
                )
                future_map[future] = (idx, item)

            for future in concurrent.futures.as_completed(future_map):
                idx, item = future_map[future]
                try:
                    audio_bytes = future.result()
                    fname = unique_filename()
                    mw.col.media.write_data(fname, audio_bytes)
                    key = (item.get("task_i", 0), item["target_field"], item.get("seg_i", -1))
                    results[key] = fname
                except Exception as e:
                    logger.error(f"TTS editor error: {e}")
                    errors += 1

        return results, errors

    def on_done(future):
        _GENERATING.discard(editor_id)
        try:
            results, errors = future.result()
        except Exception as e:
            tooltip(f"TTS: błąd generowania — {e}", period=8000)
            return

        if not results:
            tooltip(
                f"TTS: nie udało się wygenerować audio ({errors} błędów).",
                period=8000,
            )
            return

        def apply():
            for idx, item in enumerate(work_items):
                key = (item.get("task_i", 0), item["target_field"], item.get("seg_i", -1))
                fname = results.get(key)
                if not fname:
                    continue

                if item["mode"] == "single":
                    note[item["target_field"]] = f"[sound:{fname}]"

            split_updates = {}
            for idx, item in enumerate(work_items):
                if item["mode"] != "split":
                    continue
                key = (item.get("task_i", 0), item["target_field"], item["seg_i"])
                fname = results.get(key)
                if fname:
                    split_key = (item.get("task_i", 0), item["target_field"])
                    if split_key not in split_updates:
                        split_updates[split_key] = (
                            item["source_field"],
                            item["split_sep"],
                            note[item["source_field"]],
                            []
                        )
                    split_updates[split_key][3].append(
                        (item["seg_i"], fname)
                    )

            for (_task_i, target_field), (source_field, split_sep, raw_text, seg_updates) in split_updates.items():
                sep_pattern = re.escape(split_sep).replace(r"\ ", r"\s*")
                sep_re = re.compile(f"(?:{sep_pattern}){{1,}}")
                segments = sep_re.split(raw_text)
                fname_by_seg = dict(seg_updates)
                parts = []
                for i, seg in enumerate(segments):
                    content = seg
                    if i in fname_by_seg:
                        content += f"[sound:{fname_by_seg[i]}]"
                    parts.append(content)
                note[target_field] = split_sep.join(parts)

            # User may have switched notes while audio was generating — only
            # refresh the editor if it still shows the processed note,
            # otherwise persist directly so the audio isn't lost.
            if editor.note is note:
                editor.loadNote()
            elif note.id:
                mw.col.update_note(note)

            msg = f"TTS: wygenerowano {len(results)} plików audio."
            if errors:
                msg += f" Błędy: {errors}."
            tooltip(msg, period=8000)

        if editor.note is note:
            editor.saveNow(apply)
        else:
            apply()

    mw.taskman.run_in_background(bg_task, on_done)
