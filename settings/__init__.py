"""Settings dialog for Anki Toolkit — unified configuration UI."""

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox,
    QListWidget, QListWidgetItem, QStackedWidget, QColor, Qt,
)
from aqt.utils import tooltip
from aqt.utils import showWarning

from ..common import ADDON_NAME, get_full_config, save_full_config, set_debug
from ..common.ui import hint_label

from .status_tab import StatusTab
from .modules_tab import ModulesTab
from .dictionary_tab import DictionaryTab
from .ai_generator_tab import AIGeneratorTab
from .workflows_tab import WorkflowsTab
from .tts_tab import TTSTab
from .audio_normalizer_tab import AudioNormalizerTab
from .narzedzia_tab import NarzedziaTab
from .deck_router_tab import DeckRouterTab
from .stats_tab import StatsTab
from .logs_tab import LogsTab


def _reload_module_configs() -> None:
    """Reset cached module state so next use picks up the new config."""
    try:
        from .. import ai_generator as _ai_mod
        _ai_mod.reset_generator()
    except ImportError:
        pass


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Anki Toolkit — Ustawienia")
        self.resize(960, 620)
        self.setMinimumSize(680, 460)

        cfg = get_full_config()
        # LogsTab applies the debug toggle immediately — remember the saved
        # state so Cancel can restore it.
        self._orig_debug = bool(cfg.get("debug", {}).get("enabled", False))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._status_tab = StatusTab(cfg, open_tab=self._open_tab)

        # (base_title, icon, widget, group) — order = by task: daily → content →
        # system → insight. base_title is what status_tab navigates by; the icon
        # is only for display. group=None starts a new group with no header.
        tabs = [
            ("Start",        "🏠", self._status_tab,        None),
            ("AI Generator", "✨", AIGeneratorTab(cfg),     "Treść"),
            ("Workflowy",    "🔀", WorkflowsTab(cfg),       "Treść"),
            ("TTS",          "🔊", TTSTab(cfg),             "Treść"),
            ("Słownik",      "📖", DictionaryTab(cfg),      "Treść"),
            ("Moduły",       "🧩", ModulesTab(cfg),         "System"),
            ("Narzędzia",    "🛠", NarzedziaTab(cfg),       "System"),
            ("Deck Router",  "🎯", DeckRouterTab(cfg),      "System"),
            ("Normalizacja", "🎚", AudioNormalizerTab(cfg), "System"),
            ("Statystyki",   "📊", StatsTab(cfg),           "Wgląd"),
            ("Logi",         "📜", LogsTab(cfg),            "Wgląd"),
        ]

        self._nav = QListWidget()
        self._nav.setFixedWidth(190)
        self._nav.setSpacing(2)
        self._stack = QStackedWidget()
        self._tabs_list: list[tuple[str, object]] = []  # (title, widget) for apply()
        self._title_to_row: dict[str, int] = {}
        self._row_to_page: dict[int, int] = {}

        current_group = object()  # sentinel — Start (group None) gets no header
        for title, icon, widget, group in tabs:
            if group is not None and group != current_group:
                header = QListWidgetItem(group.upper())
                header.setFlags(Qt.ItemFlag.NoItemFlags)  # non-selectable separator
                header.setForeground(QColor("#9aa3ad"))
                self._nav.addItem(header)
                current_group = group
            page = self._stack.addWidget(widget)
            row = self._nav.count()
            self._nav.addItem(QListWidgetItem(f"{icon}  {title}"))
            self._row_to_page[row] = page
            self._title_to_row[title] = row
            self._tabs_list.append((title, widget))

        self._nav.currentRowChanged.connect(self._on_nav_changed)

        body = QHBoxLayout()
        body.setSpacing(8)
        body.addWidget(self._nav)
        body.addWidget(self._stack, 1)
        layout.addLayout(body)

        self._nav.setCurrentRow(self._title_to_row["Start"])

        info = hint_label("ⓘ Gdzie są zapisywane ustawienia?", small=True)
        info.setToolTip(
            "config.json w folderze wtyczki to szablon domyślny — nie jest nadpisywany.\n"
            "Zmiany są zapisywane w profilu Anki (meta.json) i widoczne po ponownym\n"
            "otwarciu tego dialogu."
        )
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _open_tab(self, title: str) -> None:
        row = self._title_to_row.get(title)
        if row is not None:
            self._nav.setCurrentRow(row)

    def _on_nav_changed(self, row: int) -> None:
        page = self._row_to_page.get(row)
        if page is None:
            return
        self._stack.setCurrentIndex(page)
        # Returning to Start: rebuild the dashboard from the current widget
        # state of the other tabs, so it reflects unsaved changes too.
        if self._stack.widget(page) is self._status_tab:
            self._status_tab.refresh(self._collect_config())

    def _collect_config(self) -> dict:
        """Current config merged with unsaved widget state (no save)."""
        cfg = get_full_config()
        for _title, widget in self._tabs_list:
            if widget is self._status_tab:
                continue
            try:
                widget.apply(cfg)
            except Exception:
                pass  # a half-filled tab must not break the dashboard
        return cfg

    def reject(self) -> None:
        set_debug(self._orig_debug)
        super().reject()

    def _save(self) -> None:
        cfg = get_full_config()
        for _title, widget in self._tabs_list:
            widget.apply(cfg)

        # Validation warnings
        warnings = []
        ai = cfg.get("ai_generator", {})
        ai_providers = ai.get("providers", {})
        for pname in ("openai", "anthropic", "google", "mistral"):
            p = ai_providers.get(pname, {})
            if p.get("model", "").strip() and not p.get("api_key", "").strip():
                warnings.append(f"AI Generator — {pname}: model ustawiony ale klucz API pusty")

        tts = cfg.get("tts", {})
        if tts.get("tts_provider") == "openrouter":
            used_shared = tts.get("use_ai_openrouter_key", False)
            if used_shared:
                or_key = ai_providers.get("openrouter", {}).get("api_key", "").strip()
                if not or_key:
                    warnings.append("TTS używa klucza z AI Generatora, ale OpenRouter w AI Generator nie ma klucza API")
            elif not tts.get("openrouter_api_key", "").strip():
                warnings.append("TTS — OpenRouter: klucz API pusty")

        if warnings:
            showWarning(
                "⚠️  Znaleziono potencjalne problemy:\n\n" +
                "\n".join(f"• {w}" for w in warnings) +
                "\n\nUstawienia zostały zapisane, ale niektóre funkcje mogą nie działać."
            )

        save_full_config(cfg)
        _reload_module_configs()
        tooltip("Ustawienia zapisane. Niektóre zmiany wymagają restartu Anki.")
        self.accept()


def open_settings() -> None:
    dlg = SettingsDialog()
    dlg.exec()
