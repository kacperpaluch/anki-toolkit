"""Settings dialog for Anki Toolkit — unified configuration UI."""

from aqt import mw
from aqt.qt import QDialog, QTabWidget, QVBoxLayout, QDialogButtonBox
from aqt.utils import tooltip
from aqt.utils import showWarning

from ..common import ADDON_NAME, get_full_config, save_full_config, set_debug
from ..common.ui import hint_label

from .status_tab import StatusTab
from .modules_tab import ModulesTab
from .dictionary_tab import DictionaryTab
from .ai_generator_tab import AIGeneratorTab
from .tts_tab import TTSTab
from .audio_normalizer_tab import AudioNormalizerTab
from .narzedzia_tab import NarzedziaTab
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
        self.resize(780, 580)
        self.setMinimumSize(520, 420)

        cfg = get_full_config()
        # LogsTab applies the debug toggle immediately — remember the saved
        # state so Cancel can restore it.
        self._orig_debug = bool(cfg.get("debug", {}).get("enabled", False))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self._tabs = QTabWidget()
        self._tab_indices: dict[str, int] = {}

        self._status_tab = StatusTab(cfg, open_tab=self._open_tab)
        self._tabs_list = [
            ("Start",            self._status_tab),
            ("Moduły",           ModulesTab(cfg)),
            ("Słownik",          DictionaryTab(cfg)),
            ("AI Generator",     AIGeneratorTab(cfg)),
            ("TTS",              TTSTab(cfg)),
            ("Normalizacja",     AudioNormalizerTab(cfg)),
            ("Narzędzia",        NarzedziaTab(cfg)),
            ("Statystyki",       StatsTab(cfg)),
            ("Logi",             LogsTab(cfg)),
        ]
        for title, widget in self._tabs_list:
            self._tab_indices[title] = self._tabs.addTab(widget, title)

        self._tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self._tabs)

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
        index = self._tab_indices.get(title)
        if index is not None:
            self._tabs.setCurrentIndex(index)

    def _on_tab_changed(self, index: int) -> None:
        # Returning to Start: rebuild the dashboard from the current widget
        # state of the other tabs, so it reflects unsaved changes too.
        if index == self._tab_indices.get("Start"):
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
