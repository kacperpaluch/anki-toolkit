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
            ('www.diki.pl', '<div class="dictionaryEntity"><div class="hws"><b class="hw">mother</b></div><ul class="foreignToNativeMeanings"><li>matka</li></ul></div>'),
            ('www.oxfordlearnersdictionaries.com', '<div class="entry"><h1 class="headword">mother</h1><div class="sense"><span class="def">a female parent</span></div></div>'),
            ('www.ldoceonline.com', '<div class="Entry"><span class="HWD">mother</span><span class="Sense"><span class="DEF">a female parent</span></span></div>'),
            ('dictionary.cambridge.org', '<div class="entry-body__el"><b class="hw dhw">mother</b><div class="def-block"><span class="def">a female parent</span><span class="dtrans-se">matka</span></div></div>'),
        ]
        profile = QWebEngineProfile()
        page = QWebEnginePage(profile)
        try:
            for host, entry in cases:
                with self.subTest(host=host):
                    loop = QEventLoop()
                    page.loadFinished.connect(loop.quit)
                    page.setHtml('<html><body>MENU ADVERT ' + entry + entry.replace('mother', 'father').replace('matka', 'ojciec') + '</body></html>', QUrl('https://' + host + '/'))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    page.loadFinished.disconnect(loop.quit)
                    result = []
                    page.runJavaScript(script + '\nwindow.ankiDictionaryText("mother")', lambda value: (result.append(value), loop.quit()))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    self.assertTrue(result and result[0])
                    self.assertNotIn('father', result[0])
                    self.assertNotIn('MENU', result[0])
                    self.assertNotIn('Anki', result[0])
                    result.clear()
                    page.runJavaScript('window.ankiDictionaryText("unrelated phrase")', lambda value: (result.append(value), loop.quit()))
                    QTimer.singleShot(5000, loop.quit)
                    loop.exec()
                    self.assertEqual(result, [''])
            result = []
            # Markup changed: no entry selector matches, but the word is on the page.
            page.runJavaScript('document.body.innerHTML="<main><p>mother</p><p>a female parent</p></main>"; window.ankiDictionaryText("mother")', lambda value: (result.append(value), loop.quit()))
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.assertTrue(result[0]['whole'])
            self.assertIn('a female parent', result[0]['text'])
            result = []
            page.runJavaScript('document.body.innerHTML="Verify you are human"; window.ankiDictionaryText("mother")', lambda value: (result.append(value), loop.quit()))
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.assertEqual(result, [''])
        finally:
            from aqt.qt import sip
            sip.delete(page)
            sip.delete(profile)

    def test_picker_requires_explicit_review_and_edit_resets_it(self):
        spec = importlib.util.spec_from_file_location('senses_smoke', ROOT / 'integrations/ai_senses.py')
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        dialog = m.SensePicker([{'word': 'mother', 'senses': [{'pl': 'matka', 'en': 'a female parent', 'example': '', 'match': 'exact'}]}], None)
        try:
            self.assertFalse(dialog.selected()[0][1]['reviewed'])
            box, word, sense, fields, reviewed = dialog._boxes[0]
            reviewed.setChecked(True)
            self.assertTrue(dialog.selected()[0][1]['reviewed'])
            fields['pl'].setPlainText('mama')
            self.assertFalse(dialog.selected()[0][1]['reviewed'])
            fields['pl'].clear()
            dialog._accept_selected()
            self.assertTrue(dialog._error.text())
        finally:
            dialog.close()


if __name__ == '__main__':
    unittest.main()
