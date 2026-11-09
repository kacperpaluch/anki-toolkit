"""Run with Anki's Python: QT_QPA_PLATFORM=offscreen python tests/qt_integrations_smoke.py.

Real queue panel and userscript buttons in QtWebEngine; synthetic pages, no network.
"""
import importlib.util
import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from aqt.qt import QApplication, QEventLoop, QTimer, QUrl, QWebEnginePage, QWebEngineProfile

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication(["qt-integrations-smoke"])


class QtIntegrationSmoke(unittest.TestCase):
    def test_queue_layout_and_action_states_without_n8n(self):
        from aqt.qt import QDockWidget, QTabWidget, Qt, sip
        # Import the real panel without registering add-on hooks or using a profile.
        package = types.ModuleType('queue_preview')
        package.__path__ = [str(ROOT)]
        integrations = types.ModuleType('queue_preview.integrations')
        integrations.__path__ = [str(ROOT / 'integrations')]
        with patch.dict(sys.modules, {'queue_preview': package,
                                     'queue_preview.integrations': integrations}):
            module = importlib.import_module('queue_preview.integrations.panel')
        panel = module.WordQueuePanel.__new__(module.WordQueuePanel)
        QDockWidget.__init__(panel)
        with tempfile.TemporaryDirectory() as folder:
            panel._state = module.QueueState('/test/collection.anki2', {}, folder)
            panel._cfg = {'word_column': 'Slowko', 'flag_column': 'Anki', 'order': 'id'}
            panel._marked = set()
            panel._pending = {}
            panel._suspend = False
            panel._done_count = 0
            try:
                with patch.object(module, '_DictTabs', side_effect=lambda *args: QTabWidget(args[-1])):
                    panel.setWidget(panel._build_ui())
                panel.resize(1100, 750)
                panel.show()
                APP.processEvents()
                # Silence navigation so this test never touches an editor or a dictionary.
                with panel._silent():
                    for row_id, word in ((1, 'mother'), (2, 'word 2'), (3, 'word 3')):
                        panel._list.addItem(panel._make_item({'id': row_id, 'Slowko': word}))
                self.assertIsNone(panel._list.item(0).data(Qt.ItemDataRole.CheckStateRole))  # no checkbox
                panel._marked.add(2)
                panel._apply_hiding()  # default filter: only todo
                self.assertEqual([panel._list.item(i).isHidden() for i in range(3)], [False, True, False])
                panel._status_filter.setCurrentIndex(2)  # only done
                self.assertEqual([panel._list.item(i).isHidden() for i in range(3)], [True, False, True])
                panel._status_filter.setCurrentIndex(0)  # all
                panel._search.setText('WORD')
                self.assertEqual([panel._list.item(i).isHidden() for i in range(3)], [True, False, False])
            finally:
                sip.delete(panel)

    def test_diki_buttons_cover_every_headword(self):
        # diki "sea buckthorn": a latin name comes first, alternatives follow „także:”.
        script = (ROOT / 'integrations/dictionaries-to-anki.user.js').read_text()
        html = ('<div class="dictionaryEntity"><div class="hws"><h1><span class="hw">hippophae</span><br>'
                '<span class="hw">sea buckthorn</span>, także: '
                '<span class="hw hwLessPopularAlternative">seaberry</span></h1></div>'
                '<ol class="foreignToNativeMeanings"><li><span class="hw">rokitnik</span></li></ol></div>')
        sent = ('(() => { let body; window.fetch = (_url, options) => { body = options.body;'
                ' return Promise.resolve({json: () => ({ok: true})}); };'
                ' const buttons = [...document.querySelectorAll(".ankiBtn")];'
                ' buttons.find((b) => b.textContent === "→ oba").click();'
                ' return [buttons.filter((b) => b.textContent === "→ hasło")'
                '.map((b) => b.previousElementSibling.textContent), JSON.parse(body).fields.headword]; })()')
        profile = QWebEngineProfile()
        page = QWebEnginePage(profile)
        try:
            for query, headword in (('sea+buckthorn', 'sea buckthorn'), ('seaberry', 'seaberry'),
                                    ('rokitnik', 'hippophae')):  # no headword searched: the first
                with self.subTest(query=query):
                    loop = QEventLoop()
                    page.loadFinished.connect(loop.quit)
                    page.setHtml(html, QUrl('https://www.diki.pl/slownik-angielskiego?q=' + query))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    page.loadFinished.disconnect(loop.quit)
                    result = []
                    page.runJavaScript(script + '\n' + sent, lambda value: (result.append(value), loop.quit()))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    self.assertEqual(result, [[['hippophae', 'sea buckthorn', 'seaberry'], headword]])
        finally:
            from aqt.qt import sip
            sip.delete(page)
            sip.delete(profile)

    def test_userscript_works_where_page_scripts_are_off(self):
        # Tabs outside `page_js` run no page JavaScript; the userscript lives in its own world.
        from aqt.qt import QWebEngineScript, QWebEngineSettings, sip
        world = 1  # ApplicationWorld, as panel._WORLD
        profile = QWebEngineProfile()
        script = QWebEngineScript()
        script.setSourceCode((ROOT / 'integrations/dictionaries-to-anki.user.js').read_text())
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(world)
        profile.scripts().insert(script)
        page = QWebEnginePage(profile)
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
        try:
            loop = QEventLoop()
            page.loadFinished.connect(loop.quit)
            page.setHtml('<script>document.title = "page js ran"</script><div class="Entry">'
                         '<span class="HWD">mother</span><span class="Sense">'
                         '<span class="DEF">a female parent</span></span></div>',
                         QUrl('https://www.ldoceonline.com/dictionary/mother'))  # Qt honours @match
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            result = []
            page.runJavaScript(
                '[document.title, document.querySelectorAll(".ankiBtn").length]',
                world, lambda value: (result.append(value), loop.quit()))
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.assertEqual(result, [['', 2]])  # no page script; → hasło, → def
        finally:
            sip.delete(page)
            sip.delete(profile)

if __name__ == '__main__':
    unittest.main()
