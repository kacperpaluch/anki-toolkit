"""Manual canary: do the panel's dictionary tabs still load and yield entries?

Drives the real `integrations.panel._DictTabs` — same profile, userscript world and
`page_js` setting as the Add window — against the live dictionaries. Run it after an
Anki update, with the Qt that Anki ships (needs network, so not part of the unit suite):
    QT_QPA_PLATFORM=offscreen PYTHONPATH=/Applications/Anki.app/Contents/Resources/app_packages \\
        python3.13 tests/live_selectors.py 2>/dev/null   # stderr is Chromium noise

AI column:  OK = entry items found (diki: meanings, others: definitions).
            EMPTY = nothing extracted (CAPTCHA, timeout, broken rule, page needs its scripts).
            PADŁ = the renderer process crashed on this page.
Buttons:    OK = the searched word has a "→ hasło" button and other buttons exist.
            Inflected words (went) only need some headword button (often the lemma).
Exit code 1 unless everything is OK.
"""
import importlib
from pathlib import Path
import sys
import types

from aqt.qt import QApplication, QEventLoop, QTimer, sip

ROOT = Path(__file__).resolve().parents[1]
WORDS = ["mother", "give up", "went"]  # plain word, phrasal verb, inflected form
INFLECTED = {"went"}
BUTTONS = """(() => {
  const all = [...document.querySelectorAll('.ankiBtn')];
  const heads = all.filter((b) => b.textContent === '→ hasło').map((b) =>
    (b.previousElementSibling ? b.previousElementSibling.textContent : '').replace(/\\s+/g, ' ').trim().toLowerCase());
  return {heads: heads, other: all.length - heads.length};
})()"""


def wait(call, timeout_ms=20000):
    loop, out = QEventLoop(), []
    call(lambda *value: (out.append(value[0] if value else None), loop.quit()))
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return out[0] if out else None


def main():
    app = QApplication.instance() or QApplication(["live-selectors"])
    # The repository root is the add-on package; a bare stand-in avoids its menu wiring.
    package = types.ModuleType("live_addon")
    package.__path__ = [str(ROOT)]
    sys.modules["live_addon"] = package
    panel = importlib.import_module("live_addon.integrations.panel")
    word_queue = panel.word_queue
    cfg = word_queue._DEFAULTS
    labels = word_queue.dict_labels(cfg)
    tabs = panel._DictTabs(labels, cfg["page_js"])
    tabs.resize(900, 700)
    tabs.show()
    crashed = set()
    for index, view in enumerate(tabs._views):
        view.renderProcessTerminated.connect(lambda *_a, i=index: crashed.add(i))
    failed = 0
    for word in WORDS:
        crashed.clear()
        tabs.set_urls(word_queue.dict_urls(word, cfg), word)
        entries = wait(tabs.entries, 30000) or {}
        for index, label in enumerate(labels):
            items = entries.get(label) or []
            status = "PADŁ" if index in crashed else "OK" if items else "EMPTY"
            buttons = wait(lambda done, i=index: tabs._views[i].page().runJavaScript(
                BUTTONS, panel._WORLD, done), 5000) or {}
            heads = buttons.get("heads") or []
            if word in INFLECTED:  # the page may only point to the lemma ("past tense of go")
                ok_buttons = bool(heads)
            else:  # diki lists related phrases too; the searched word must have its own button
                ok_buttons = word in heads and (buttons.get("other") or 0) > 0
            # An inflected form's page may only point to the lemma ("past tense of go").
            failed += (status != "OK" and word not in INFLECTED) or not ok_buttons
            js = "JS" if label in cfg["page_js"] else "  "
            print(f"AI {status:8} przyciski {'OK' if ok_buttons else 'ZLE':3} {js} {label:16} {word:8} "
                  f"{len(items):3} poz.  hasło={sorted(set(heads))} inne={int(buttons.get('other') or 0)}", flush=True)
    sip.delete(tabs)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
