"""TTS note processing — single-note and batch operations."""

import concurrent.futures
import logging
import random
import re

from aqt import mw
from aqt.utils import tooltip

from ..common import unique_filename, clean_html

from .api import generate_audio
from .config import get_tts_config, validate_config, get_tasks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Async batch processing (QProgressDialog + cancel)
# ---------------------------------------------------------------------------

def process_task_async(browser, nids: list, task: dict):
    from aqt.qt import QProgressDialog, Qt

    config = get_tts_config()
    if not validate_config(config):
        return

    label = task.get("label", "TTS")
    mode = task.get("mode", "single")
    from ..common import unique
    voices = unique(config.get("voices", []))
    if not voices:
        return

    items = _collect_work_items(nids, task, voices)

    if not items:
        tooltip(f"\"{label}\": brak pól wymagających generowania.")
        return

    mw.checkpoint("TTS Generate")

    progress = QProgressDialog(f"{label}...", "Anuluj", 0, len(items), browser)
    progress.setWindowTitle("TTS")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)

    cancel_flag = {"cancelled": False}
    progress.canceled.connect(lambda: cancel_flag.update(cancelled=True))

    def bg_task():
        results = {}
        errors = 0
        done = 0

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=int(config.get("max_workers", 12))
        ) as pool:
            future_map = {}
            for idx, item in enumerate(items):
                if cancel_flag["cancelled"]:
                    break
                future = pool.submit(
                    generate_audio, item["text"], config, item["voice"]
                )
                future_map[future] = (idx, item)

            for future in concurrent.futures.as_completed(future_map):
                if cancel_flag["cancelled"]:
                    break
                idx, item = future_map[future]
                try:
                    audio_bytes = future.result()
                    fname = unique_filename()
                    mw.col.media.write_data(fname, audio_bytes)
                    key = (item["nid"], item.get("seg_i", -1))
                    results[key] = fname
                except Exception as e:
                    logger.error(f"TTS error (nid={item['nid']}): {e}")
                    errors += 1
                done += 1
                _update = lambda d=done: (
                    progress.setLabelText(f"{label}... {d}/{len(items)}"),
                    progress.setValue(d),
                )
                mw.taskman.run_on_main(_update)

        return results, errors, cancel_flag["cancelled"]

    def on_done(fut):
        progress.close()
        try:
            results, errors, cancelled = fut.result()
        except Exception as e:
            tooltip(f"TTS: błąd — {e}", period=5000)
            return

        if cancelled:
            _save_batch_results(items, results, mode, task)
            browser.mw.reset()
            tooltip(f"\"{label}\": przerwano. Wygenerowano: {len(results)}, błędów: {errors}", period=8000)
            return

        _save_batch_results(items, results, mode, task)
        browser.mw.reset()
        tooltip(
            f"\"{label}\": zaktualizowano {len(set(k[0] for k in results))} notatek,"
            f" wygenerowano {len(results)} plików, błędów: {errors}",
            period=10000,
        )

    mw.taskman.run_in_background(bg_task, on_done)


def _collect_work_items(nids: list, task: dict, voices: list) -> list[dict]:
    source_field = task.get("source_field", "")
    target_field = task.get("target_field", "")
    mode = task.get("mode", "single")
    split_sep = task.get("split_separator", "<br><br>")

    items = []

    if mode == "split":
        sep_pattern = re.escape(split_sep).replace(r"\ ", r"\s*")
        sep_re = re.compile(f"(?:{sep_pattern}){{1,}}")

    for nid in nids:
        note = mw.col.get_note(nid)

        if mode == "split":
            if source_field not in note:
                continue
            raw_segments = sep_re.split(note[source_field])
            note_voices = voices[:]
            random.shuffle(note_voices)
            for seg_i, seg in enumerate(raw_segments):
                if "[sound:" in seg or not clean_html(seg):
                    continue
                text = clean_html(seg)
                if not text:
                    continue
                items.append({
                    "nid": nid,
                    "seg_i": seg_i,
                    "text": text,
                    "voice": note_voices[seg_i % len(note_voices)],
                    "target_field": target_field,
                    "split_sep": split_sep,
                    "raw_segments": list(raw_segments),
                    "mode": "split",
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
            items.append({
                "nid": nid,
                "seg_i": -1,
                "text": text,
                "voice": voice,
                "target_field": target_field,
                "mode": "single",
            })

    return items


def _save_batch_results(items: list, results: dict, mode: str, task: dict):
    target_field = task.get("target_field", "")
    split_sep = task.get("split_separator", "<br><br>")

    note_updates = {}

    for item in items:
        nid = item["nid"]
        seg_i = item.get("seg_i", -1)
        fname = results.get((nid, seg_i))
        if not fname:
            continue
        if nid not in note_updates:
            note_updates[nid] = {"single": {}, "split": {}}
        if item["mode"] == "split":
            note_updates[nid]["split"].setdefault(
                (target_field, split_sep, tuple(item.get("raw_segments", []))),
                {}
            )[seg_i] = fname
        else:
            note_updates[nid]["single"][target_field] = fname

    for nid, updates in note_updates.items():
        note = mw.col.get_note(nid)
        for tf, fname in updates["single"].items():
            note[tf] = f"[sound:{fname}]"
        for (tf, sep, segments), seg_map in updates["split"].items():
            parts = []
            for i, seg_text in enumerate(list(segments)):
                content = seg_text
                if i in seg_map:
                    content += f"[sound:{seg_map[i]}]"
                parts.append(content)
            note[tf] = sep.join(parts)
        mw.col.update_note(note)


# ---------------------------------------------------------------------------
# Single-note processing
# ---------------------------------------------------------------------------

def process_single_note(note, config: dict = None) -> bool:
    if config is None:
        config = get_tts_config()
    if not validate_config(config):
        return False

    tasks = get_tasks(config)
    if not tasks:
        return False

    from ..common import unique
    voices = unique(config.get("voices", []))
    if not voices:
        return False

    changed = False

    for task in tasks:
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
            note_voices = voices[:]
            random.shuffle(note_voices)

            parts = []
            note_changed = False
            for seg_i, seg in enumerate(raw_segments):
                content = seg
                if "[sound:" in seg or not clean_html(seg):
                    parts.append(content)
                    continue
                text = clean_html(seg)
                if not text:
                    parts.append(content)
                    continue
                voice = note_voices[seg_i % len(note_voices)]
                try:
                    audio_bytes = generate_audio(text, config, voice)
                    fname = unique_filename()
                    mw.col.media.write_data(fname, audio_bytes)
                    content += f"[sound:{fname}]"
                    note_changed = True
                except Exception as e:
                    logger.error(f"TTS error (nid={note.id}, seg={seg_i}): {e}")
                parts.append(content)

            if note_changed:
                note[target_field] = split_sep.join(parts)
                changed = True
        else:
            if source_field not in note or target_field not in note:
                continue
            if "[sound:" in note[target_field]:
                continue
            text = clean_html(note[source_field])
            if not text:
                continue
            voice = random.choice(voices)
            try:
                audio_bytes = generate_audio(text, config, voice)
                fname = unique_filename()
                mw.col.media.write_data(fname, audio_bytes)
                note[target_field] = f"[sound:{fname}]"
                changed = True
            except Exception as e:
                logger.error(f"TTS error (nid={note.id}): {e}")

    if changed:
        mw.col.update_note(note)

    return changed
