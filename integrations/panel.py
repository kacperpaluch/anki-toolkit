"""Dok przy oknie „Dodaj": słowniki wewnątrz Anki + kolejka słówek z n8n.

Bierze wiersz z DataTable (flag_column == false), wpisuje `Slowko` do pola
notatki i ładuje gotowe URL-e z kolumn (diki / Longman / Oxford) w QWebEngineView.
Do stron wstrzykiwany jest TEN SAM userscript, którego używasz w przeglądarce —
jego przyciski gadają z mostkiem web_bridge na 127.0.0.1:8767. Dzięki temu
istnieje jedna wersja skryptu, a nie dwie.
Skrypty samych stron działają tylko na zakładkach z `page_js`; userscript ma
własny świat JS i działa wszędzie.

Po dodaniu notatki (hook w __init__) wiersz jest odhaczany po `id`, ale panel
ZOSTAJE na słówku — jedno hasło bywa kilkoma kartami (kilka znaczeń).

Stan „zrobione" z n8n widać kolorem — szare to odhaczone — i zmienia się go
prawym klikiem albo przyciskiem „Oznacz jako zrobione". Nic nie znika z listy samo;
od chowania jest filtr „Niezrobione”.

Przyciski: „Oznacz jako zrobione" = odhacz w n8n + skok dalej (koniec z tym hasłem),
„Pomiń" = skok bez odhaczania (pominięcie).

Wybór słówka ładuje tylko widoczną zakładkę; pozostałe przy pierwszym wejściu.
Przechodzenie po liście to jedno zapytanie na słowo zamiast czterech (mniej
pamięci Chromium i rzadsza weryfikacja Cloudflare na Cambridge).
"""

import html
import logging
import random
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QBrush,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QKeySequence,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QShortcut,
    QSplitter,
    Qt,
    QTabWidget,
    QTimer,
    QUrl,
    QVBoxLayout,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    QWidget,
    QWebEngineView,
    sip,
)
from aqt.utils import askUser, tooltip

from ..common import clean_html_normalized, update_module_config
from . import bridge, word_queue
from .queue_state import QueueState

log = logging.getLogger(__name__)

# Ten sam plik, który wgrywasz do Tampermonkeya. Jedno źródło prawdy.
_USERSCRIPT_PATH = Path(__file__).resolve().parent / "dictionaries-to-anki.user.js"


def _age_key(row: dict):
    """Rosnąco = od najstarszego. `id` rośnie z każdym dopisanym wierszem, więc
    jest zarazem datą dodania."""
    return row.get("id") or 0

_profile = None  # jeden na proces — nazwany, więc ciasteczka (zgody RODO, logowanie) przeżywają restart


# Strona weryfikacji Cloudflare (Cambridge). Bez JS strony pokazuje tylko
# „Enable JavaScript and cookies to continue”.
_CHALLENGE_JS = ("document.documentElement.innerHTML.includes('_cf_chl_opt')"
                 " || !!document.querySelector('script[src*=\"/cdn-cgi/challenge-platform/\"]')")

# Userscript żyje w osobnym świecie JS: DOM i fetch() ma te same, ale działa także
# tam, gdzie skrypty samej strony są wyłączone (patrz `_DictTabs.__init__`).
_WORLD = 1  # QWebEngineScript.ScriptWorldId.ApplicationWorld; Qt bierze tu liczbę


def _dict_profile() -> QWebEngineProfile:
    global _profile
    if _profile is not None:
        return _profile
    _profile = QWebEngineProfile("ankitoolkit-dict", mw)
    script = QWebEngineScript()
    script.setName("dictionaries-to-anki")
    # The file carries the default port (it is also the Tampermonkey copy).
    port = bridge._bound_port or bridge._port()
    script.setSourceCode(_USERSCRIPT_PATH.read_text(encoding="utf-8").replace(
        f"http://{bridge.HOST}:{bridge.DEFAULT_PORT}", f"http://{bridge.HOST}:{port}"))
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    script.setWorldId(_WORLD)
    script.setRunsOnSubFrames(False)
    _profile.scripts().insert(script)
    return _profile


