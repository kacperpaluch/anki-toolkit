import json,os,re,shutil
from pathlib import Path
from aqt import mw,gui_hooks
from aqt.qt import QAction,QCursor,QMenu,QTimer
from aqt.utils import tooltip
from .logic import oxford_fields,sm_fields,truncate
_cache={}


def _migrate_legacy_databases():
 """Copy old merged-addon databases once; never delete the source files."""
 target = Path(__file__).parent / "user_files"
 legacy = Path(__file__).resolve().parents[2] / "user_files"
 for filename in ("oxford.json", "supermemo.json"):
  source, destination = legacy / filename, target / filename
  if source.is_file() and not destination.exists():
   try:
    target.mkdir(exist_ok=True)
    shutil.copy2(source, destination)
   except OSError:
    pass


_migrate_legacy_databases()
def _name(): return __name__.split('.')[0]
def get_config(): return {'oxford':{'match_field':'ang'},'supermemo':{'match_field':'ang','field_map':{'Translation':'pol','Definition':'def','Synonyms':'synonim','PartOfSpeech':'cz_mowy'}},**(mw.addonManager.getConfig(_name()) or {})}
def save_config(changes):
 c=mw.addonManager.getConfig(_name()) or {}; c.update(changes); mw.addonManager.writeConfig(_name(),c)
def _db(kind):
 if kind not in _cache:
  try:
   with open(os.path.join(os.path.dirname(__file__),'user_files',f'{kind}.json'),encoding='utf8') as f:_cache[kind]=json.load(f)
  except Exception:_cache[kind]={}
 return _cache[kind]
def _clean(value):return re.sub('<[^>]+>','',value or '').strip()
def _fetch(editor,kind):
 cfg=get_config()[kind]; match=cfg['match_field']
 def start():
  note=editor.note
  if note is None or match not in note:return
  word=_clean(note[match])
  entries=_db(kind).get(word.lower(),[])
  if not word:tooltip(f'{kind.title()}: puste pole źródłowe.',parent=mw);return
  if not entries:tooltip(f'{kind.title()}: brak „{word}”.',parent=mw);return
  def fill(entry):
   existing={k:note[k] for k in note.keys()}; updates=oxford_fields(entry,existing,match) if kind=='oxford' else sm_fields(entry,existing,cfg.get('field_map',{}),match)
   if not updates:tooltip(f'{kind.title()}: brak nowych pól do uzupełnienia.',parent=mw);return
   for key,value in updates.items():note[key]=value
   editor.loadNote();tooltip(f'{kind.title()}: uzupełniono {len(updates)} pól.',parent=mw)
  if len(entries)==1:fill(entries[0]);return
  menu=QMenu(editor.widget)
  for entry in entries:
   translation=_clean(entry.get('pol',entry.get('Translation',''))); definition=truncate(_clean(entry.get('def',entry.get('Definition','')))); label=' · '.join(x for x in (entry.get('_level',''),translation,definition) if x) or '(bez tłumaczenia)'; action=QAction(label,menu); action.triggered.connect(lambda _=False,e=entry:fill(e));menu.addAction(action)
  menu.exec(QCursor.pos())
 editor.saveNow(start)
def _buttons(buttons,editor):
 buttons.append(editor.addButton(None,'local_libraries_ox',lambda ed=editor:_fetch(ed,'oxford'),tip='Uzupełnij pola z Oxford 5000',label='OX'));buttons.append(editor.addButton(None,'local_libraries_sm',lambda ed=editor:_fetch(ed,'supermemo'),tip='Uzupełnij pola z SuperMemo',label='SM'));return buttons
gui_hooks.editor_did_init_buttons.append(_buttons)
def _menu(*_):
 from .settings import open_settings
 action=QAction('Anki Toolkit: Local Sources — Ustawienia…',mw);action.triggered.connect(open_settings);mw.form.menuTools.addAction(action)
if hasattr(gui_hooks,'main_window_did_init'):gui_hooks.main_window_did_init.append(_menu)
else:QTimer.singleShot(0,_menu)
