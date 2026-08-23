"""TTS note processing — single-note and batch operations.

Shared building blocks (used by the editor button, the browser batch and the
workflow):
  build_note_work_items() — collect (task, segment) work items for one note
  generate_for_items()    — parallel audio generation + media writes
  apply_results_to_note() — write [sound:...] tags back into note fields
"""

import concurrent.futures
import logging
import random
import re
from typing import Callable, Optional

from aqt import mw
from aqt.operations import CollectionOp
from aqt.utils import tooltip

from ..common import (
    unique_filename, clean_html, split_separator_regex, unique,
    start_progress, update_progress, finish_progress,
)

from .api import generate_audio
from .config import get_tts_config, validate_config, get_tasks

logger = logging.getLogger(__name__)

# Audio in a field is either the raw Anki tag or an <audio> player left by
# audio_embed — both mean "already generated".
_AUDIO_RE = re.compile(r"\[sound:[^\]]*\]|<audio\b[^>]*>.*?</audio>", re.I | re.S)


def has_audio(text: str) -> bool:
    return bool(_AUDIO_RE.search(text or ""))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def build_note_work_items(note, tasks: list[dict], voices: list[str]):
    """Collect TTS work items for one note.

    Returns (work_items, split_contexts):
      work_items     — [{task_i, mode, seg_i, text, voice[, target_field]}]
      split_contexts — {task_i: (target_field, split_sep, raw_segments, mode)}

    Modes:
      single      — one audio per note, written to target_field
      split       — split source, audio appended after each segment, written
                    back interleaved (keeps the words)
      split_audio — split source, write ONLY the [sound:...] tags concatenated
                    into a separate target_field (no words)
    """
    work_items: list[dict] = []
    split_contexts: dict = {}

    for task_i, task in enumerate(tasks):
        mode = task.get("mode", "single")
        source_field = task.get("source_field", "")
        target_field = task.get("target_field", "")
        split_sep = task.get("split_separator", "<br><br>")

        if mode in ("split", "split_audio"):
            if source_field not in note:
                continue
            # split_audio writes to a separate field — skip if it already has
            # audio (regen strips it first via overwrite).
            if mode == "split_audio" and (
                target_field not in note or has_audio(note[target_field])
            ):
                continue
            raw_segments = split_separator_regex(split_sep).split(note[source_field])
            note_voices = list(voices)
            random.shuffle(note_voices)
            task_has_items = False
            for seg_i, seg in enumerate(raw_segments):
                if has_audio(seg):
                    continue
                text = clean_html(seg)
                if not text:
                    continue
                work_items.append({
                    "task_i": task_i,
                    "mode": mode,
                    "seg_i": seg_i,
                    "text": text,
                    "voice": note_voices[seg_i % len(note_voices)],
                })
                task_has_items = True
            if task_has_items:
                split_contexts[task_i] = (target_field, split_sep, raw_segments, mode)
        else:
            if source_field not in note or target_field not in note:
                continue
            if has_audio(note[target_field]):
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

    return work_items, split_contexts


def apply_results_to_note(note, work_items: list[dict], split_contexts: dict,
                          results: dict) -> bool:
    """Write generated audio into note fields (in memory — no collection save).

    `results` maps (task_i, seg_i) → media filename.
    Returns True if any field changed.
    """
    changed = False

    for item in work_items:
        if item["mode"] != "single":
            continue
        fname = results.get((item["task_i"], -1))
        if fname:
            note[item["target_field"]] = f"[sound:{fname}]"
            changed = True

    for task_i, (target_field, split_sep, raw_segments, mode) in split_contexts.items():
        seg_map = {
            seg_i: fname
            for (ti, seg_i), fname in results.items()
            if ti == task_i and seg_i >= 0
        }
        if not seg_map:
            continue
        if mode == "split_audio":
            note[target_field] = "".join(
                f"[sound:{seg_map[i]}]" for i in sorted(seg_map)
            )
            changed = True
            continue
        parts = []
        for i, seg in enumerate(raw_segments):
            content = seg
            if i in seg_map:
                content += f"[sound:{seg_map[i]}]"
            parts.append(content)
        note[target_field] = split_sep.join(parts)
        changed = True

    return changed


def generate_for_items(
    work_items: list[dict],
    config: dict,
    key_fn: Optional[Callable[[dict], tuple]] = None,
    cancel_flag: Optional[dict] = None,
    on_progress: Optional[Callable[[], None]] = None,
) -> tuple[dict, int, Optional[str]]:
    """Generate audio for work items in parallel and write media files.

    Returns (results, errors, first_error) where results maps
    key_fn(item) → media filename (default key: (task_i, seg_i)).

    Cancelling (cancel_flag["cancelled"] = True) cancels requests that have
    not started yet; requests already running finish and their results are
    still collected — the audio is paid for either way.
    """
    if key_fn is None:
        key_fn = lambda item: (item["task_i"], item["seg_i"])

    results: dict = {}
    errors = 0
    first_error: Optional[str] = None

    def collect(future, item) -> None:
        nonlocal errors, first_error
        try:
            audio_bytes = future.result()
            # write_data may rename on collision — always use the returned name
            fname = mw.col.media.write_data(unique_filename(), audio_bytes)
            results[key_fn(item)] = fname
        except Exception as e:
            errors += 1
            if first_error is None:
                first_error = str(e)
            logger.error(f"TTS error ({item['text'][:40]!r}): {e}")

    cancelled_early = False
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=int(config.get("max_workers", 12))
    ) as pool:
        future_map = {
            pool.submit(generate_audio, item["text"], config, item["voice"]): item
            for item in work_items
        }
        for future in concurrent.futures.as_completed(future_map):
            if cancel_flag is not None and cancel_flag.get("cancelled"):
                cancelled_early = True
                pool.shutdown(wait=False, cancel_futures=True)
                break
            collect(future, future_map[future])
            if on_progress:
                on_progress()
    # Leaving the `with` block waited for the requests that were already
    # running when we cancelled — collect their results too.
    if cancelled_early:
        for future, item in future_map.items():
            if future.cancelled() or not future.done():
                continue
            if key_fn(item) in results:
                continue
            collect(future, item)

    return results, errors, first_error


