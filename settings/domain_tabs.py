"""Composite settings pages organised around user tasks, not code modules."""

from pathlib import Path

from aqt.qt import QWidget, QVBoxLayout, QTabWidget, QLabel

from .audio_normalizer_tab import AudioNormalizerTab
from .deck_router_tab import DeckRouterTab
from .dictionary_tab import DictionaryTab
from .field_hider_tab import FieldHiderTab
from .logs_tab import LogsTab
from .narzedzia_tab import (
    AudioEmbedSettings, FieldSplitterSettings, FilteredDeckSettings,
    HtmlCleanupSettings, LearningRulesSettings,
)
from .stats_tab import StatsTab
from .tts_tab import TTSTab
from .word_queue_tab import WordQueueTab
from .workflows_tab import WorkflowsTab


class DomainTabs(QWidget):
    """A tabbed page that delegates configuration writes to its child panels."""

    def __init__(self, panels: list[tuple[str, QWidget]]):
        super().__init__()
        self._panels = panels
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        for title, panel in panels:
            tabs.addTab(panel, title)
        layout.addWidget(tabs)

    def apply(self, cfg: dict) -> None:
        for _title, panel in self._panels:
            apply = getattr(panel, "apply", None)
            if apply is not None:
                apply(cfg)


def workflows_page(cfg: dict) -> DomainTabs:
    return DomainTabs([
        ("Workflowy", WorkflowsTab(cfg)),
        ("Rozdzielanie pól", FieldSplitterSettings(cfg)),
    ])


def pronunciation_page(cfg: dict) -> DomainTabs:
    return DomainTabs([
        ("TTS", TTSTab(cfg)),
        ("Słownik", DictionaryTab(cfg)),
    ])


def learning_page(cfg: dict) -> DomainTabs:
    return DomainTabs([
        ("Odblokowywanie", LearningRulesSettings(cfg)),
        ("Kierowanie do talii", DeckRouterTab(cfg)),
        ("Presety powtórek", FilteredDeckSettings(cfg)),
    ])


class WebBridgeInfo(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        text = QLabel(
            "Web Bridge uruchamia lokalny mostek HTTP na 127.0.0.1:8766. "
            "Włącza się go w zakładce Moduły. Userscript znajduje się w:\n\n"
            f"{Path(__file__).parent.parent / 'web_bridge' / 'dictionaries-to-anki.user.js'}"
        )
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch()

    def apply(self, cfg: dict) -> None:
        return


def integrations_page(cfg: dict) -> DomainTabs:
    return DomainTabs([
        ("Kolejka słówek", WordQueueTab(cfg)),
        ("Web Bridge", WebBridgeInfo()),
    ])


def maintenance_page(cfg: dict) -> DomainTabs:
    return DomainTabs([
        ("Normalizacja audio", AudioNormalizerTab(cfg)),
        ("Osadzanie audio", AudioEmbedSettings(cfg)),
        ("Czyszczenie HTML", HtmlCleanupSettings(cfg)),
        ("Ukrywanie pól", FieldHiderTab(cfg)),
    ])


def diagnostics_page(cfg: dict) -> DomainTabs:
    return DomainTabs([
        ("Statystyki", StatsTab(cfg)),
        ("Logi", LogsTab(cfg)),
    ])
