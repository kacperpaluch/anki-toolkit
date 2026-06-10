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
        state = {"done": 0}
        results, errors = _generate_items(
            items, config, label, cancel_flag, progress, state
        )
        return results, errors, cancel_flag["cancelled"]

    def on_done(fut):
        progress.close()
        try:
            results, errors, cancelled = fut.result()
        except Exception as e:
            tooltip(f"TTS: błąd — {e}", period=5000)
            return

        if cancelled:
            _save_batch_results(items, results, task)
            browser.mw.reset()
            tooltip(f"\"{label}\": przerwano. Wygenerowano: {len(results)}, błędów: {errors}", period=8000)
            return

        _save_batch_results(items, results, task)
        browser.mw.reset()
        tooltip(
            f"\"{label}\": zaktualizowano {len(set(k[0] for k in results))} notatek,"
            f" wygenerowano {len(results)} plików, błędów: {errors}",
            period=10000,
        )

    mw.taskman.run_in_background(bg_task, on_done)


def process_tasks_async(browser, nids: list, tasks: list[dict]):
    """Run multiple TTS tasks as one browser operation with one progress dialog."""
    from aqt.qt import QProgressDialog, Qt
    from ..common import unique

    config = get_tts_config()
    if not validate_config(config):
        return

    voices = unique(config.get("voices", []))
    if not voices:
        return

    jobs = []
    total_items = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        label = task.get("label", "TTS")
        items = _collect_work_items(nids, task, voices)
        if not items:
            continue
        jobs.append((task, label, items))
        total_items += len(items)

    if not jobs:
        tooltip("TTS: brak pól wymagających generowania.")
        return

    mw.checkpoint("TTS Generate All")

    progress = QProgressDialog("TTS: uruchamianie zadań...", "Anuluj", 0, total_items, browser)
    progress.setWindowTitle("TTS")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setValue(0)

    cancel_flag = {"cancelled": False}
    progress.canceled.connect(lambda: cancel_flag.update(cancelled=True))

    def bg_task():
        state = {"done": 0}
        job_results = []
        total_errors = 0
        for task, label, items in jobs:
            if cancel_flag["cancelled"]:
                break
            results, errors = _generate_items(
                items, config, label, cancel_flag, progress, state
            )
            job_results.append((task, items, results))
            total_errors += errors
        return job_results, total_errors, cancel_flag["cancelled"]

    def on_done(fut):
        progress.close()
        try:
            job_results, errors, cancelled = fut.result()
        except Exception as e:
            tooltip(f"TTS: błąd — {e}", period=5000)
            return

        updated_notes = set()
        generated_files = 0
        for task, items, results in job_results:
            _save_batch_results(items, results, task)
            updated_notes.update(k[0] for k in results)
            generated_files += len(results)

        browser.mw.reset()
        parts = [
            f"zaktualizowano {len(updated_notes)} notatek",
            f"wygenerowano {generated_files} plików",
        ]
        if errors:
            parts.append(f"błędy: {errors}")
        if cancelled:
            parts.append("przerwano")
        tooltip("TTS: " + ", ".join(parts), period=10000)

    mw.taskman.run_in_background(bg_task, on_done)


def _generate_items(
    items: list[dict],
    config: dict,
    label: str,
    cancel_flag: dict,
    progress,
    state: dict,
) -> tuple[dict, int]:
    results = {}
    errors = 0

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
            _idx, item = future_map[future]
            try:
                audio_bytes = future.result()
                fname = unique_filename()
                mw.col.media.write_data(fname, audio_bytes)
                key = (item["nid"], item.get("seg_i", -1))
                results[key] = fname
            except Exception as e:
                logger.error(f"TTS error (nid={item['nid']}): {e}")
                errors += 1
            state["done"] += 1
            done = state["done"]
            _update = lambda d=done: (
                progress.setLabelText(f"{label}... {d}/{progress.maximum()}"),
                progress.setValue(d),
            )
            mw.taskman.run_on_main(_update)

    return results, errors


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


def _save_batch_results(items: list, results: dict, task: dict):
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

    work_items = []
    split_contexts = {}  # task_i -> (target_field, split_sep, raw_segments)

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
            note_voices = voices[:]
            random.shuffle(note_voices)
            task_has_items = False
            for seg_i, seg in enumerate(raw_segments):
                if "[sound:" in seg:
                    continue
                text = clean_html(seg)
                if not text:
                    continue
                work_items.append({
                    "task_i": task_i,
                    "mode": "split",
                    "seg_i": seg_i,
                    "text": text,
                    "voice": note_voices[seg_i % len(note_voices)],
                })
                task_has_items = True
            if task_has_items:
                split_contexts[task_i] = (target_field, split_sep, raw_segments)
        else:
            if source_field not in note or target_field not in note:
                continue
            if "[sound:" in note[target_field]:
                continue
            text = clean_html(note[source_field])
            if not text:
                continue
            work_items.append({
                "task_i": task_i,
                "mode": "single",
                "seg_i": -1,
                "text": text,
                "voice": random.choice(voices),
                "target_field": target_field,
            })

    if not work_items:
        return False

    results = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=int(config.get("max_workers", 12))
    ) as pool:
        future_map = {
            pool.submit(generate_audio, item["text"], config, item["voice"]): item
            for item in work_items
        }
        for future in concurrent.futures.as_completed(future_map):
            item = future_map[future]
            try:
                audio_bytes = future.result()
                fname = unique_filename()
                mw.col.media.write_data(fname, audio_bytes)
                results[(item["task_i"], item["seg_i"])] = fname
            except Exception as e:
                logger.error(
                    f"TTS error (nid={note.id}, task={item['task_i']}, seg={item['seg_i']}): {e}"
                )

    if not results:
        return False

    changed = False

    for item in work_items:
        if item["mode"] != "single":
            continue
        fname = results.get((item["task_i"], -1))
        if fname:
            note[item["target_field"]] = f"[sound:{fname}]"
            changed = True

    for task_i, (target_field, split_sep, raw_segments) in split_contexts.items():
        seg_map = {
            seg_i: fname
            for (ti, seg_i), fname in results.items()
            if ti == task_i and seg_i >= 0
        }
        if not seg_map:
            continue
        parts = []
        for i, seg in enumerate(raw_segments):
            content = seg
            if i in seg_map:
                content += f"[sound:{seg_map[i]}]"
            parts.append(content)
        note[target_field] = split_sep.join(parts)
        changed = True

    if changed and note.id:
        mw.col.update_note(note)

    return changed
