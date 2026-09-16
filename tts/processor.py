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
from aqt.utils import tooltip

from ..common import (
    unique_filename, clean_html, clean_html_normalized, split_separator_regex, unique,
    start_progress, update_progress, finish_progress, strip_sound_tags,
)

from ..common.editor_operation import save_detached_notes, snapshot_fields
from .api import generate_audio
from .config import get_tts_config, validate_config, get_tasks

logger = logging.getLogger(__name__)

_AUDIO_RE = re.compile(r"\[sound:[^\]]*\]")


def has_audio(text: str) -> bool:
    return bool(_AUDIO_RE.search(text or ""))


def audio_tags(text: str) -> list:
    """Every audio tag in the field, in order."""
    return _AUDIO_RE.findall(text or "")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def build_note_work_items(note, tasks: list[dict], voices: list[str],
                          overwrite: bool = False):
    """Collect TTS work items for one note. Never mutates the note.

    Returns (work_items, split_contexts):
      work_items     — [{task_i, mode, seg_i, text, voice[, target_field]}]
      split_contexts — {task_i: {target, sep, segments, mode, eligible,
                                 prev, prev_tags}}

    Modes:
      single      — one audio per note, written to target_field
      split       — split source, audio appended after each segment, written
                    back interleaved (keeps the words)
      split_audio — split source, write ONLY the [sound:...] tags concatenated
                    into a separate target_field (no words)

    overwrite=True regenerates audio that is already there. The old tags are
    only remembered here (`prev`) — nothing is removed from the note until a
    replacement actually exists, so a failed regeneration can't lose audio.
    """
    work_items: list[dict] = []
    split_contexts: dict = {}

    for task_i, task in enumerate(tasks):
        mode = task.get("mode", "single")
        source_field = task.get("source_field", "")
        target_field = task.get("target_field", "")
        split_sep = task.get("split_separator", "<br><br>")

        if mode in ("split", "split_audio"):
            if source_field not in note or target_field not in note:
                continue
            splitter = split_separator_regex(split_sep)
            raw_segments = splitter.split(note[source_field])
            # prev: old audio kept aside so a segment that fails to regenerate
            # keeps what it had (split: keyed by segment index, audio sits in
            # the source). split_audio keeps its old tags in `old`.
            prev: dict = {}
            if overwrite and mode == "split":
                for i, seg in enumerate(raw_segments):
                    tags = "".join(audio_tags(seg))
                    if tags:
                        prev[i] = tags
                raw_segments = [_strip_sound_tags(seg) for seg in raw_segments]
            spoken = [_speech_text(seg) for seg in raw_segments]
            eligible = [i for i, seg in enumerate(raw_segments) if not has_audio(seg) and spoken[i]]
            old: dict = {}
            source_audio: dict = {}
            if mode == "split_audio":
                # Segments that already carry audio in the source are copied
                # into the target in place, so the target stays complete.
                source_audio = {i: audio_tags(seg) for i, seg in enumerate(raw_segments)
                                if spoken[i] and has_audio(seg)}
                old = _old_split_audio(audio_tags(note[target_field]), spoken, source_audio, eligible)
                if not overwrite and eligible and len(old) == len(eligible):
                    continue  # every segment already has its recording
            elif (target_field != source_field and not overwrite
                  and _split_target_complete(splitter.split(note[target_field]), spoken)):
                continue  # separate copy with audio already made
            if not eligible:
                continue
            note_voices = list(voices)
            random.shuffle(note_voices)
            for seg_i in eligible:
                work_items.append({
                    "task_i": task_i,
                    "mode": mode,
                    "seg_i": seg_i,
                    "text": spoken[seg_i],
                    "voice": note_voices[seg_i % len(note_voices)],
                })
            split_contexts[task_i] = {
                "target": target_field, "sep": split_sep, "mode": mode,
                "segments": raw_segments, "eligible": eligible,
                "spoken": [i for i, text in enumerate(spoken) if text],
                "prev": prev, "old": old, "source_audio": source_audio,
                "require_complete": mode == "split" and target_field != source_field
                                    and bool(note[target_field]),
            }
        else:
            if source_field not in note or target_field not in note:
                continue
            if has_audio(note[target_field]) and not overwrite:
                continue
            text = _speech_text(note[source_field])
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

    `results` maps (task_i, seg_i) → media filename. A segment with no result
    keeps whatever audio it had before (split_contexts["prev"]), so a partial
    failure never costs the user existing recordings.
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

    for task_i, ctx in split_contexts.items():
        target_field, mode = ctx["target"], ctx["mode"]
        raw_segments, prev = ctx["segments"], ctx["prev"]
        seg_map = {
            seg_i: fname
            for (ti, seg_i), fname in results.items()
            if ti == task_i and seg_i >= 0
        }
        if not seg_map:
            continue
        if ctx["require_complete"] and any(i not in seg_map for i in ctx["eligible"]):
            continue  # separate old text/audio cannot be safely matched by index
        if mode == "split_audio":
            tags = []
            for i in ctx["spoken"]:
                if i in ctx["source_audio"]:
                    tags += ctx["source_audio"][i]
                elif i in seg_map:
                    tags.append(f"[sound:{seg_map[i]}]")
                elif i in ctx["old"]:
                    tags.append(ctx["old"][i])
                else:
                    break  # no recording for this position: keep the field intact
            else:
                note[target_field] = "".join(tags)
                changed = True
            continue
        parts = []
        for i, seg in enumerate(raw_segments):
            content = seg
            if i in seg_map:
                content += f"[sound:{seg_map[i]}]"
            elif prev.get(i):
                content += prev[i]
            parts.append(content)
        note[target_field] = ctx["sep"].join(parts)
        changed = True

    return changed


