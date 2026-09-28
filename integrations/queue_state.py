"""Per-profile/table scratch file. Main thread only; no credentials stored.

- drafts: AI proposals not yet saved as cards (a second model call costs money),
- owed: row id → word whose cards exist, but whose n8n "done" PATCH has not succeeded.

ponytail: no Undo tracking. Undoing an AI batch leaves the n8n row marked done;
untick it by hand. Add GUID receipts only if that turns out to matter.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile

log = logging.getLogger(__name__)


class QueueState:
    def __init__(self, collection_path, cfg, directory=None, path=None):
        scope = [str(Path(collection_path).resolve()), cfg.get("n8n_url", "").rstrip("/"),
                 cfg.get("table_id", ""), cfg.get("word_column", ""), cfg.get("flag_column", "")]
        key = hashlib.sha256(json.dumps(scope).encode()).hexdigest()[:24]
        self.path = Path(path) if path else (
            Path(directory or Path(__file__).resolve().parent.parent / "user_files") / f"word_queue_{key}.json")
        self.data = {"drafts": [], "owed": {}}
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or any(not isinstance(data.get(k, v), type(v))
                                                 for k, v in self.data.items()):
                raise ValueError("unexpected structure")
        except (OSError, ValueError):
            # A broken scratch file must never keep the panel from opening.
            log.exception("word_queue: uszkodzony plik stanu, zaczynam od zera: %s", self.path)
            try:
                os.replace(self.path, self.path.with_suffix(".broken"))
            except OSError:
                pass
            return
        self.data.update({k: data.get(k, v) for k, v in self.data.items()})

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def drop_drafts(self, row_ids):
        self.data["drafts"] = [p for p in self.data["drafts"] if p["row_id"] not in row_ids]
