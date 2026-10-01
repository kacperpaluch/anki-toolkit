"""Run with Anki's Python: QT_QPA_PLATFORM=offscreen python tests/qt_integrations_smoke.py.

Real QtWebEngine DOM extraction and picker widgets; synthetic pages, no network.
"""
import importlib.util
from pathlib import Path
import unittest

from aqt.qt import QApplication, QEventLoop, QTimer, QUrl, QWebEnginePage, QWebEngineProfile

ROOT = Path(__file__).resolve().parents[1]
APP = QApplication.instance() or QApplication(["qt-integrations-smoke"])


class QtIntegrationSmoke(unittest.TestCase):
    def test_dictionary_entries_and_challenges(self):
        script = (ROOT / 'integrations/dictionaries-to-anki.user.js').read_text()
        cases = [
            ('www.diki.pl', '<div class="dictionaryEntity"><div class="hws"><b class="hw">mother</b></div><ul class="foreignToNativeMeanings"><li><span class="hw"><a>matka</a> (rodzic)</span>, <span class="hw">mama</span> <span class="meaningAdditionalInformation"> </span><div class="cat">Rodzina</div><div class="exampleSentence">Anki example</div></li></ul></div><div class="dictionaryEntity"><div class="hws"><b class="hw">mother <span class="stopword">somebody</span></b></div><ul class="foreignToNativeMeanings"><li><span class="hw">matkować</span></li></ul></div>', [{'pl': 'matka (rodzic), mama'}, {'pl': 'matkować'}]),
            ('www.oxfordlearnersdictionaries.com', '<div class="entry"><h1 class="headword">mother</h1><div class="sense"><span class="def">a female parent</span></div></div>', [{'def': 'a female parent'}]),
            ('www.ldoceonline.com', '<div class="Entry"><span class="HWD">mother</span><span class="Sense"><span class="DEF">a female parent</span></span></div>', [{'def': 'a female parent'}]),
            ('dictionary.cambridge.org', '<div class="entry-body__el"><b class="hw dhw">mother</b><div class="def-block"><span class="def">a female parent:</span><span class="dtrans-se">matka</span></div><div class="def-block"><span class="def"></span><span class="dtrans-se">sierota</span></div></div>', [{'def': 'a female parent', 'pl': 'matka'}]),
        ]
        cases.extend([
            ('www.diki.pl',
             '<div class="dictionaryEntity"><div class="hws"><b class="hw">mother</b></div>'
             '<div class="partOfSpeechSectionHeader"><span class="partOfSpeech">rzeczownik</span></div>'
             '<ol class="foreignToNativeMeanings"><li><span class="hw">matka</span>'
             '<span class="meaningAdditionalInformation">potocznie</span></li></ol>'
             '<div class="partOfSpeechSectionHeader"><span class="partOfSpeech">czasownik</span></div>'
             '<ol class="foreignToNativeMeanings"><li><span class="hw">matkować</span></li></ol></div>',
             [{'pl': 'matka, potocznie', 'pos': 'rzeczownik', 'labels': 'potocznie'},
              {'pl': 'matkować', 'pos': 'czasownik'}]),
            ('www.oxfordlearnersdictionaries.com',
             '<div class="entry"><h1 class="headword">mother</h1><span class="pos">noun</span>'
             '<div class="sense"><span class="labels">formal</span><span class="def">a parent</span></div>'
             '<div class="sense"><span class="labels">informal</span><span class="def">mum</span></div></div>',
             [{'def': 'a parent', 'pos': 'noun', 'labels': 'formal'},
              {'def': 'mum', 'pos': 'noun', 'labels': 'informal'}]),
            ('www.ldoceonline.com',
             '<div class="Entry"><span class="Head"><span class="HWD">mother</span><span class="POS">noun</span>'
             '<span class="GRAM">countable</span></span><span class="Sense">'
             '<span class="REGISTER">formal</span><span class="DEF">a parent</span></span></div>',
             [{'def': 'a parent', 'pos': 'noun', 'labels': 'countable; formal'}]),
            ('dictionary.cambridge.org',
             '<div class="entry-body__el"><b class="dhw">mother</b><div class="pos-header">'
             '<span class="pos">noun</span><span class="gram">[C]</span></div>'
             '<div class="def-block"><span class="lab"><span class="usage">informal</span></span>'
             '<span class="def">a parent</span><span class="dtrans-se">matka</span></div></div>',
             [{'def': 'a parent', 'pl': 'matka', 'pos': 'noun', 'labels': '[C]; informal'}]),
        ])
        cases = [(host, entry, expected, 'mother') for host, entry, expected in cases]
        cases.extend((host, entry.replace('mother', head), expected, 'brother in law')
                     for host, entry, expected, _word in cases[:4]
                     for head in ('brother-in-law', 'brother‑in‑law'))
        profile = QWebEngineProfile()
        page = QWebEnginePage(profile)
        try:
            for host, entry, expected, word in cases:
                with self.subTest(host=host):
                    loop = QEventLoop()
                    page.loadFinished.connect(loop.quit)
                    page.setHtml('<html><body>MENU ADVERT ' + entry + entry.replace('mother', 'father').replace('brother', 'sister').replace('matka', 'ojciec') + '</body></html>', QUrl('https://' + host + '/'))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    page.loadFinished.disconnect(loop.quit)
                    result = []
                    page.runJavaScript(script + f'\nwindow.ankiDictionaryEntries({word!r})', lambda value: (result.append(value), loop.quit()))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    self.assertEqual(result, [expected])  # only this entry, no menus, buttons or examples
                    result.clear()
                    page.runJavaScript('window.ankiDictionaryEntries("unrelated-phrase")', lambda value: (result.append(value), loop.quit()))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    self.assertEqual(result, [[]])
            for body in ("<main><p>mother</p><p>a female parent</p></main>", "Verify you are human"):
                # Changed markup or a CAPTCHA is no source, never a guess from the whole page.
                result = []
                page.runJavaScript(f'document.body.innerHTML="{body}"; window.ankiDictionaryEntries("mother")', lambda value: (result.append(value), loop.quit()))
                QTimer.singleShot(5000, loop.quit)
                loop.exec()
                self.assertEqual(result, [[]])
        finally:
            from aqt.qt import sip
            sip.delete(page)
            sip.delete(profile)

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
                '[document.title, window.ankiDictionaryEntries("mother").length,'
                ' document.querySelectorAll(".ankiBtn").length]',
                world, lambda value: (result.append(value), loop.quit()))
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.assertEqual(result, [['', 1, 2]])  # no page script; entry read; → hasło, → def
        finally:
            sip.delete(page)
            sip.delete(profile)

    def test_picker_requires_explicit_review_and_edit_resets_it(self):
        spec = importlib.util.spec_from_file_location('senses_smoke', ROOT / 'integrations/ai_senses.py')
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        senses = [{'pl': 'matka', 'en': 'a female parent', 'src': 'Oxford', 'by_ai': True},
                  {'pl': 'mama', 'en': 'mum', 'src': 'Cambridge', 'by_ai': False},
                  {'pl': 'macierz', 'en': '', 'src': '', 'by_ai': False}]
        dialog = m.SensePicker([{'word': 'mother', 'senses': senses}], None, {'ai_max_senses': 2})
        try:
            self.assertEqual([s['pl'] for _w, s in dialog.selected()], ['matka', 'mama'])  # first N checked
            self.assertIsNone(dialog._boxes[1][4])          # dictionary pair: nothing to review
            self.assertIn('bez definicji', dialog._boxes[2][0].text())
            self.assertTrue(dialog.selected()[0][1]['reviewed'])    # ticked by default
            self.assertFalse(dialog.selected()[1][1]['reviewed'])   # no checkbox, no claim
            box, word, sense, fields, reviewed = dialog._boxes[0]
            fields['pl'].setPlainText('mama')
            self.assertFalse(dialog.selected()[0][1]['reviewed'])
            fields['pl'].clear()
            dialog._accept_selected()
            self.assertTrue(dialog._error.text())
        finally:
            dialog.close()


if __name__ == '__main__':
    unittest.main()
