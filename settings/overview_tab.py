"""Przegląd — where things are and what is configured; each row opens its page."""
from aqt.qt import QGroupBox, QPushButton, QVBoxLayout, QWidget

from ..common.ui import hint_label, scroll_panel
from ..ai_generator.providers import PROVIDER_LABELS
from .ai_generator_tab import used_providers

WHERE = (
    "• Edytor (Dodaj / Edytuj): przycisk „Toolkit ▾” — sekwencje, AI, wymowa, nagrania.\n"
    "• Przeglądarka kart: prawy klik na zaznaczonych notatkach → „Anki Toolkit”.\n"
    "• Narzędzia → Anki Toolkit: kolejka słówek i operacje na całej kolekcji."
)


def summary(cfg: dict) -> list:
    """(page key, text) rows describing the saved configuration."""
    flows = [w.get("name", "?") for w in cfg.get("workflows") or []
             if isinstance(w, dict) and w.get("steps")]
    note_types = {nt: f for nt, f in ((cfg.get("ai_generator") or {}).get("note_types") or {}).items()
                  if isinstance(f, dict) and f}
    prompts = sum(len(f) for f in note_types.values())
    dicts = [b.get("label", "?") for b in (cfg.get("dictionary") or {}).get("buttons") or []
             if isinstance(b, dict) and b.get("enabled") and b.get("dictionaries")]
    tasks = [t for t in (cfg.get("tts") or {}).get("tasks") or [] if isinstance(t, dict) and t.get("label")]
    providers = [PROVIDER_LABELS.get(p, p) for p in sorted(used_providers(cfg))]
    queue = (cfg.get("word_queue") or {}).get("n8n_url")
    return [
        ("workflows", f"⚙️  Sekwencje: {', '.join(flows) if flows else 'brak'}"),
        ("ai_generator", f"🤖  Prompty AI: {prompts} w typach notatek: {len(note_types)}"),
        ("tts", f"🔊  Nagrania: zadań {len(tasks)}"),
        ("dictionary", f"📖  Wymowa: {', '.join(dicts) if dicts else 'wyłączona'}"),
        ("integrations", f"📚  Kolejka słówek: {'połączona z n8n' if queue else 'nie skonfigurowana'}"),
        ("accounts", f"🔑  Dostawcy AI: {', '.join(providers) if providers else 'brak'}"),
    ]


class OverviewTab(QWidget):
    """Read-only. SettingsDialog sets `go_to(page_key)` to switch pages."""

    def __init__(self, cfg: dict):
        super().__init__()
        self.go_to = lambda _key: None
        layout = scroll_panel(self)
        where = QGroupBox("Gdzie to znajdę")
        QVBoxLayout(where).addWidget(hint_label(WHERE))
        layout.addWidget(where)
        state = QGroupBox("Co jest skonfigurowane (stan z otwarcia okna)")
        rows = QVBoxLayout(state)
        for key, text in summary(cfg):
            button = QPushButton(text)
            button.setFlat(True)
            button.setStyleSheet("text-align: left; padding: 4px;")
            button.setToolTip("Otwórz tę stronę")
            button.clicked.connect(lambda _checked=False, k=key: self.go_to(k))
            rows.addWidget(button)
        layout.addWidget(state)
        layout.addStretch()

    def apply(self, cfg: dict) -> None:
        pass  # nothing to save
