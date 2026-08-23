from aqt import mw
from aqt.qt import QDialog,QDialogButtonBox,QFormLayout,QLabel,QLineEdit,QVBoxLayout
from aqt.utils import tooltip
class Settings(QDialog):
 def __init__(self):
  super().__init__(mw); self.setWindowTitle('Anki Toolkit: Local Sources — Ustawienia'); from . import get_config; c=get_config(); box=QVBoxLayout(self); x=QLabel('Oxford i SuperMemo używają lokalnych plików JSON w user_files/. Pola mapowania SuperMemo zapisuj jako pary źródło:cel, oddzielone przecinkami.'); x.setWordWrap(True); box.addWidget(x); form=QFormLayout(); self.ox=QLineEdit(c['oxford']['match_field']); self.sm=QLineEdit(c['supermemo']['match_field']); self.map=QLineEdit(', '.join(f'{a}:{b}' for a,b in c['supermemo']['field_map'].items())); form.addRow('Oxford — pole hasła:',self.ox); form.addRow('SuperMemo — pole hasła:',self.sm); form.addRow('SuperMemo — mapowanie:',self.map); box.addLayout(form); b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); b.accepted.connect(self.save); b.rejected.connect(self.reject); box.addWidget(b)
 def save(self):
  from . import save_config
  mapping={a.strip():b.strip() for item in self.map.text().split(',') if ':' in item for a,b in [item.split(':',1)] if a.strip() and b.strip()}; save_config({'oxford':{'match_field':self.ox.text().strip() or 'ang'},'supermemo':{'match_field':self.sm.text().strip() or 'ang','field_map':mapping}}); tooltip('Ustawienia Local Libraries zapisane.',parent=mw); self.accept()
def open_settings(): Settings().exec()