# ---------------------------------------------------------------------------
# Async batch processing (natywny pasek mw.progress + cancel + single-undo save)
# ---------------------------------------------------------------------------

def process_task_async(browser, nids: list, task: dict):
    _process_batch_async(browser, nids, [task], label=task.get("label", "TTS"))


def process_tasks_async(browser, nids: list, tasks: list[dict]):
    """Run multiple TTS tasks as one browser operation with one progress dialog."""
    _process_batch_async(browser, nids, tasks, label="TTS")


def _process_batch_async(browser, nids: list, tasks: list[dict], label: str):
    config = get_tts_config()
    if not validate_config(config):
        return

    voices = unique(config.get("voices", []))
    if not voices:
        return

    # Collect everything up front (main thread): one entry per note.
    entries = []
    all_items: list[dict] = []
    for nid in nids:
        note = mw.col.get_note(nid)
        items, split_contexts = build_note_work_items(note, tasks, voices)
        if not items:
            continue
        for item in items:
            item["nid"] = nid
        entries.append({"nid": nid, "items": items, "split_contexts": split_contexts})
        all_items.extend(items)

    if not all_items:
        tooltip(f"\"{label}\": brak pól wymagających generowania.")
        return

    cancel_flag = start_progress(label, len(all_items), "TTS")

    state = {"done": 0}

    def on_progress():
        state["done"] += 1
        update_progress(cancel_flag, label, state["done"], len(all_items))

    def bg_task():
        return generate_for_items(
            all_items, config,
            key_fn=lambda item: (item["nid"], item["task_i"], item["seg_i"]),
            cancel_flag=cancel_flag,
            on_progress=on_progress,
        )

    def on_done(fut):
        finish_progress()
        try:
            results, errors, first_error = fut.result()
        except Exception as e:
            tooltip(f"TTS: błąd — {e}", period=5000)
            return

        # Group results per note and apply (main thread, fresh note objects).
        grouped: dict = {}
        for (nid, task_i, seg_i), fname in results.items():
            grouped.setdefault(nid, {})[(task_i, seg_i)] = fname

        changed_notes = []
        for entry in entries:
            per_note = grouped.get(entry["nid"])
            if not per_note:
                continue
            note = mw.col.get_note(entry["nid"])
            if apply_results_to_note(note, entry["items"], entry["split_contexts"], per_note):
                changed_notes.append(note)

        parts = [
            f"zaktualizowano {len(changed_notes)} notatek",
            f"wygenerowano {len(results)} plików",
        ]
        if errors:
            parts.append(f"błędy: {errors}" + (f" ({first_error})" if first_error else ""))
        if cancel_flag["cancelled"]:
            parts.append("przerwano")
        summary = f"\"{label}\": " + ", ".join(parts)

        logger.info(f"TTS batch {summary}")

        if not changed_notes:
            tooltip(summary, period=8000)
            return

        def _saved(_changes):
            tooltip(summary, period=10000)

        CollectionOp(
            parent=browser,
            op=lambda col: col.update_notes(changed_notes),
        ).success(_saved).run_in_background()

    mw.taskman.run_in_background(bg_task, on_done)


# ---------------------------------------------------------------------------
# Single-note processing (used by the workflow and the editor button)
# ---------------------------------------------------------------------------

def _strip_sound_tags(text: str) -> str:
    """Remove audio ([sound:...] or <audio>) so regeneration can replace it."""
    return _AUDIO_RE.sub("", text).strip()


def process_single_note(note, config: dict = None,
                        tasks: list = None,
                        overwrite: bool = False) -> tuple[bool, Optional[str]]:
    """Generate audio for one note (parallel).

    Returns (changed, error_message). Mutates the note in memory only —
    the caller decides how to persist (editor save vs. update_note).

    tasks: subset of configured TTS tasks to run (default: all). Each entry
    must be a task dict with at least source_field, target_field, mode.
    overwrite: if True, strip [sound:...] from target fields before
    generating so existing audio is replaced. False = skip filled (today).
    """
    if config is None:
        config = get_tts_config()
    if not validate_config(config):
        return False, None

    if tasks is None:
        tasks = get_tasks(config)
    if not tasks:
        return False, None

    voices = unique(config.get("voices", []))
    if not voices:
        return False, None

    if overwrite:
        for task in tasks:
            target = task.get("target_field", "")
            if target and target in note:
                note[target] = _strip_sound_tags(note[target])

    work_items, split_contexts = build_note_work_items(note, tasks, voices)
    if not work_items:
        return False, None

    logger.debug(
        f"TTS single note: nid={note.id}, {len(work_items)} segmentów, "
        f"max_workers={int(config.get('max_workers', 12))}"
    )

    results, errors, first_error = generate_for_items(work_items, config)

    if not results:
        if errors:
            return False, f"nie wygenerowano audio, {errors} błędów ({first_error})"
        return False, None

    changed = apply_results_to_note(note, work_items, split_contexts, results)

    error = None
    if errors:
        error = f"wygenerowano {len(results)}, błędów: {errors} ({first_error})"
    return changed, error