class _DictTabs(QTabWidget):
    """Zakładki ze słownikami. URL ładowany dopiero przy pierwszym wejściu w zakładkę."""

    def __init__(self, labels: list[str], page_js: list[str] = (), parent=None):
        super().__init__(parent)
        self._labels = list(labels)          # indeks zakładki → etykieta
        self._views: list[QWebEngineView] = []
        self._pending: dict[int, str] = {}   # indeks → URL czekający na pierwsze wejście
        self._page_js = set(page_js)
        self._challenged: set[int] = set()   # zakładki z JS włączonym tylko na weryfikację
        self._passed: dict[int, str] = {}    # indeks → URL, dla którego weryfikacja już była
        for index, label in enumerate(self._labels):
            view = QWebEngineView(self)
            view.setPage(QWebEnginePage(_dict_profile(), view))
            # Skrypty strony tylko na życzenie (`page_js`). QtWebEngine 6.11.2 wywraca
            # renderer na każdym zasobie w starym kodowaniu (windows-1250, ISO-8859-x),
            # a takie skrypty doładowują reklamy słowników: strona znikała po chwili.
            # Blokada samych reklam nie wystarcza — strony same się wtedy czyszczą.
            view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, label in page_js)
            view.renderProcessTerminated.connect(
                lambda status, code, i=index: self._renderer_died(i, status, code))
            view.loadFinished.connect(lambda _ok, i=index: self._after_load(i))
            self._views.append(view)
            self.addTab(view, label)
        self.currentChanged.connect(lambda _i: self._load_current())

    def _renderer_died(self, index: int, status, code: int) -> None:
        """Martwy renderer zostawia pusty, szary widok — powiedz to wprost."""
        url = self._views[index].url().toString()
        log.warning("word_queue: renderer zakładki %s padł (%s, kod %s) na %s",
                    self._labels[index], status.name, code, url)
        self._pending.setdefault(index, url)  # ponowne wejście w zakładkę wczyta ją od nowa
        self._set_challenge_js(index, False)

        def explain():  # poza sygnałem silnika
            if not sip.isdeleted(self):
                self._views[index].setHtml(
                    "<p style='font: 14px sans-serif; margin: 2em'>Silnik przeglądarki przerwał "
                    "wyświetlanie tej strony. Przejdź na inną zakładkę i wróć, żeby wczytać ją "
                    "ponownie.</p>")

        QTimer.singleShot(0, explain)

    def set_urls(self, urls: dict[str, str]) -> None:
        """urls: etykieta → URL. Brak/pusty URL = zakładka wyszarzona."""
        self._pending = {i: urls.get(label) or "" for i, label in enumerate(self._labels)}
        self._pending = {i: url for i, url in self._pending.items() if url}
        for i in range(len(self._labels)):
            enabled = i in self._pending
            self.setTabEnabled(i, enabled)
            if not enabled:
                self._views[i].load(QUrl("about:blank"))
        if not self._pending:
            return
        if not self.isTabEnabled(self.currentIndex()):
            self.setCurrentIndex(min(self._pending))
        self._load_current()  # reszta czeka w `_pending` na wejście w zakładkę

    def _load_current(self) -> None:
        self._start_load(self.currentIndex())

    def _start_load(self, index: int) -> None:
        url = self._pending.pop(index, None)
        if url:
            if index in self._challenged:  # nowe hasło nie dziedziczy JS po weryfikacji
                self._set_challenge_js(index, False)
            self._views[index].load(QUrl(url))

    def _set_challenge_js(self, index: int, enabled: bool) -> None:
        (self._challenged.add if enabled else self._challenged.discard)(index)
        if self._labels[index] not in self._page_js:
            self._views[index].settings().setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, enabled)

    def _after_load(self, index: int) -> None:
        """Weryfikacja Cloudflare potrzebuje JS. Włącz go tylko na jej czas,
        potem wczytaj stronę ponownie bez JS — ciasteczko z weryfikacji zostaje
        w profilu, więc kolejne hasła przechodzą od razu."""
        if self._labels[index] in self._page_js:
            return  # JS strony i tak działa, Cloudflare poradzi sobie sam
        view = self._views[index]
        url = view.url().toString()
        address = url.split("?")[0]  # Cloudflare dokleja do adresu własne tokeny

        def checked(challenge):
            QTimer.singleShot(0, lambda: react(bool(challenge)))  # poza callbackiem silnika

        def react(challenge):
            if sip.isdeleted(self) or view.url().toString() != url:
                return
            if index in self._challenged:
                if not challenge:  # weryfikacja przeszła, strona już jest
                    self._set_challenge_js(index, False)
                    view.reload()
            elif not challenge:
                self._passed.pop(index, None)  # wygasłe ciasteczko może później dostać nową próbę
            elif self._passed.get(index) != address:
                log.info("word_queue: weryfikacja Cloudflare na %s — JS tylko na jej czas", url)
                self._passed[index] = address  # jedna próba na adres, bez pętli
                self._set_challenge_js(index, True)
                view.reload()

        view.page().runJavaScript(_CHALLENGE_JS, _WORLD, checked)


