"""Ustawienia Integrations: kolejka n8n + sekcja „AI: znaczenia".

Lista dostawców i modeli pochodzi z dodatku Content — to on trzyma klucze.
Bez Contentu rozwijanka pokazuje tylko zapisaną wartość i jest wyłączona.
"""
from aqt import mw
from aqt.qt import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                    QLineEdit, QSpinBox, QVBoxLayout)
from aqt.utils import tooltip

from . import ai_senses


def _header(text):
    label = QLabel(f"<b>{text}</b>")
    return label


class Settings(QDialog):
 def __init__(self):
  super().__init__(mw);self.setWindowTitle('Anki Toolkit: Integrations — Ustawienia');c=mw.addonManager.getConfig(__package__) or {};q=c.get('word_queue',{});box=QVBoxLayout(self);x=QLabel('Kolejka słówek pobiera DataTable z n8n; adres zapasowy może być domeną Tailscale. Zmiany wymagają ponownego otwarcia panelu.');x.setWordWrap(True);box.addWidget(x);f=QFormLayout();self.url=QLineEdit(q.get('n8n_url',''));self.fallback=QLineEdit(q.get('fallback_url',''));self.key=QLineEdit(q.get('api_key',''));self.key.setEchoMode(QLineEdit.EchoMode.Password);self.table=QLineEdit(q.get('table_id',''));self.field=QLineEdit(q.get('word_field','ang'));self.word=QLineEdit(q.get('word_column','Slowko'));self.flag=QLineEdit(q.get('flag_column','Anki'));f.addRow('Adres n8n:',self.url);f.addRow('Adres zapasowy:',self.fallback);f.addRow('Klucz API:',self.key);f.addRow('ID tabeli:',self.table);f.addRow('Pole notatki:',self.field);f.addRow('Kolumna słowa:',self.word);f.addRow('Kolumna flagi:',self.flag);box.addLayout(f)
  box.addWidget(_header('AI: znaczenia'))
  hint = QLabel('Przycisk „AI: znaczenia” w panelu robi z jednego hasła po jednej karcie '
                'na każde znaczenie. Definicje są dosłownymi cytatami ze słowników '
                'otwartych w zakładkach — model je dopasowuje, nie tłumaczy.')
  hint.setWordWrap(True);box.addWidget(hint)

  ai = QFormLayout()
  fields = q.get('ai_fields') or {}
  self._content = self._content_providers()
  self.provider = QComboBox();self._fill_providers(q.get('ai_provider', ''))
  self.model = QComboBox();self.model.setEditable(True)
  self.model.lineEdit().setPlaceholderText('puste = model domyślny dostawcy')
  self.provider.currentIndexChanged.connect(lambda _i: self._fill_models())
  self._fill_models(q.get('ai_model', ''))
  self.senses = QSpinBox();self.senses.setRange(1, 10);self.senses.setValue(int(q.get('ai_max_senses', 3) or 3))
  self.senses.setToolTip('Ile kart maksymalnie powstaje z jednego hasła')
  self.timeout = QSpinBox();self.timeout.setRange(10, 600);self.timeout.setSuffix(' s')
  self.timeout.setValue(int(q.get('ai_timeout', 120) or 120))
  self.timeout.setToolTip('Lokalne CLI (Codex, Claude) myśli dłużej niż API')
  self.tag = QLineEdit(q.get('ai_tag', ''));self.tag.setPlaceholderText('puste = bez tagu')
  self.review_tag = QLineEdit(q.get('ai_review_tag', ''));self.review_tag.setPlaceholderText('puste = bez tagu')
  self.pl = QLineEdit(fields.get('pl', 'pol'))
  self.definition = QLineEdit(fields.get('definition', 'def'))
  self.example = QLineEdit(fields.get('example', 'przyklad'))
  ai.addRow('Dostawca AI:', self.provider)
  ai.addRow('Model:', self.model)
  ai.addRow('Maks. znaczeń z hasła:', self.senses)
  ai.addRow('Limit czasu:', self.timeout)
  ai.addRow('Tag pewnych dopasowań:', self.tag)
  ai.addRow('Tag do weryfikacji:', self.review_tag)
  ai.addRow('Pole polskie:', self.pl)
  ai.addRow('Pole definicji:', self.definition)
  ai.addRow('Pole przykładu:', self.example)
  box.addLayout(ai)
  note = QLabel('Pole angielskie to „Pole notatki” powyżej. Tagi rozdzielaj spacją lub przecinkiem; karta dostaje dokładnie jeden z dwóch — nigdy oba.')
  note.setWordWrap(True);box.addWidget(note)

  b=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);b.accepted.connect(self.save);b.rejected.connect(self.reject);box.addWidget(b)

 # -- dostawcy z dodatku Content -------------------------------------------

 def _content_providers(self):
  """{klucz dostawcy: jego konfiguracja} z Contentu; ({} gdy go nie ma)."""
  module, addon = ai_senses.providers_module()
  if module is None:
   return {}
  self._labels = getattr(module, 'PROVIDER_LABELS', {})
  generator = (mw.addonManager.getConfig(addon) or {}).get('ai_generator', {})
  return dict(generator.get('providers') or {})

 def _fill_providers(self, current):
  if not self._content:
   # Bez Contentu nie ma z czego wybierać — pokaż, co zapisane, i nie udawaj listy.
   self.provider.addItem(current or '— brak dodatku Content —', current)
   self.provider.setEnabled(False)
   return
  self.provider.addItem('— nie wybrano —', '')
  for key, label in getattr(self, '_labels', {}).items():
   configured = key in self._content
   self.provider.addItem(label if configured else f'{label} (nieskonfigurowany)', key)
  index = self.provider.findData(current)
  self.provider.setCurrentIndex(index if index >= 0 else 0)

 def _fill_models(self, current=None):
  """Modele znane Contentowi dla wybranego dostawcy. Pole zostaje edytowalne."""
  if current is None:
   current = self.model.currentText()
  cfg = self._content.get(self.provider.currentData() or '', {})
  known = {cfg.get('model', '')} | set(cfg.get('cached_models') or [])
  self.model.clear();self.model.addItem('')
  self.model.addItems(sorted(m for m in known if m))
  self.model.setCurrentText(current or '')

 def save(self):
  c=mw.addonManager.getConfig(__package__) or {};q=c.setdefault('word_queue',{})
  q.update({'n8n_url':self.url.text().strip(),'fallback_url':self.fallback.text().strip(),'api_key':self.key.text().strip(),'table_id':self.table.text().strip(),'word_field':self.field.text().strip(),'word_column':self.word.text().strip(),'flag_column':self.flag.text().strip()})
  q.update({
   'ai_provider': self.provider.currentData() or '',
   'ai_model': self.model.currentText().strip(),
   'ai_max_senses': self.senses.value(),
   'ai_timeout': self.timeout.value(),
   'ai_tag': ' '.join(ai_senses.parse_tags(self.tag.text())),
   'ai_review_tag': ' '.join(ai_senses.parse_tags(self.review_tag.text())),
   'ai_fields': {'pl': self.pl.text().strip(), 'definition': self.definition.text().strip(),
                 'example': self.example.text().strip()},
  })
  mw.addonManager.writeConfig(__package__,c);tooltip('Ustawienia Integrations zapisane.',parent=mw);self.accept()
def open_settings():Settings().exec()
