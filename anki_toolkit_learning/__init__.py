"""Anki Toolkit: Learning — filtered-deck presets."""
from aqt import mw, gui_hooks
from aqt.qt import QAction, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox, QSpinBox, QVBoxLayout, QTimer
from aqt.utils import showInfo, tooltip

NO_LIMIT=999999999
PRESETS=[("Uczone w ostatnich 7 dniach","rated:7",99999,1),("Uczone w ostatnich 30 dniach","rated:30",99999,1),("Wszystkie uczone karty (bez limitu)","-is:new",0,1),("Trudne karty (pomyłki z 30 dni)","rated:30:1",99999,1),("Losowe karty (uczone lub nie)","deck:*",100,1)]
def _addon_name(): return __name__.split(".")[0]
def get_config(): return {"deck_name":"Angielski - Powtórka z wyprzedzeniem", **(mw.addonManager.getConfig(_addon_name()) or {})}
def save_config(changes):
    cfg=mw.addonManager.getConfig(_addon_name()) or {}; cfg.update(changes); mw.addonManager.writeConfig(_addon_name(),cfg)

class PresetDialog(QDialog):
    def __init__(self):
        super().__init__(mw); self.setWindowTitle("Talia filtrowana — preset"); layout=QVBoxLayout(self); form=QFormLayout(); self.preset=QComboBox()
        for index,(label,*_) in enumerate(PRESETS): self.preset.addItem(label,index)
        self.limit=QSpinBox(); self.limit.setRange(0,NO_LIMIT); self.limit.setSpecialValueText("Bez limitu"); self.preset.currentIndexChanged.connect(self.sync); self.sync(); form.addRow("Preset:",self.preset); form.addRow("Limit kart:",self.limit); layout.addLayout(form); hint=QLabel("Karty z dowolnego decka. Powtórka nie zmienia harmonogramu."); hint.setWordWrap(True); layout.addWidget(hint); buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); advanced=buttons.addButton("Dodatkowe ustawienia…", QDialogButtonBox.ButtonRole.ActionRole); advanced.clicked.connect(self.open_settings); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def sync(self): self.limit.setValue(PRESETS[self.preset.currentData()][2])
    def values(self): return self.preset.currentData(), self.limit.value() or NO_LIMIT
    def open_settings(self):
        from .settings import open_settings
        open_settings()

def create_filtered_deck(index, limit=None):
    label,query,default,order=PRESETS[index]; limit=limit or default or NO_LIMIT; base=get_config()["deck_name"]; name=f"{base} — {label}"; col=mw.col
    try:
        existing=col.decks.by_name(name); reused=bool(existing and existing.get("dyn")); deck_id=existing["id"] if reused else None
        if not deck_id:
            counter=1; candidate=name
            while col.decks.by_name(candidate): candidate=f"{name} ({counter})"; counter+=1
            name=candidate; deck_id=col.decks.new_filtered(name)
        deck=col.decks.get(deck_id)
        if isinstance(deck,dict): deck["terms"][0][0]=query; deck["terms"][0][1]=limit; deck["terms"][0][2]=order; deck["resched"]=False; deck["separate"]=True; col.decks.save(deck)
        else:
            term=deck.config.search_terms[0]; term.search=query; term.limit=limit; term.order=order; deck.config.reschedule=False; col.decks.save(deck)
        col.sched.rebuild_filtered_deck(deck_id); mw.col.decks.select(deck_id); mw.reset(); tooltip(f"{'Zaktualizowano' if reused else 'Utworzono'} talię '{name}'",period=3000)
    except Exception as error: showInfo(f"Błąd podczas tworzenia talii filtrowanej: {error}")
def show_presets():
    dialog=PresetDialog()
    if dialog.exec(): create_filtered_deck(*dialog.values())
def _setup(*_args):
    from .settings import open_settings
    action=QAction("Anki Toolkit: Learning…", mw); action.triggered.connect(show_presets); mw.form.menuTools.addAction(action)
    mw.addonManager.setConfigAction(_addon_name(), open_settings)
if hasattr(gui_hooks,"main_window_did_init"): gui_hooks.main_window_did_init.append(_setup)
else: QTimer.singleShot(0,_setup)