def generate_for_items(
    work_items: list[dict],
    config: dict,
    key_fn: Optional[Callable[[dict], tuple]] = None,
    cancel_flag: Optional[dict] = None,
    on_progress: Optional[Callable[[], None]] = None,
    collection=None,
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
    col = collection if collection is not None else mw.col

    results: dict = {}
    errors = 0
    first_error: Optional[str] = None

    def collect(future, item) -> None:
        nonlocal errors, first_error
        try:
            audio_bytes = future.result()
            # Media writes go through the Rust backend (which serializes them),
            # but the collection can be gone if the profile closed mid-batch —
            # fail this item instead of raising AttributeError on None.
            if col is None or mw.col is not col:
                raise RuntimeError("profil Anki został zamknięty w trakcie generowania")
            # write_data may rename on collision — always use the returned name
            fname = col.media.write_data(unique_filename(), audio_bytes)
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
    col = mw.col
    entries = []
    all_items: list[dict] = []
    for nid in nids:
        note = mw.col.get_note(nid)
        items, split_contexts = build_note_work_items(note, tasks, voices)
        if not items:
            continue
        for item in items:
            item["nid"] = nid
        entries.append({"note": note, "items": items, "split_contexts": split_contexts})
        all_items.extend(items)
    before = snapshot_fields(entry["note"] for entry in entries)

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
            collection=col,
        )

    def on_done(fut):
        finish_progress()
        try:
            results, errors, first_error = fut.result()
        except Exception as e:
            tooltip(f"TTS: błąd — {e}", period=5000)
            return

        # Group results per note and apply to the notes the plan was built
        # from; save_detached_notes() then writes them into fresh notes and
        # skips any note whose fields changed meanwhile (stale segments).
        grouped: dict = {}
        for (nid, task_i, seg_i), fname in results.items():
            grouped.setdefault(nid, {})[(task_i, seg_i)] = fname

        changed_notes = []
        for entry in entries:
            note = entry["note"]
            per_note = grouped.get(note.id)
            if per_note and apply_results_to_note(note, entry["items"], entry["split_contexts"], per_note):
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
        save_detached_notes(browser, col, changed_notes, before, summary)

    mw.taskman.run_in_background(bg_task, on_done)


# ---------------------------------------------------------------------------
# Single-note processing (used by the workflow and the editor button)
# ---------------------------------------------------------------------------

def _speech_text(html_text: str) -> str:
    """What the engine reads: visible text without HTML and audio references."""
    return clean_html_normalized(strip_sound_tags(html_text))


def _old_split_audio(tags: list, spoken: list, source_audio: dict, eligible: list) -> dict:
    """Map a split_audio target's existing tags to segment indexes.

    Current layout: one entry per spoken segment, source audio copied in
    place. Older layout: only the generated segments. Anything else has no
    reliable positional mapping.
    """
    if len(tags) == len(eligible):
        return dict(zip(eligible, tags))
    if len(tags) != len(eligible) + sum(len(v) for v in source_audio.values()):
        return {}
    old, position = {}, 0
    for i, text in enumerate(spoken):
        if not text:
            continue
        if i in source_audio:
            position += len(source_audio[i])
        else:
            old[i] = tags[position]
            position += 1
    return old


def _split_target_complete(target_segments: list, spoken: list) -> bool:
    """A separate `split` target that already mirrors the source with audio."""
    texts = [text for text in spoken if text]
    filled = [seg for seg in target_segments if _speech_text(seg)]
    return (len(filled) == len(texts)
            and all(has_audio(seg) for seg in filled)
            and [_speech_text(seg) for seg in filled] == texts)


def _strip_sound_tags(text: str) -> str:
    """Remove audio ([sound:...]) from a copy of the text."""
    return _AUDIO_RE.sub("", text).strip()


def process_single_note(note, config: dict = None,
                        tasks: list = None,
                        overwrite: bool = False) -> tuple[bool, Optional[str]]:
    """Generate audio for one note (parallel).

    Returns (changed, error_message). Mutates the note in memory only —
    the caller decides how to persist (editor save vs. update_note).

    tasks: subset of configured TTS tasks to run (default: all). Each entry
    must be a task dict with at least source_field, target_field, mode.
    overwrite: if True, regenerate audio that is already there. The old tags
    are replaced only where a new file was generated, so a failed request
    never leaves the note without its recording. False = skip filled fields.
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

    work_items, split_contexts = build_note_work_items(
        note, tasks, voices, overwrite=overwrite
    )
    if not work_items:
        return False, None

    logger.debug(
        f"TTS single note: nid={note.id}, {len(work_items)} segmentów, "
        f"max_workers={int(config.get('max_workers', 12))}"
    )

    results, errors, first_error = generate_for_items(
        work_items, config, collection=getattr(note, "_toolkit_collection", None))

    if not results:
        if errors:
            return False, f"nie wygenerowano audio, {errors} błędów ({first_error})"
        return False, None

    changed = apply_results_to_note(note, work_items, split_contexts, results)

    error = None
    if errors:
        error = f"wygenerowano {len(results)}, błędów: {errors} ({first_error})"
    return changed, error
