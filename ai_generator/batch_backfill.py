"""Batch backfill — async, ~50% cheaper bulk generation (Anthropic + OpenAI).

Separate from the synchronous field_generator path. A provider-agnostic core
(field selection, custom_id→field map, persistence, apply) sits over thin
per-provider backends that hide the very different wire protocols:

  * Anthropic — requests inline in the create body; results via results_url.
  * OpenAI    — upload a JSONL input file (Files API), create a batch by
                file id; results downloaded from an output file. One model
                per batch, so OpenAI items are grouped by model.

Both give ~50% off and a 24h window. Other providers don't expose a
compatible batch endpoint, so only anthropic/openai fields are eligible.
This module is pure logic (no aqt); UI actions live in browser_ui.py.

Limitations (v1): no fallback; dependent fields use the note's state at submit
time (batch parents first, apply, then children); results are written only
into fields that are still empty.
"""

import json
import logging
import os
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from ..common import clean_html_normalized, safe_str
from . import stats
# Keep these orchestration seams module-level and call them unqualified below:
# tests patch batch_backfill._submit_* / _poll_* without reaching into backends.
from .batch_anthropic import first_text as _first_text
from .batch_anthropic import poll_batch as _anthropic_poll_batch
from .batch_anthropic import submit_batch as _anthropic_submit_batch
from .batch_openai import cleanup_files as _cleanup_openai_files
from .batch_openai import poll_batch as _openai_poll_batch
from .batch_openai import submit_batch as _openai_submit_batch
from .field_generator import iter_note_fields
from .template_engine import render_template

logger = logging.getLogger(__name__)

_ELIGIBLE_PROVIDERS = ("anthropic", "openai")

# OpenAI enqueues (input + reserved output) tokens from every pending batch
# against an org-wide cap (2M on lower tiers). One giant batch blows that cap and
# gets rejected/failed, so we split a model's items into chunks under a token
# budget and submit them sequentially, stopping the moment the cap is hit. The
# un-sent fields stay empty, so re-running the same action after the queue drains
# re-picks exactly them — no deferred queue needed.
_OPENAI_TOKEN_BUDGET = 1_500_000   # per batch; stays under the common 2M org cap
_OPENAI_OUTPUT_RESERVE = 1000      # est. output tokens counted toward the cap
_ENQUEUED_LIMIT_HINT = "enqueued"  # substring of OpenAI's "Enqueued token limit" error

# OpenAI's enqueued-token counter can stay stuck for hours after a wave of
# failed/completed batches (observed 2026-07-04: every create 400'd for 2h+
# with nothing visibly enqueued). While it's stuck every create fails, so after
# one enqueued-limit rejection we stop trying for a while instead of uploading
# a fresh input file every poll tick.
_OPENAI_BACKOFF_S = 30 * 60
_openai_blocked_until = 0.0


def _est_tokens(prompt: str, reserve: int) -> int:
    # ponytail: len//4 is the standard rough token heuristic; exact counting
    # needs tiktoken (a dep) for no real gain — we only need chunk sizing.
    return len(prompt) // 4 + reserve


def _chunk_by_tokens(items, budget: int, reserve: int) -> list:
    """Split items into sublists each under `budget` estimated tokens (min 1/chunk)."""
    chunks: list = []
    cur: list = []
    cur_tok = 0
    for it in items:
        t = _est_tokens(it["prompt"], reserve)
        if cur and cur_tok + t > budget:
            chunks.append(cur)
            cur, cur_tok = [], 0
        cur.append(it)
        cur_tok += t
    if cur:
        chunks.append(cur)
    return chunks

_USER_FILES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_files")
_PATH = os.path.join(_USER_FILES, "ai_batches.json")
_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Persistence — survives Anki restart (user_files/ is kept across updates)
# --------------------------------------------------------------------------

def _load_store() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("batches"), list):
            return data
    except (FileNotFoundError, ValueError, OSError):
        pass
    return {"batches": []}


def _save_store(store: dict) -> None:
    os.makedirs(_USER_FILES, exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)


