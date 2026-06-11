from aqt import mw
from aqt.qt import QAction, QDialog, QVBoxLayout, QLabel, QSpinBox, QDialogButtonBox, QComboBox, QFormLayout
from aqt.utils import showInfo, tooltip

from ..common import ADDON_NAME


def _get_config() -> dict:
    full = mw.addonManager.getConfig(ADDON_NAME) or {}
    return full.get("filtered_deck", {})


class FilterSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ustawienia talii filtrowanej")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.days_spin = QSpinBox()
        self.days_spin.setRange(0, 36500)
        self.days_spin.setValue(9999)
        self.days_spin.setToolTip("Zakres wyszukiwania Anki: prop:due<=X")
        form.addRow("Dni do przodu:", self.days_spin)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 999999)
        self.limit_spin.setValue(99999)
        form.addRow("Limit kart:", self.limit_spin)

        self.order_combo = QComboBox()
        self.order_combo.addItem("Najdawniej oglądane", 0)
        self.order_combo.addItem("Losowo", 1)
        self.order_combo.addItem("Rosnące interwały", 2)
        self.order_combo.addItem("Malejące interwały", 3)
        self.order_combo.addItem("Najwięcej pomyłek", 4)
        self.order_combo.addItem("Kolejność dodania", 5)
        self.order_combo.addItem("Termin powtórki", 6)
        self.order_combo.setCurrentIndex(1)
        form.addRow("Kolejność:", self.order_combo)

        layout.addLayout(form)

        hint = QLabel("Talia filtrowana nie zmienia harmonogramu powtórek.")
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

    def get_values(self):
        return (
            self.days_spin.value(),
            self.limit_spin.value(),
            self.order_combo.currentData()
        )


def create_filtered_deck(days_ahead, card_limit, sort_order):
    cfg = _get_config()
    deck_name = cfg.get("deck_name", "Angielski - Powtórka z wyprzedzeniem")
    search_deck = cfg.get("search_deck", "angielski")
    escaped_deck = search_deck.replace('"', '\\"')
    search_query = f'prop:due<={days_ahead} deck:"{escaped_deck}"'
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
            base_name = deck_name
            counter = 1
            while col.decks.by_name(deck_name):
                deck_name = f"{base_name} ({counter})"
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
        tooltip(f"{verb} talię '{deck_name}'\nKarty: {card_count}\nZakres: {days_ahead} dni.", period=3000)

    except Exception as e:
        showInfo(f"Błąd podczas tworzenia talii filtrowanej: {str(e)}")


def show_dialog_and_create():
    dialog = FilterSettingsDialog(mw)
    if dialog.exec():
        days, limit, order = dialog.get_values()
        create_filtered_deck(days, limit, order)


def setup_menu(parent_menu=None):
    cfg = _get_config()
    search_deck = cfg.get("search_deck", "angielski")
    menu = parent_menu or mw.form.menuTools
    action = QAction(f"Utwórz talię filtrowaną: {search_deck}...", mw)
    action.triggered.connect(show_dialog_and_create)
    menu.addAction(action)
