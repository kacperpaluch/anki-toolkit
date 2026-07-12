from aqt import mw
from aqt.qt import QAction, QDialog, QVBoxLayout, QLabel, QComboBox, QSpinBox, QDialogButtonBox, QFormLayout
from aqt.utils import showInfo, tooltip

from ..common import ADDON_NAME


# Anki wymaga liczby w polu limitu talii filtrowanej — "bez limitu" (spinbox=0)
# mapujemy na tę wartość.
NO_LIMIT = 999999999

# Predefiniowane presety: (etykieta, search, limit, kolejność)
# Kolejność 1=losowo dla wszystkich. Działają w dowolnym decku (brak filtra
# deck:) i nie zmieniają harmonogramu (resched=False).
PRESETS = [
    ("Uczone w ostatnich 7 dniach", "rated:7", 99999, 1),
    ("Uczone w ostatnich 30 dniach", "rated:30", 99999, 1),
    ("Wszystkie uczone karty (bez limitu)", "-is:new", 0, 1),
    ("Trudne karty (pomyłki z 30 dni)", "rated:30:1", 99999, 1),
    ("Losowe karty (uczone lub nie)", "deck:*", 100, 1),
]


def _get_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("filtered_deck", {})


class FilterSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Talia filtrowana — preset")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        form = QFormLayout()

        self.preset_combo = QComboBox()
        for i, (label, *_rest) in enumerate(PRESETS):
            self.preset_combo.addItem(label, i)
        form.addRow("Preset:", self.preset_combo)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, NO_LIMIT)
        self.limit_spin.setSpecialValueText("Bez limitu")  # wyświetla się przy 0
        form.addRow("Limit kart:", self.limit_spin)

        # Wybór presetu podpowiada jego domyślny limit; użytkownik może nadpisać.
        self.preset_combo.currentIndexChanged.connect(self._sync_limit)
        self._sync_limit()

        layout.addLayout(form)

        hint = QLabel("Karty z dowolnego decka. Powtórka nie zmienia harmonogramu.")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def _sync_limit(self):
        self.limit_spin.setValue(PRESETS[self.preset_combo.currentData()][2])

    def get_values(self):
        # spinbox 0 ("Bez limitu") -> NO_LIMIT
        return self.preset_combo.currentData(), self.limit_spin.value() or NO_LIMIT


def create_filtered_deck(preset_index, card_limit=None):
    label, search_query, default_limit, sort_order = PRESETS[preset_index]
    if card_limit is None:
        card_limit = default_limit
    if not card_limit:  # 0 = bez limitu
        card_limit = NO_LIMIT
    cfg = _get_config()
    base_name = cfg.get("deck_name", "Powtórka z wyprzedzeniem")
    deck_name = f"{base_name} — {label}"
    reschedule = False

    try:
        col = mw.col

        # Reuse an existing filtered deck with this name instead of piling up
        # "name (1)", "name (2)"... — only suffix when the name is taken by a
        # regular (non-filtered) deck.
        existing = col.decks.by_name(deck_name)
        reused = False
        if existing and existing.get("dyn"):
            deck_id = existing["id"]
            reused = True
        else:
            counter = 1
            while col.decks.by_name(deck_name):
                deck_name = f"{base_name} — {label} ({counter})"
                counter += 1
            deck_id = col.decks.new_filtered(deck_name)
        deck = col.decks.get(deck_id)

        if isinstance(deck, dict):
            terms = deck.get('terms')
            if terms and len(terms) > 0 and len(terms[0]) >= 3:
                deck['terms'][0][0] = search_query
                deck['terms'][0][1] = card_limit
                deck['terms'][0][2] = sort_order
                deck['resched'] = reschedule
                deck['separate'] = True
                col.decks.save(deck)
            else:
                showInfo(f"Talia zwróciła nieoczekiwaną strukturę 'terms': {terms}")
                return
        else:
            try:
                config = deck.config
                if not config.search_terms or len(config.search_terms) == 0:
                    showInfo("Talia nie ma warunków wyszukiwania (search_terms jest puste).")
                    return
                config.search_terms[0].search = search_query
                config.search_terms[0].limit = card_limit
                config.search_terms[0].order = sort_order
                config.reschedule = reschedule
                col.decks.save(deck)
            except AttributeError as e:
                showInfo(f"Nieobsługiwana struktura talii filtrowanej: {e}")
                return

        col.sched.rebuild_filtered_deck(deck_id)
        card_count = col.decks.card_count(deck_id, include_subdecks=False)
        mw.col.decks.select(deck_id)
        mw.reset()
        verb = "Zaktualizowano" if reused else "Utworzono"
        tooltip(f"{verb} talię '{deck_name}'\nKarty: {card_count}", period=3000)

    except Exception as e:
        showInfo(f"Błąd podczas tworzenia talii filtrowanej: {str(e)}")


def show_dialog_and_create():
    dialog = FilterSettingsDialog(mw)
    if dialog.exec():
        preset_index, card_limit = dialog.get_values()
        create_filtered_deck(preset_index, card_limit)


def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools
    action = QAction("Utwórz talię filtrowaną (preset)...", mw)
    action.triggered.connect(show_dialog_and_create)
    menu.addAction(action)
