"""The one settings window: a grouped sidebar over every module's panel.

Each panel takes the full config in `__init__`, writes its own section in
`apply(cfg)` and may veto saving through `validate() -> str | None`. The dialog
wraps every panel in the same page header (title + one-line purpose).
"""
from aqt import mw
from aqt.qt import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSize, QStackedWidget, Qt, QVBoxLayout, QWidget,
)
from aqt.utils import showWarning, tooltip

from .audio_normalizer.settings import AudioNormalizerTab
from .common import get_full_config, save_full_config, set_debug
from .common.ui import hint_label
from .field_hider.settings import FieldHiderTab
from .html_cleanup.settings import HtmlCleanupTab
from .integrations.settings import IntegrationsTab
from .settings.ai_generator_tab import AIGeneratorTab
from .settings.dictionary_tab import DictionaryTab
from .settings.logs_tab import LogsTab
from .settings.narzedzia_tab import FieldSplitterSettings
from .settings.tts_tab import TTSTab
from .settings.workflows_tab import WorkflowsTab
from .workload.settings import WorkloadTab

# (grupa, [(klucz strony, ikona, tytuł, opis, panel)])
PAGES = [
    ("Tworzenie kart", [
        ("workflows", "⚙️", "Workflowy",
         "Nazwane sekwencje kroków AI, słownika, TTS i rozdzielania — w menu PPM i jako przyciski edytora.",
         WorkflowsTab),
        ("ai_generator", "🤖", "AI Generator",
         "Prompty dla pól notatek i dostawcy modeli językowych.", AIGeneratorTab),
        ("tts", "🔊", "TTS", "Nagrania z lokalnego Kokoro albo OpenRouter.", TTSTab),
        ("dictionary", "📖", "Słownik",
         "Wymowa i IPA z Diki, Oxford, Cambridge i Longman.", DictionaryTab),
        ("field_splitter", "✂️", "Rozdzielanie pól",
         "Kopiuje kolejne części pola źródłowego do pól docelowych.", FieldSplitterSettings),
    ]),
    ("Źródła", [
        ("integrations", "📚", "Kolejka słówek",
         "Kolejka z n8n, AI: znaczenia i Web Bridge dla userscriptu słownika.", IntegrationsTab),
    ]),
    ("Nauka", [
        ("workload", "📅", "Plan nauki",
         "Spokojne tempo nowych kart i elastyczny czas nauki.", WorkloadTab),
    ]),
    ("Porządki", [
        ("audio_normalizer", "🎚️", "Normalizacja audio",
         "Wyrównuje głośność plików audio w kolekcji przez ffmpeg.", AudioNormalizerTab),
        ("html_cleanup", "🧹", "Czyszczenie HTML",
         "Reguły „znajdź → zamień” stosowane przy dodawaniu notatek.", HtmlCleanupTab),
        ("field_hider", "👁", "Ukrywanie pól",
         "Pola pomocnicze schowane tylko w oknie „Dodaj”.", FieldHiderTab),
    ]),
    ("Inne", [
        ("logs", "🩺", "Diagnostyka", "Logi wtyczki i tryb debugowania.", LogsTab),
    ]),
]

_SIDEBAR_STYLE = """
QListWidget { border: none; outline: none; padding-top: 6px; }
QListWidget::item { padding: 5px 8px; border-radius: 6px; margin: 1px 6px; }
QListWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }
"""


def _page(icon: str, title: str, description: str, panel: QWidget) -> QWidget:
    """The same header over every panel, so pages read as one window."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    heading = QLabel(f"{icon}  {title}")
    font = heading.font()
    font.setPointSizeF(font.pointSizeF() * 1.45)
    font.setBold(True)
    heading.setFont(font)
    heading.setContentsMargins(12, 6, 12, 0)
    layout.addWidget(heading)
    subtitle = hint_label(description)
    subtitle.setContentsMargins(12, 0, 12, 4)
    layout.addWidget(subtitle)
    layout.addWidget(panel, 1)
    return page


class SettingsDialog(QDialog):
    def __init__(self, page: str | None = None):
        super().__init__(mw)
        self.setWindowTitle("Anki Toolkit — Ustawienia")
        self.resize(1080, 680)
        self.cfg = get_full_config()
        self._orig_debug = bool(self.cfg.get("debug", {}).get("enabled", False))
        self._sidebar = QListWidget()
        self._sidebar.setFixedWidth(200)
        self._sidebar.setStyleSheet(_SIDEBAR_STYLE)
        self._stack = QStackedWidget()
        self._panels = []
        self._rows = {}
        for index, (group, pages) in enumerate(PAGES):
            header = QListWidgetItem(group.upper())
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            font.setPointSizeF(font.pointSizeF() * 0.85)
            header.setFont(font)
            # Odstęp nad każdą grupą poza pierwszą; nagłówki nie są klikalne.
            header.setSizeHint(QSize(0, 22 if index == 0 else 34))
            header.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
            self._sidebar.addItem(header)
            for key, icon, title, description, panel_class in pages:
                panel = panel_class(self.cfg)
                item = QListWidgetItem(f"{icon}  {title}")
                item.setData(Qt.ItemDataRole.UserRole,
                             self._stack.addWidget(_page(icon, title, description, panel)))
                self._sidebar.addItem(item)
                self._rows[key] = self._sidebar.row(item)
                self._panels.append(panel)
        self._sidebar.currentItemChanged.connect(self._show_page)
        self._sidebar.setCurrentRow(self._rows.get(page, self._rows["workflows"]))

        body = QHBoxLayout()
        body.addWidget(self._sidebar)
        body.addWidget(self._stack, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Zapisz")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Anuluj")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_page(self, item, _previous=None):
        if item is not None and item.data(Qt.ItemDataRole.UserRole) is not None:
            self._stack.setCurrentIndex(item.data(Qt.ItemDataRole.UserRole))

    def save(self):
        for panel in self._panels:
            error = panel.validate() if hasattr(panel, "validate") else None
            if error:
                page = self._stack.indexOf(panel.parentWidget())
                self._sidebar.setCurrentRow(next(
                    row for row in range(self._sidebar.count())
                    if self._sidebar.item(row).data(Qt.ItemDataRole.UserRole) == page))
                showWarning(error, parent=self)
                return
        for panel in self._panels:
            panel.apply(self.cfg)
        save_full_config(self.cfg)
        tooltip("Ustawienia Anki Toolkit zapisane.", parent=mw)
        self.accept()

    def reject(self):
        set_debug(self._orig_debug)
        super().reject()


def open_settings(page: str | None = None) -> bool:
    """True, gdy zapisano — wywołujący może wtedy przeliczyć swój widok."""
    return SettingsDialog(page).exec() == QDialog.DialogCode.Accepted