def _append_record(record: dict) -> None:
    with _LOCK:
        store = _load_store()
        store["batches"].append(record)
        _save_store(store)


def pending_batches() -> list:
    return [b for b in _load_store()["batches"] if b.get("status") == "in_progress"]


def _pending_openai_tokens() -> int:
    """Estimated tokens our own still-running OpenAI batches already enqueue.

    Subtracted from the per-run budget so a re-run while an earlier batch is
    in progress doesn't push the org over its enqueued-token cap again."""
    return sum(int(b.get("enq_tokens") or 0)
               for b in pending_batches() if b.get("provider") == "openai")


def openai_budget_left(config: dict) -> int:
    """Estimated enqueued-token budget still available for new OpenAI batches.

    0 while backing off after an enqueued-limit rejection — callers can skip
    building items entirely instead of submitting into a full queue."""
    if time.time() < _openai_blocked_until:
        return 0
    budget = int(config.get("openai_batch_token_budget") or _OPENAI_TOKEN_BUDGET)
    return max(0, budget - _pending_openai_tokens())


def est_item_tokens(item: dict, config: dict) -> int:
    """Estimated enqueued tokens for one built item (prompt + output reserve)."""
    reserve = int(config.get("openai_batch_output_reserve") or _OPENAI_OUTPUT_RESERVE)
    return _est_tokens(item["prompt"], reserve)


def inflight_fields() -> set:
    """{(nid, field)} currently sitting in a pending batch — must not be re-sent."""
    out: set = set()
    for b in pending_batches():
        for meta in (b.get("map") or {}).values():
            out.add((meta.get("nid"), meta.get("field")))
    return out


# --------------------------------------------------------------------------
# Backfill jobs — remember a selection so deferred slices auto-submit over time
# --------------------------------------------------------------------------

def add_job(nids, only_fields, total: int = 0, sent: int = 0) -> str:
    """Persist a resumable backfill job (the selected notes + optional field
    filter). The auto-poll cycle drains it slice by slice until every field is
    filled, staying under the OpenAI enqueued-token budget each round.

    total/sent (request counts) drive the progress shown in tooltips."""
    with _LOCK:
        store = _load_store()
        job_id = "job-" + uuid.uuid4().hex[:12]
        store.setdefault("jobs", []).append({
            "id": job_id,
            "nids": [int(n) for n in nids],
            "only_fields": sorted(only_fields) if only_fields else None,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "active",
            "total": int(total),
            "sent": int(sent),
        })
        _save_store(store)
    return job_id


def record_job_progress(records) -> Optional[str]:
    """Bump active jobs' sent counters by the requests just submitted (matched
    by nid) and return a human progress string like '2 874/19 140 zapytań (15%)',
    or None when no job tracks a total (legacy jobs)."""
    per_nid = Counter(m.get("nid") for r in records for m in (r.get("map") or {}).values())
    with _LOCK:
        store = _load_store()
        jobs = [j for j in store.get("jobs", []) if j.get("status") == "active"]
        for job in jobs:
            nids = set(job.get("nids", []))
            mine = sum(c for nid, c in per_nid.items() if nid in nids)
            if mine:
                job["sent"] = int(job.get("sent") or 0) + mine
                # a nid can sit in overlapping jobs — credit the first one only
                for nid in list(per_nid):
                    if nid in nids:
                        del per_nid[nid]
        _save_store(store)
    tracked = [j for j in jobs if int(j.get("total") or 0) > 0]
    if not tracked:
        return None
    total = sum(int(j["total"]) for j in tracked)
    sent = min(sum(int(j.get("sent") or 0) for j in tracked), total)
    return f"{sent:,}/{total:,} zapytań ({100 * sent // total}%)".replace(",", " ")


def active_jobs() -> list:
    return [j for j in _load_store().get("jobs", []) if j.get("status") == "active"]


# ponytail: a field the model keeps returning empty stays empty and would be
# re-sent every poll forever — cap a job at the 24h batch window instead of
# tracking per-field retries. Straggler fields left after that → manual re-run.
_JOB_MAX_AGE_H = 24


