"""reader — okno lokalnego słownika StarDict, niezależne od kolejki n8n.

Czytnik to zwykła strona z mostka (`GET /dict`), więc okno jest cienkie: widok
WWW i nawigacja. Działa bez konfiguracji n8n i bez panelu 📚 — wystarczy baza
`user_files/stardict.sqlite`. Wstawianie znaczeń do notatki wymaga otwartego
okna „Dodaj", bo tam pisze mostek; samo czytanie nie wymaga niczego.
"""

from urllib.parse import quote

from aqt import mw
from aqt.qt import QKeySequence, QShortcut, QUrl, QVBoxLayout, QWebEngineView, QWidget, Qt, sip

from . import local_dict

_window = None  # jedno okno na profil — kolejne wywołania tylko nawigują


class Reader(QWidget):
    def __init__(self):
        super().__init__(mw, Qt.WindowType.Window)
        self.setWindowTitle("Słownik lokalny")
        self.resize(760, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        layout.addWidget(self.view)
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)

    def go(self, word: str = "") -> None:
        port = (mw.addonManager.getConfig(__package__) or {}).get("web_bridge", {}).get("port") or 8767
        self.view.load(QUrl(f"http://127.0.0.1:{port}/dict?word={quote((word or '').strip())}"))


def open_reader(word: str = "") -> None:
    global _window
    if _window is None or sip.isdeleted(_window):
        _window = Reader()
    _window.go(word)
    _window.show()
    _window.raise_()
    _window.activateWindow()


def open_for_editor(editor) -> None:
    """Z edytora: podpowiedz hasłem z pola notatki, jeśli jakieś już wpisano."""
    field = (mw.addonManager.getConfig(__package__) or {}).get("word_queue", {}).get("word_field") or "ang"
    note = getattr(editor, "note", None)
    word = ""
    if note is not None and field in note:
        from .html import clean_html_normalized
        word = clean_html_normalized(note[field])
    open_reader(word)


def on_editor_buttons_init(buttons, editor):
    """Przycisk 📖 w edytorze — także w przeglądarce kart, czytnik nie potrzebuje okna „Dodaj"."""
    buttons.append(editor.addButton(icon=None, cmd="local_dict_reader",
                                    func=lambda ed=editor: open_for_editor(ed),
                                    tip="Słownik lokalny (StarDict)", label="📖"))
    return buttons