class WordQueuePanel(QDockWidget):
    """Dok po prawej stronie okna „Dodaj". Żyje tak długo jak to okno."""


    def __init__(self, addcards, cfg: dict, fetch_queue, mark_row_done):
        super().__init__("Kolejka słówek", addcards)
        self._addcards = addcards
        self._cfg = cfg
        self._collection = mw.col
        self._state = QueueState(mw.col.path, cfg)
        self._fetch_queue = fetch_queue
        self._mark_row_done = mark_row_done
        self._marked: set = set()  # id wierszy już odhaczonych — PATCH tylko raz na wiersz
        self._done_count = 0
        self._suspend = False  # zmiany programowe nie udają kliknięć użytkownika
        self._pending: dict = {}  # one in-flight PATCH per row
        self._refill_generation = 0
        self._selection_generation = 0
        self._bound_note = None
        self._bound_row_id = None
        self._adding: set[str] = set()  # hasła w trakcie zapisu do n8n (casefold)
        self._added: dict = {}  # id → wiersz zapisany w n8n, zanim zobaczy go odświeżenie

        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.setWidget(self._build_ui())
        addcards.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        addcards.resizeDocks([self], [1100], Qt.Orientation.Horizontal)
        self.refill()

    def _save_state(self) -> bool:
        try:
            self._state.save()
            return True
        except Exception:
            log.exception("word_queue: nie zapisano pliku stanu")
            tooltip("Kolejka: nie zapisano pliku stanu — sprawdź Logi.", parent=mw)
            return False

    def _owe(self, rows: dict) -> bool:
        """Cards for these rows are (about to be) in the collection; n8n must hear about it."""
        self._state.data["owed"].update({str(row_id): word for row_id, word in rows.items()})
        return self._save_state()

    def _settle_owed(self) -> None:
        """After a refill: finish PATCHes lost to a crash or a network error."""
        listed = {(self._list.item(i).data(Qt.ItemDataRole.UserRole) or {}).get("id")
                  for i in range(self._list.count())}
        for key, word in list(self._state.data["owed"].items()):
            row_id = int(key)
            if row_id in self._marked or row_id not in listed:  # done, or row deleted in n8n
                del self._state.data["owed"][key]
                continue
            try:
                has_cards = bool(word_queue.find_word_notes(word, self._cfg))
            except Exception:
                log.exception("word_queue: nie sprawdzono kart dla %r", word)
                continue
            if has_cards:
                self._set_row(None, True, row_id=row_id)
            else:
                self._state.data["owed"].pop(key)  # crash before commit: nothing to report
        self._save_state()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self) -> QWidget:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)

        split = QSplitter(Qt.Orientation.Horizontal, root)
        sidebar = QWidget(split)
        sidebar.setMinimumWidth(310)
        queue = QVBoxLayout(sidebar)
        queue.setContentsMargins(0, 0, 6, 0)
        queue.addWidget(QLabel("<b>Słowa do opracowania</b>"))
        self._counter = QLabel("")
        queue.addWidget(self._counter)

        controls_widget = QWidget(sidebar)
        controls = QVBoxLayout(controls_widget)
        controls.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self._order = QComboBox()
        self._order.setToolTip("Kolejność słów na liście")
        for label, value in (("Od początku", "id"), ("Najnowsze", "new"), ("Losowo", "random")):
            self._order.addItem(label, value)
        index = self._order.findData(self._cfg.get("order") or "id")
        self._order.setCurrentIndex(index if index >= 0 else 0)
        self._order.currentIndexChanged.connect(lambda _i: self._on_order_changed())
        filters.addWidget(self._order, 1)
        self._status_filter = QComboBox()
        self._status_filter.setToolTip("Status hasła w n8n")
        for label, value in (("Wszystkie", "all"), ("Niezrobione", "todo"), ("Zrobione", "done")):
            self._status_filter.addItem(label, value)
        self._status_filter.setCurrentIndex(1)
        self._status_filter.currentIndexChanged.connect(lambda _index: self._apply_hiding())
        filters.addWidget(self._status_filter, 1)
        reload_btn = QPushButton("Odśwież")
        reload_btn.setToolTip("Pobierz kolejkę z n8n od nowa")
        reload_btn.clicked.connect(self.refill)
        filters.addWidget(reload_btn)
        controls.addLayout(filters)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Szukaj w kolejce…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _text: self._apply_hiding())
        controls.addWidget(self._search)

        adding = QHBoxLayout()
        self._word_input = QLineEdit()
        self._word_input.setPlaceholderText("Dodaj słowo — Enter")
        self._word_input.setToolTip("Kilka słów rozdziel przecinkiem. Zapis do kolejki wymaga połączenia z n8n.")
        self._word_input.returnPressed.connect(self._add_typed_word)
        adding.addWidget(self._word_input, 1)
        paste_btn = QPushButton("Wklej listę…")
        paste_btn.setToolTip("Dodaj do n8n wiele słów, po jednym na linię")
        paste_btn.clicked.connect(lambda _checked=False: self._paste_words())
        adding.addWidget(paste_btn)
        controls.addLayout(adding)
        queue.addWidget(controls_widget)

        self._queue_status = QLabel("")
        self._queue_status.setWordWrap(True)
        queue.addWidget(self._queue_status)
        self._list = QListWidget(sidebar)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._list_menu)
        queue.addWidget(self._list, 1)
        split.addWidget(sidebar)

        # Bieżące słowo nad słownikami: to ono jest w notatce i jego dotyczą przyciski obok.
        current = QWidget(split)
        side = QVBoxLayout(current)
        side.setContentsMargins(6, 0, 0, 0)
        bar = QHBoxLayout()
        self._word_title = QLabel("Wybierz słowo z listy")
        self._word_title.setTextFormat(Qt.TextFormat.PlainText)
        self._word_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        font = self._word_title.font()
        font.setPointSizeF(font.pointSizeF() * 1.45)
        font.setBold(True)
        self._word_title.setFont(font)
        bar.addWidget(self._word_title, 1)
        manual_controls = QWidget(current)
        manual = QHBoxLayout(manual_controls)
        manual.setContentsMargins(0, 0, 0, 0)
        done_btn = QPushButton("Oznacz jako zrobione")
        done_btn.setToolTip("Oznacz bieżące słowo w n8n i przejdź dalej. Nie tworzy kart. Skrót: D na liście.")
        done_btn.clicked.connect(lambda _checked=False: self._done_and_next())
        manual.addWidget(done_btn)
        next_btn = QPushButton("Pomiń")
        next_btn.setToolTip("Przejdź do następnego słowa bez oznaczania w n8n. Skrót: S na liście.")
        next_btn.clicked.connect(lambda _checked=False: self.advance())
        manual.addWidget(next_btn)
        bar.addWidget(manual_controls)
        side.addLayout(bar)
        self._tabs = _DictTabs(word_queue.dict_labels(self._cfg), self._cfg.get("page_js") or [], current)
        side.addWidget(self._tabs, 1)
        split.addWidget(current)

        # Skróty tylko przy fokusie na liście — w polach tekstowych litery mają się wpisywać,
        # a Ctrl+Enter należy do „Dodaj”. Strzałki działają w Qt same.
        for key, button in ((Qt.Key.Key_D, done_btn), (Qt.Key.Key_S, next_btn)):
            shortcut = QShortcut(QKeySequence(key), self._list)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(button.click)  # click() nic nie robi, gdy przycisk wyłączony
        split.setStretchFactor(1, 1)
        split.setSizes([330, 770])
        layout.addWidget(split, 1)

        return root

    # -- kolejka ------------------------------------------------------------

    def _current_row(self) -> dict | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    _shown_word = ""  # hasło aktualnie w zakładkach; chroni przed zbędnym przeładowaniem

    def _show_urls(self, word: str, row: dict | None) -> None:
        self._word_title.setText(word)
        if word == self._shown_word:
            return  # paczka z jednym hasłem nie przeładowuje tego, co już widać
        self._shown_word = word
        self._tabs.set_urls(word_queue.dict_urls(word, self._cfg, row))

    def _add_typed_word(self) -> None:
        """Enter w polu obok listy: dopisz hasło (albo kilka po przecinku)."""
        self._add_words(word_queue.parse_words(self._word_input.text()))
        self._word_input.clear()

    def _paste_words(self) -> None:
        """Przycisk „+ lista": okno na wklejenie kolumny haseł, po jednym na linię."""
        text, accepted = QInputDialog.getMultiLineText(
            self, "Własne hasła", "Po jednym na linię (albo po przecinku):")
        if accepted:
            self._add_words(word_queue.parse_words(text))

    def _add_words(self, words: list[str]) -> None:
        """Dopisz hasła do tabeli n8n i na koniec listy; skocz na pierwsze z nich.

        Hasło, które już jest na liście, pomijamy — panel trzyma CAŁĄ tabelę,
        więc to jest zarazem kontrola duplikatów w n8n, bez dodatkowego zapytania.

        Gdy n8n nie przyjmie zapisu, hasła wracają do pola „własne hasło”, żeby
        nie przepadły — ponowienie to Enter (po „Odśwież”, jeśli zapis był niepewny).
        """
        if not words:
            return
        column = self._cfg["word_column"]
        rows = [self._list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self._list.count())]
        # Hasło już na liście (z n8n albo dopisane wcześniej) nie dostaje drugiego
        # wiersza — od kilku znaczeń jednego hasła jest jedna pozycja, nie kopia.
        # Do porównania dokładamy hasła, których zapis jeszcze trwa: przed
        # odpowiedzią n8n nie ma ich na liście, więc drugie wklejenie tego samego
        # słowa zapisałoby duplikat do tabeli.
        known = {clean_html_normalized(row.get(column) or "").casefold() for row in rows}
        known |= self._adding
        known |= {clean_html_normalized(row.get(column) or "").casefold() for row in self._added.values()}
        fresh, skipped = [], []
        for word in words:
            if word.casefold() in known:
                skipped.append(word)
                continue
            known.add(word.casefold())
            fresh.append(word)
        if skipped:
            shown = ", ".join(skipped[:8]) + (f" (+{len(skipped) - 8})" if len(skipped) > 8 else "")
            tooltip(f"Już na liście, pominięto: {shown}", parent=mw, period=4000)
        if not fresh:
            self._select_word(skipped[0] if skipped else "")
            return
        self._adding |= {word.casefold() for word in fresh}

        def done(future):
            try:
                saved, error = future.result()
            except Exception:  # noqa: BLE001
                log.exception("word_queue: dopisywanie wierszy rzuciło wyjątkiem")
                saved, error = [], "wyjątek (szczegóły w Logach)"
            if sip.isdeleted(self):
                if error:
                    tooltip(f"n8n: {error}. Nie zapisano: {', '.join(fresh)}", parent=mw, period=8000)
                return
            self._adding -= {word.casefold() for word in fresh}
            if error:
                tooltip(f"n8n: {error}. Hasła wróciły do pola „własne hasło”.",
                        parent=mw, period=8000)
                typed = self._word_input.text().strip()
                self._word_input.setText(", ".join(([typed] if typed else []) + fresh))
                return
            self._added.update({row["id"]: row for row in saved})
            if mw.col is self._collection:
                self._append_rows(saved)

        mw.taskman.run_in_background(
            lambda: word_queue.add_rows(fresh, self._cfg), done,
            uses_collection=False)

    def _append_rows(self, fresh: list[dict]) -> None:
        if not fresh:
            return
        rows = [self._list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._list.count())]
        self._rebuild(self._ordered(rows + fresh))
        self._select_word(fresh[0][self._cfg["word_column"]])

    def _select_word(self, word: str) -> None:
        """Skocz na pozycję z tym hasłem, jeśli jest widoczna."""
        if not word:
            return
        column = self._cfg["word_column"]
        for i in range(self._list.count()):
            row = self._list.item(i).data(Qt.ItemDataRole.UserRole)
            if clean_html_normalized(row.get(column) or "").casefold() == word.casefold():
                self._list.setCurrentRow(i)
                return

    def current_row_id(self):
        row = self._current_row()
        return row.get("id") if row else None

    def refill(self) -> None:
        """Pobierz świeżą paczkę wierszy z flag_column == false i zbuduj listę."""
        if self._pending:
            tooltip("n8n: poczekaj na zakończenie zapisu wierszy.", parent=mw)
            return
        self._refill_generation += 1
        generation = self._refill_generation
        self._queue_status.setText("Pobieranie kolejki z n8n…")
        def done(future):
            if sip.isdeleted(self) or generation != self._refill_generation:
                return
            try:
                rows, error = future.result()
            except Exception:
                log.exception("word_queue: pobieranie kolejki rzuciło wyjątkiem")
                self._queue_status.setText("Nie pobrano kolejki. Spróbuj ponownie przez Odśwież.")
                return
            if error:
                self._queue_status.setText(f"Nie pobrano kolejki z n8n: {error}. Spróbuj przez Odśwież.")
                tooltip(f"n8n: nie pobrano kolejki — {error}", parent=mw, period=5000)
                return
            if sip.isdeleted(self):
                return  # okno „Dodaj" zamknięte, zanim n8n odpowiedział
            # Stan bierzemy z tabeli, nie z pamięci sesji — po „Odśwież" zrobione
            # wciąż są na liście (schowane), więc pomyłkę da się cofnąć.
            self._marked = {r["id"] for r in rows if r.get(self._cfg["flag_column"])}
            # A GET that started before our POST does not know the new rows yet.
            fetched = {row["id"] for row in rows}
            for row_id in fetched & set(self._added):
                del self._added[row_id]
            late = [row for row_id, row in self._added.items() if row_id not in fetched]
            self._done_count = 0  # licznik jest per sesja, nie per tabela
            self._rebuild(self._ordered(rows + late))
            self._queue_status.setText("" if rows or late else "Kolejka jest pusta. Dodaj słowo lub wklej listę.")
            self._settle_owed()

        mw.taskman.run_in_background(lambda: self._fetch_queue(self._cfg), done,
                                     uses_collection=False)

    def _rebuild(self, rows: list[dict]) -> None:
        """Przebuduj listę z podanych wierszy, zachowując wygląd odhaczonych."""
        selected_id = self.current_row_id()
        self._selection_generation += 1
        with self._silent():  # programowa zmiana bieżącej pozycji to nie klik użytkownika
            self._list.clear()
            for row in rows:
                self._list.addItem(self._make_item(row))
        self._apply_hiding()
        self._update_counter()
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole).get("id") == selected_id:
                with self._silent():
                    self._list.setCurrentRow(i)
                return
        self._bound_note = self._bound_row_id = None
        self._select_first_visible()  # odpala _on_item_changed → prefill + zakładki

    def _select_first_visible(self) -> None:
        """Nie zaczynaj od zrobionego słówka, gdy zrobione są schowane."""
        for i in range(self._list.count()):
            if not self._list.item(i).isHidden():
                self._list.setCurrentRow(i)
                return

    def _make_item(self, row: dict) -> QListWidgetItem:
        """Zrobione widać kolorem."""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, row)  # _style_item czyta stąd hasło
        self._style_item(item)
        return item

    def _on_order_changed(self) -> None:
        """Przestaw kolejność OD RAZU, nie dopiero przy następnym pobraniu —
        inaczej rozwijanka wygląda na zepsutą. Wybór przeżywa restart."""
        order = self._order.currentData()
        self._cfg["order"] = order
        update_module_config("word_queue", {"order": order})
        self._rebuild(self._ordered(
            [self._list.item(i).data(Qt.ItemDataRole.UserRole)
             for i in range(self._list.count())]))

    def _ordered(self, rows: list[dict]) -> list[dict]:
        """Ułóż wiersze zgodnie z wybraną kolejnością."""
        rows = sorted(rows, key=_age_key)
        order = self._cfg.get("order") or "id"
        if order == "new":
            rows.reverse()
        elif order == "random":
            random.shuffle(rows)
        return rows

    def _list_menu(self, point) -> None:
        """Prawy klik: przełącz stan „zrobione" w n8n."""
        item = self._list.itemAt(point)
        if item is None:
            return
        row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
        menu = QMenu(self)
        done = row_id in self._marked
        toggle = menu.addAction("Cofnij odhaczenie" if done else "Oznacz jako zrobione")
        toggle.triggered.connect(lambda _checked=False: self._set_row(item, not done))
        menu.exec(self._list.mapToGlobal(point))

    def _done_and_next(self) -> None:
        """Przycisk „Zrobione”: odhacz bieżące słówko w n8n i przejdź dalej.

        Nawigujemy od razu — PATCH leci w tle, a gdyby padł, styl wróci do
        „do zrobienia".
        """
        item = self._list.currentItem()
        if item is None:
            return
        self._set_row(item, True)
        self.advance()

    def _set_row(self, item: QListWidgetItem | None, done: bool, row_id=None) -> None:
        """Zapisz stan „zrobione" w n8n. Przy błędzie cofa kolor — lista ma
        mówić prawdę o tabeli."""
        if item is not None:
            row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
        if row_id is None:
            return
        if row_id in self._pending:
            return
        previous = row_id in self._marked
        if previous == done:
            if item is not None:
                self._style_item(item)
            return
        self._refill_generation += 1  # an older GET must not overwrite this PATCH
        self._pending[row_id] = done
        if item is not None:
            self._style_item(item)

        def finished(future):
            try:
                matched, error = future.result()
                if not error and matched != 1:
                    error = f"oczekiwano 1 wiersza, zmieniono {matched}; odśwież kolejkę"
            except Exception:
                log.exception("word_queue: PATCH rzucił wyjątkiem")
                error = "wyjątek (szczegóły w Logach)"
            self._pending.pop(row_id, None)
            if sip.isdeleted(self) or mw.col is not self._collection:
                return  # `owed` stays on disk; the next panel retries after refill
            if not error:
                # Success either way settles the debt: done is reported, undone was a manual choice.
                self._state.data["owed"].pop(str(row_id), None)
                self._save_state()
            if error:
                tooltip(f"n8n: nie zapisano wiersza {row_id} — {error}", parent=mw, period=5000)
            else:
                self._marked.add(row_id) if done else self._marked.discard(row_id)
                self._done_count += 1 if done else -1
            # Shuffle may have rebuilt the QListWidget while HTTP was running.
            for i in range(self._list.count()):
                current = self._list.item(i)
                if current.data(Qt.ItemDataRole.UserRole).get("id") == row_id:
                    self._style_item(current)
            self._apply_hiding()
            self._update_counter()

        try:
            mw.taskman.run_in_background(
                lambda: self._mark_row_done(row_id, self._cfg, done), finished,
                uses_collection=False,
            )
        except Exception as error:
            failed = Future()
            failed.set_exception(error)
            finished(failed)

    def _style_item(self, item: QListWidgetItem) -> None:
        """Szare = zrobione w n8n."""
        row = item.data(Qt.ItemDataRole.UserRole) or {}
        row_id = row.get("id")
        done = self._pending.get(row_id, row_id in self._marked)
        word = row.get(self._cfg["word_column"]) or "—"
        with self._silent():
            waiting = str(row_id) in self._state.data["owed"] and row_id not in self._marked
            item.setText(word + (" · karty są, czeka n8n" if waiting else ""))
            # Rola = None przywraca domyślny wygląd motywu (jasny i ciemny).
            item.setData(Qt.ItemDataRole.ForegroundRole,
                         QBrush(Qt.GlobalColor.gray) if done else None)

    @contextmanager
    def _silent(self):
        """Zmiany programowe nie mogą udawać kliknięć użytkownika. Zagnieżdżalne."""
        previous = self._suspend
        self._suspend = True
        try:
            yield
        finally:
            self._suspend = previous

    def _apply_hiding(self) -> None:
        status = self._status_filter.currentData()
        query = self._search.text().strip().casefold()
        for i in range(self._list.count()):
            item = self._list.item(i)
            row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
            row = item.data(Qt.ItemDataRole.UserRole) or {}
            word = clean_html_normalized(row.get(self._cfg["word_column"]) or "").casefold()
            done = row_id in self._marked
            item.setHidden((status == "todo" and done) or (status == "done" and not done)
                           or query not in word)

    def advance(self) -> None:
        """Następna WIDOCZNA pozycja. Nic nie odhacza."""
        for i in range(self._list.currentRow() + 1, self._list.count()):
            if not self._list.item(i).isHidden():
                self._list.setCurrentRow(i)
                return

    def _on_item_changed(self, current: QListWidgetItem, previous) -> None:
        """Zmiana pozycji (klik lub strzałki) → wpisanie hasła i słowniki.

        Odkładamy o obrót pętli zdarzeń: odmowa zastąpienia hasła cofa bieżącą
        pozycję, a tego nie robi się z wnętrza sygnału zmiany pozycji.
        """
        if self._suspend or current is None:
            return
        QTimer.singleShot(0, lambda: self._apply_selection(current, previous))

    def _apply_selection(self, current: QListWidgetItem, previous) -> None:
        if sip.isdeleted(self) or self._suspend or sip.isdeleted(current):
            return
        if self._list.currentItem() is not current:
            return  # zaznaczenie poszło dalej, zanim doszliśmy do tej pozycji
        row = current.data(Qt.ItemDataRole.UserRole)
        word = row.get(self._cfg["word_column"]) or ""
        def ready(accepted):
            if accepted:
                self._show_urls(word, row)
            else:
                with self._silent():
                    self._list.setCurrentItem(previous if previous is not None and not sip.isdeleted(previous) else None)
        self._prefill(word, ready, confirm=True)

    def note_added(self, note) -> None:
        """Hook po dodaniu notatki: odhacz wiersz, ale ZOSTAŃ na słówku.

        Bez przeskoku, bo jedno hasło bywa kilkoma kartami (kilka znaczeń).
        Kolejne dodania nie wołają n8n ponownie — `_marked` pilnuje jednego PATCH-a.
        """
        row = self._current_row()
        if row is None or note is not self._bound_note or row.get("id") != self._bound_row_id:
            return
        field = self._cfg["word_field"]
        word = row.get(self._cfg["word_column"]) or ""
        if field not in note or clean_html_normalized(note[field]).casefold() != clean_html_normalized(word).casefold():
            tooltip("n8n: inne hasło — wiersz nie został odhaczony. Użyj „Oznacz jako zrobione”, jeśli to ta sama pozycja.", parent=mw)
            return

        # Anki wczytało już pustą notatkę (_load_new_note leci przed hookiem),
        # więc wpisujemy hasło z powrotem — gotowe na kolejne znaczenie.
        self._prefill(word)

        row_id = row.get("id")
        if row_id is None or row_id in self._marked or row_id in self._pending:
            return
        self._owe({row_id: word})
        item = self._list.currentItem()
        if item is not None:
            self._set_row(item, True)

    def _update_counter(self) -> None:
        left = sum((self._list.item(i).data(Qt.ItemDataRole.UserRole) or {}).get("id") not in self._marked
                   for i in range(self._list.count()))
        self._counter.setText(f"Pozostało: {left} · Zrobione w tej sesji: {self._done_count}")

    # -- pomocnicze ---------------------------------------------------------

    def _prefill(self, word: str, after=None, confirm=False) -> None:
        """Flush unsaved fields before changing the headword; reject stale callbacks."""
        editor = self._addcards.editor
        note = editor.note
        collection = mw.col
        self._selection_generation += 1
        generation = self._selection_generation
        field = self._cfg["word_field"]
        if note is None or field not in note:
            if after:
                after(False)
            return

        def valid():
            return (not sip.isdeleted(self) and generation == self._selection_generation
                    and mw.col is collection and editor.note is note
                    and editor.web is not None and not sip.isdeleted(editor.web))

        def saved():
            if not valid():
                return
            existing = clean_html_normalized(note[field])
            # Pytamy tylko wtedy, gdy JEST co stracić, czyli gdy notatka jest
            # naprawdę rozpoczęta: samo hasło wpisał tu panel przy poprzednim
            # kliknięciu, więc pytanie o nie broniłoby własnego tekstu i wyskakiwało
            # przy każdym przejściu po liście.
            started = any(clean_html_normalized(value)
                          for name, value in note.items() if name != field)
            if confirm and started and existing and existing != clean_html_normalized(word):
                accepted = askUser(f"Zastąpić hasło „{existing}” przez „{word}” w rozpoczętej notatce? Pozostałe pola pozostaną bez zmian.", parent=self)
                if not valid():
                    return
                if not accepted:
                    if after:
                        after(False)
                    return
            note[field] = html.escape(word, quote=False)  # n8n holds plain text
            self._bound_note = note
            self._bound_row_id = self.current_row_id()
            editor.loadNote()
            if after:
                after(True)

        editor.saveNow(saved)