def job_expired(job: dict) -> bool:
    try:
        created = datetime.strptime(job.get("created_at", ""), "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return datetime.now() - created > timedelta(hours=_JOB_MAX_AGE_H)


def finish_job(job_id: str) -> None:
    with _LOCK:
        store = _load_store()
        for j in store.get("jobs", []):
            if j.get("id") == job_id:
                j["status"] = "done"
        _save_store(store)


# --------------------------------------------------------------------------
# Building items (provider-agnostic)
# --------------------------------------------------------------------------

def build_items(notes, config: dict, only_fields=None) -> tuple:
    """Return (items, skipped) for a batch backfill.

    items: [{custom_id, provider, model, prompt, nid, field, temperature}] —
    one per empty, eligible field. custom_id is unique across the whole submit.
    skipped: eligible fields whose provider isn't anthropic/openai, or that
    have no resolvable model.

    only_fields: restrict to those target field names; None = all empty
    non-manual fields (same selection as the sync auto batch).
    """
    providers = config.get("providers", {})
    defaults = {
        p: safe_str((providers.get(p) or {}).get("model"))
        for p in _ELIGIBLE_PROVIDERS
    }
    items: list = []
    skipped = 0
    idx = 0
    for note in notes:
        fields_map = None
        for field_cfg, target_field in iter_note_fields(note, config, only_fields=only_fields):
            provider = safe_str(field_cfg.get("provider"))
            if provider not in _ELIGIBLE_PROVIDERS:
                skipped += 1
                continue
            model = safe_str(field_cfg.get("model")) or defaults.get(provider, "")
            if not model:
                skipped += 1
                continue
            if fields_map is None:
                fields_map = {fld: clean_html_normalized(note[fld]) for fld in note.keys()}
            temperature = field_cfg.get("temperature")
            if not isinstance(temperature, (int, float)):
                temperature = None
            items.append({
                "custom_id": f"i{idx}",
                "provider": provider,
                "model": model,
                "prompt": render_template(safe_str(field_cfg.get("prompt", "")), fields_map),
                "nid": note.id,
                "field": target_field,
                "temperature": temperature,
            })
            idx += 1
    return items, skipped


def summarize(items) -> str:
    """Human-readable 'anthropic/model: n; openai/model: n' for the confirm dialog."""
    combos = Counter((i["provider"], i["model"]) for i in items)
    return "; ".join(f"{p}/{m}: {c}" for (p, m), c in sorted(combos.items()))


def _record_map(items) -> dict:
    return {i["custom_id"]: {"nid": i["nid"], "field": i["field"], "model": i["model"]}
            for i in items}


def _new_record(batch_id: str, provider: str, items) -> dict:
    return {
        "id": batch_id,
        "provider": provider,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(items),
        "status": "in_progress",
        "map": _record_map(items),
    }


# --------------------------------------------------------------------------
# Submit — dispatch to per-provider backends, one record per API batch
# --------------------------------------------------------------------------

def submit(items, config: dict) -> tuple:
    """Create batches for all items. Returns (records, errors).

    Anthropic items go into one batch; OpenAI items are grouped by model (the
    API requires a single model per batch). Each created batch is persisted.
    """
    records: list = []
    errors: list = []

    anthropic_items = [i for i in items if i["provider"] == "anthropic"]
    if anthropic_items:
        rec, err = _submit_anthropic(anthropic_items, config)
        if rec:
            _append_record(rec)
            records.append(rec)
        else:
            errors.append(f"Anthropic: {err}")

    budget = int(config.get("openai_batch_token_budget") or _OPENAI_TOKEN_BUDGET)
    reserve = int(config.get("openai_batch_output_reserve") or _OPENAI_OUTPUT_RESERVE)
    by_model = defaultdict(list)
    for i in items:
        if i["provider"] == "openai":
            by_model[i["model"]].append(i)
    # OpenAI accepts every create() then FAILS batches asynchronously once the
    # org's enqueued-token cap is exceeded — so throttling on the create error
    # is useless. Instead cap the *total* estimated tokens in flight (our own
    # still-running batches + what we send now) to `budget` (< the 2M org cap)
    # and defer the rest; re-running the same action after the queue drains
    # picks up the still-empty fields.
    global _openai_blocked_until
    already = _pending_openai_tokens()
    running = 0
    deferred = 0
    # After ANY failed create the next chunk would fail the same way, and each
    # attempt wastes a full input-file upload — one failure stops this run
    # (the 1-min poll cycle is the retry).
    blocked = time.time() < _openai_blocked_until
    for model, group in by_model.items():
        for chunk in _chunk_by_tokens(group, budget, reserve):
            chunk_tok = sum(_est_tokens(i["prompt"], reserve) for i in chunk)
            # Send this chunk unless it would push total in-flight over budget —
            # but always let one chunk through when nothing is enqueued at all,
            # so a single over-budget item can never wedge the queue forever.
            if blocked or (already + running + chunk_tok > budget and (already or running)):
                deferred += len(chunk)
                continue
            rec, err = _submit_openai(chunk, config)
            if rec:
                rec["enq_tokens"] = chunk_tok
                _append_record(rec)
                records.append(rec)
                running += chunk_tok
            elif err and _ENQUEUED_LIMIT_HINT in err.lower():
                # Org queue full (or OpenAI's counter stuck) — back off so the
                # auto-cycle doesn't upload a file every tick just to get 400'd.
                _openai_blocked_until = time.time() + _OPENAI_BACKOFF_S
                blocked = True
                deferred += len(chunk)
                errors.append(
                    f"OpenAI: limit kolejki tokenów org — wstrzymuję wysyłkę na "
                    f"{_OPENAI_BACKOFF_S // 60} min ({err})"
                )
            else:
                blocked = True
                errors.append(f"OpenAI ({model}): {err}")
    if deferred:
        errors.append(
            f"OpenAI: limit kolejki tokenów org (~2M) — w locie ~{already + running:,} "
            f"tok., odłożono {deferred} zapytań. Gdy bieżące batche się skończą "
            f"(„Sprawdź batche” lub restart Anki), wyślij ten sam batch ponownie — "
            f"dobierze tylko wciąż puste pola."
        )

    return records, errors


def _submit_anthropic(items, config: dict) -> tuple:
    batch_id, err = _anthropic_submit_batch(items, config)
    if not batch_id:
        return None, err
    return _new_record(batch_id, "anthropic", items), None


def _poll_anthropic(record: dict, config: dict) -> tuple:
    return _anthropic_poll_batch(record, config)


def _submit_openai(items, config: dict) -> tuple:
    metadata, err = _openai_submit_batch(items, config)
    if not metadata:
        return None, err
    record = _new_record(metadata["id"], "openai", items)
    record["input_file_id"] = metadata["input_file_id"]
    return record, None


def _poll_openai(record: dict, config: dict) -> tuple:
    return _openai_poll_batch(record, config)


_POLLERS = {"anthropic": _poll_anthropic, "openai": _poll_openai}


# --------------------------------------------------------------------------
# Poll & apply (provider-agnostic — results are normalized)
# --------------------------------------------------------------------------

def poll_results(config: dict) -> tuple:
    """Network-only (safe in a background thread). Returns (ended, still, errors):

      ended  = {batch_id: {"record": rec, "results": [normalized, ...]}}
      still  = count of batches still in progress
      errors = ids whose status/results couldn't be fetched
    A normalized result: {custom_id, ok: bool, text, in_tok, out_tok}.
    """
    ended: dict = {}
    still = 0
    errors: list = []
    for rec in pending_batches():
        poller = _POLLERS.get(rec.get("provider", "anthropic"))
        if poller is None:
            status, results = "error", None
        else:
            status, results = poller(rec, config)
        if status == "ended":
            ended[rec["id"]] = {"record": rec, "results": results or []}
            logger.info(
                f"Batch {rec.get('provider', 'anthropic')} zakończony: {rec['id']} "
                f"({len(results or [])} wyników z {rec.get('count', '?')} zapytań)"
            )
        elif status == "pending":
            still += 1
        elif _batch_expired(rec):
            # Trwale nieodpytywalny (np. 404 po retencji wyników) — bez tego
            # wisiałby w in_progress na zawsze i inflight_fields() blokowałoby
            # jego pola dla wszystkich przyszłych batchy.
            _set_status([rec["id"]], "expired")
            logger.warning(f"Batch {rec['id']}: błąd odpytania od >{_BATCH_MAX_AGE_D} dni — porzucam")
        else:
            errors.append(rec["id"])
    return ended, still, errors


# Anthropic trzyma wyniki 29 dni, batche OpenAI kończą się w 24h — błąd
# odpytania utrzymujący się tydzień od utworzenia nie jest przejściowy.
_BATCH_MAX_AGE_D = 7


def _batch_expired(rec: dict) -> bool:
    try:
        created = datetime.strptime(rec.get("created_at", ""), "%Y-%m-%d %H:%M")
    except ValueError:
        return True  # brak/zepsuta data — i tak nigdy się nie odblokuje
    return datetime.now() - created > timedelta(days=_BATCH_MAX_AGE_D)


def cleanup_openai_files(records, config: dict) -> None:
    """Delete a finished batch's input/output files from OpenAI storage
    (network-only — run in a background task, AFTER the results are committed).
    Old records without input_file_id are skipped silently."""
    _cleanup_openai_files(records, config)


def _set_status(batch_ids, status: str) -> None:
    with _LOCK:
        store = _load_store()
        ids = set(batch_ids)
        for b in store["batches"]:
            if b.get("id") in ids:
                b["status"] = status
        _save_store(store)


def mark_applied(batch_ids) -> None:
    """Persist 'applied' status. Call AFTER the note changes are committed —
    marking earlier would lose the results if Anki dies before the commit
    (the batch would never be polled again). Re-applying after a crash is
    idempotent (only still-empty fields are written); stats may double-count."""
    _set_status(batch_ids, "applied")


def apply_results(col, ended: dict) -> dict:
    """Apply ended batches to the collection (MAIN THREAD — touches col).

    Writes a result only into a field that is still empty, so it never
    overwrites edits made between submit and now. custom_ids present in the
    record map but missing from the results (e.g. OpenAI expired requests) are
    counted as failures. Returns a summary with the mutated Note objects.
    Does NOT mark batches applied — the caller does that via mark_applied()
    once the notes are committed.
    """
    note_cache: dict = {}
    changed_nids: set = set()
    filled = failed = skipped = 0

    def get_note(nid):
        if nid not in note_cache:
            try:
                note_cache[nid] = col.get_note(nid)
            except Exception:
                note_cache[nid] = None
        return note_cache[nid]

    for bid, payload in ended.items():
        rec = payload["record"]
        provider = rec.get("provider", "anthropic")
        imap = rec.get("map", {})
        seen: set = set()
        for r in payload["results"]:
            cid = r.get("custom_id")
            meta = imap.get(cid)
            if not meta:
                continue
            seen.add(cid)
            model = meta.get("model", "")
            in_tok = int(r.get("in_tok") or 0)
            out_tok = int(r.get("out_tok") or 0)
            text = r.get("text")
            if not r.get("ok") or not text:
                failed += 1
                stats.record_request(provider, model, in_tok, out_tok,
                                     error=True, field_generated=False)
                continue
            note = get_note(meta.get("nid"))
            field = meta.get("field", "")
            if note is None or field not in note or note[field].strip():
                skipped += 1
                stats.record_request(provider, model, in_tok, out_tok,
                                     error=False, field_generated=False)
                continue
            note[field] = text.strip()
            changed_nids.add(note.id)
            filled += 1
            stats.record_request(provider, model, in_tok, out_tok,
                                 error=False, field_generated=True)
        # leftover map entries with no result → failures
        for cid, meta in imap.items():
            if cid not in seen:
                failed += 1
                stats.record_request(provider, meta.get("model", ""), 0, 0,
                                     error=True, field_generated=False)

    changed_notes = [note_cache[nid] for nid in changed_nids if note_cache.get(nid)]
    return {"changed_notes": changed_notes,
            "filled": filled, "failed": failed, "skipped": skipped}
