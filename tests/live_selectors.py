"""Manual canary: do the userscript selectors still match the live dictionaries?

Run with Anki's Python (needs network, so it is not part of the unit suite):
    QT_QPA_PLATFORM=offscreen "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" tests/live_selectors.py

AI column:  OK = entry found. WHOLE = markup changed, AI gets the whole page (fix the rule).
            EMPTY = nothing extracted (CAPTCHA, timeout or broken rule).
Buttons:    OK = the searched word has a "→ hasło" button and other buttons exist.
            Inflected words (went) only need some headword button (often the lemma).
Exit code 1 unless everything is OK.
"""
import importlib.util
from pathlib import Path
import sys

from aqt.qt import QApplication, QEventLoop, QTimer, QUrl, QWebEnginePage, QWebEngineProfile, sip

ROOT = Path(__file__).resolve().parents[1]
WORDS = ["mother", "give up", "went"]  # plain word, phrasal verb, inflected form
INFLECTED = {"went"}
BUTTONS = """(() => {
  const all = [...document.querySelectorAll('.ankiBtn')];
  const heads = all.filter((b) => b.textContent === '→ hasło').map((b) =>
    (b.previousElementSibling ? b.previousElementSibling.textContent : '').replace(/\\s+/g, ' ').trim().toLowerCase());
  return {heads: heads, other: all.length - heads.length};
})()"""

spec = importlib.util.spec_from_file_location("word_queue_live", ROOT / "integrations/word_queue.py")
word_queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(word_queue)
SCRIPT = (ROOT / "integrations/dictionaries-to-anki.user.js").read_text(encoding="utf-8")


def wait(page_call, timeout_ms=20000):
    loop, out = QEventLoop(), []
    page_call(lambda *value: (out.append(value[0] if value else None), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return out[0] if out else None


def main():
    app = QApplication.instance() or QApplication(["live-selectors"])
    profile = QWebEngineProfile()
    page = QWebEnginePage(profile)
    failed = 0
    for word in WORDS:
        for label, url in word_queue.dict_urls(word, word_queue._DEFAULTS).items():
            def load(done, url=url):
                page.loadFinished.connect(done)
                page.load(QUrl(url))
            loaded = wait(load)
            page.loadFinished.disconnect()
            value = wait(lambda done: page.runJavaScript(
                SCRIPT + f"\nwindow.ankiDictionaryText({word!r})", done), 5000) if loaded else None
            if isinstance(value, dict):
                status = "WHOLE"
            elif isinstance(value, str) and value.strip():
                status = "OK"
            else:
                status = "EMPTY" if loaded else "EMPTY (load failed)"
            text = value.get("text", "") if isinstance(value, dict) else (value or "")
            buttons = (wait(lambda done: page.runJavaScript(BUTTONS, done), 5000) or {}) if loaded else {}
            heads = buttons.get("heads") or []
            if word in INFLECTED:  # the page may only point to the lemma ("past tense of go")
                ok_buttons = bool(heads)
            else:  # diki lists related phrases too; the searched word must have its own button
                ok_buttons = word in heads and (buttons.get("other") or 0) > 0
            failed += status != "OK" or not ok_buttons
            print(f"AI {status:8} przyciski {'OK' if ok_buttons else 'ZLE':3} {label:16} {word:8} "
                  f"{len(text):5} zn.  hasło={sorted(set(heads))} inne={int(buttons.get('other') or 0)}", flush=True)
    sip.delete(page)
    sip.delete(profile)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
