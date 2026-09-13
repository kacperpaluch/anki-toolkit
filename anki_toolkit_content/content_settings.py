from aqt import mw
from aqt.qt import QDialog,QDialogButtonBox,QTabWidget,QVBoxLayout,QWidget
from aqt.utils import tooltip
from .settings.ai_generator_tab import AIGeneratorTab
from .settings.dictionary_tab import DictionaryTab
from .settings.tts_tab import TTSTab
from .settings.workflows_tab import WorkflowsTab
from .settings.logs_tab import LogsTab
from .settings.narzedzia_tab import FieldSplitterSettings

class SettingsDialog(QDialog):
 def __init__(self):
  super().__init__(mw);self.setWindowTitle('Anki Toolkit: Content — Ustawienia');self.resize(960,620)
  from .common import get_full_config
  self.cfg=get_full_config();box=QVBoxLayout(self);tabs=QTabWidget();self.panels=[]
  self._orig_debug=bool(self.cfg.get('debug',{}).get('enabled',False))
  for title,panel in [('Workflowy',WorkflowsTab(self.cfg)),('AI Generator',AIGeneratorTab(self.cfg)),('TTS',TTSTab(self.cfg)),('Słownik',DictionaryTab(self.cfg)),('Rozdzielanie pól',FieldSplitterSettings(self.cfg)),('Diagnostyka',LogsTab(self.cfg))]:tabs.addTab(panel,title);self.panels.append(panel)
  box.addWidget(tabs);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);box.addWidget(buttons)
 def save(self):
  from .common import save_full_config
  for panel in self.panels:panel.apply(self.cfg)
  save_full_config(self.cfg);tooltip('Ustawienia Content zapisane.',parent=mw);self.accept()
 def reject(self):
  from .common import set_debug
  set_debug(self._orig_debug);super().reject()
def open_settings():SettingsDialog().exec()
