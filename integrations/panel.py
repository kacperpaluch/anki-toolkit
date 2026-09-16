"""Dok przy oknie „Dodaj": słowniki wewnątrz Anki + kolejka słówek z n8n.

Bierze wiersz z DataTable (flag_column == false), wpisuje `Slowko` do pola
notatki i ładuje gotowe URL-e z kolumn (diki / Longman / Oxford) w QWebEngineView.
Do stron wstrzykiwany jest TEN SAM userscript, którego używasz w przeglądarce —
jego przyciski gadają z mostkiem web_bridge na 127.0.0.1:8767. Dzięki temu
istnieje jedna wersja skryptu, a nie dwie.

Po dodaniu notatki (hook w __init__) wiersz jest odhaczany po `id`, ale panel
ZOSTAJE na słówku — jedno hasło bywa kilkoma kartami (kilka znaczeń).

Ptaszek przy słówku to WYBÓR DO AI, nie stan tabeli: zbierasz nim hasła przez
całą listę, bo przewijanie i klikanie gdzie indziej go nie gubią (a podświetlenie
tak). Stan „zrobione" z n8n widać kolorem — szare to odhaczone — i zmienia się
go prawym klikiem albo przyciskiem „Zrobione →". Nic nie znika z listy samo;
od chowania jest „Ukryj zrobione".

Przyciski: „Zrobione →" = odhacz w n8n + skok dalej (koniec z tym hasłem),
„Następne" = skok bez odhaczania (pominięcie).

Wybór słówka ładuje WSZYSTKIE zakładki naraz (dwa słowniki PL, trzy EN —
Cambridge liczy się do obu). Kosztuje to pamięć, bo Chromium bierze ~100 MB na
zakładkę, ale „AI: znaczenia" i tak czyta komplet, a przy przeglądaniu ręcznym
nie czekasz na wczytanie po każdym kliknięciu w zakładkę.
"""

import json
import logging
import random
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QBrush,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFont,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSplitter,
    Qt,
    QTabWidget,
    QTimer,
    QUrl,
    QVBoxLayout,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWidget,
    QWebEngineView,
    sip,
)
from aqt.utils import askUser, tooltip

from ..common import clean_html_normalized, update_module_config
from . import ai_senses, word_queue
from .queue_state import QueueState

log = logging.getLogger(__name__)

# Ten sam plik, który wgrywasz do Tampermonkeya. Jedno źródło prawdy.
_USERSCRIPT_PATH = Path(__file__).resolve().parent / "dictionaries-to-anki.user.js"

# Powyżej tylu haseł naraz pytamy — paczka to tyle samo pytań do modelu, a przy
# lokalnym CLI tyle samo procesów. Próg, nie limit.
_BATCH_ASK = 10


def _age_key(row: dict):
    """Rosnąco = od najstarszego. `id` rośnie z każdym dopisanym wierszem, więc
    jest zarazem datą dodania. Wiersze lokalne (ujemne id) są najnowsze."""
    row_id = row.get("id") or 0
    return (1, -row_id) if row_id < 0 else (0, row_id)

_profile = None  # jeden na proces — nazwany, więc ciasteczka (zgody RODO, logowanie) przeżywają restart


def _dict_profile() -> QWebEngineProfile:
    global _profile
    if _profile is not None:
        return _profile
    _profile = QWebEngineProfile("ankitoolkit-dict", mw)
    script = QWebEngineScript()
    script.setName("dictionaries-to-anki")
    script.setSourceCode(_USERSCRIPT_PATH.read_text(encoding="utf-8"))
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    # MainWorld, bo skrypt musi widzieć fetch() i DOM strony. W izolowanym
    # świecie nie dopiąłby przycisków ani nie dobił się do mostka.
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setRunsOnSubFrames(False)
    _profile.scripts().insert(script)
    return _profile


class _DictTabs(QTabWidget):
    """Zakładki ze słownikami. URL ładowany dopiero przy pierwszym wejściu w zakładkę."""

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._labels = list(labels)          # indeks zakładki → etykieta
        self._views: list[QWebEngineView] = []
        self._pending: dict[int, str] = {}   # indeks → URL czekający na pierwsze wejście
        self._loaded: dict[int, bool | None] = {}
        self._generation = 0
        self._word = ""
        self.whole_page: set[str] = set()  # labels whose selectors found no entry
        for index, label in enumerate(self._labels):
            view = QWebEngineView(self)
            view.setPage(QWebEnginePage(_dict_profile(), view))
            view.loadStarted.connect(lambda i=index: self._loaded.__setitem__(i, None))
            view.loadFinished.connect(lambda ok, i=index: self._loaded.__setitem__(i, ok))
            self._views.append(view)
            self.addTab(view, label)
        self.currentChanged.connect(lambda _i: self._load_current())

    def set_urls(self, urls: dict[str, str], word: str = "") -> None:
        """urls: etykieta → URL. Brak/pusty URL = zakładka wyszarzona."""
        self._generation += 1
        self._word = word
        self._pending = {i: urls.get(label) or "" for i, label in enumerate(self._labels)}
        self._pending = {i: url for i, url in self._pending.items() if url}
        self._loaded = {}  # nowe hasło — stary tekst stron przestał obowiązywać
        for i in range(len(self._labels)):
            enabled = i in self._pending
            self.setTabEnabled(i, enabled)
            if not enabled:
                self._views[i].load(QUrl("about:blank"))
        if not self._pending:
            return
        if not self.isTabEnabled(self.currentIndex()):
            self.setCurrentIndex(min(self._pending))
        # Wszystkie słowniki naraz, zaczynając od widocznego. „AI: znaczenia"
        # i tak czyta komplet przy każdym haśle, więc ładowanie na żądanie
        # tylko przesuwało ten koszt na moment, w którym czekasz na model.
        self._load_current()
        for index in list(self._pending):
            self._start_load(index)

    def _load_current(self) -> None:
        self._start_load(self.currentIndex())

    def _start_load(self, index: int) -> None:
        url = self._pending.pop(index, None)
        if url:
            self._loaded[index] = None
            self._views[index].load(QUrl(url))

    def _enabled(self) -> list[int]:
        """Zakładki, z których zbieramy tekst dla AI."""
        return [i for i in range(len(self._labels)) if self.isTabEnabled(i)]

    def texts(self, callback, timeout_ms: int = 20000) -> None:
        """{etykieta: tekst strony} dla włączonych zakładek — do promptu AI.

        Zakładki ruszają już przy wyborze słówka, więc zwykle jest na co czekać,
        a nie co zaczynać. Dociąganie zostaje na wypadek zakładki, która z
        jakiegoś powodu nie ruszyła. Ta, która nie dojedzie w `timeout_ms`, jest
        pomijana — lepszy prompt z dwóch słowników niż przycisk, który nie oddaje.

        ponytail: odpytujemy timerem zamiast pilnować sygnałów loadFinished na
        krzyż. Ćwierć sekundy opóźnienia przy akcji, która i tak trwa sekundy.
        """
        for index in self._enabled():
            self._start_load(index)
        remaining = [timeout_ms]
        generation = self._generation

        def ready():
            if sip.isdeleted(self) or generation != self._generation:
                return
            if any(self._loaded.get(i) is None for i in self._enabled()) and remaining[0] > 0:
                remaining[0] -= 250
                QTimer.singleShot(250, ready)
                return
            self._collect(callback)

        ready()

    def _collect(self, callback) -> None:
        """Zbierz tekst stron i oddaj go JUŻ POZA callbackiem silnika.

        `runJavaScript` woła nas ze środka QtWebEngine, a wywołujący robi tam
        rzeczy, których w cudzym callbacku robić nie wypada: `load()` na tym
        samym widoku (paczka przechodzi do kolejnego hasła) i modalne okno
        wyboru. Jedno odbicie przez pętlę zdarzeń zdejmuje to z wszystkich
        wywołujących `texts()` naraz. Higiena, nie znana awaria.
        """
        indexes = [i for i in self._enabled() if self._loaded.get(i)]
        generation = self._generation
        if not indexes:
            QTimer.singleShot(0, lambda: None if sip.isdeleted(self) or generation != self._generation else callback({}))
            return
        result: dict[str, str] = {}
        whole: set[str] = set()
        missing = [len(indexes)]
        returned = [False]

        def finish():
            if returned[0] or sip.isdeleted(self) or generation != self._generation:
                return
            returned[0] = True
            self.whole_page = whole
            callback(result)

        # A stalled renderer may never answer runJavaScript, even after loadFinished.
        QTimer.singleShot(5000, finish)

        def got(text, label):
            if returned[0]:
                return
            if isinstance(text, dict):  # userscript fell back to the whole page
                text = text.get("text")
                whole.add(label)
            if isinstance(text, str) and text.strip():
                result[label] = text
            missing[0] -= 1
            if missing[0] == 0 and not sip.isdeleted(self):
                QTimer.singleShot(0, finish)

        for index in indexes:
            self._views[index].page().runJavaScript(
                "typeof window.ankiDictionaryText === 'function' ? window.ankiDictionaryText("
                + json.dumps(self._word) + ") : ''",
                lambda text, label=self._labels[index]: got(text, label)
            )


class WordQueuePanel(QDockWidget):
    """Dok po prawej stronie okna „Dodaj". Żyje tak długo jak to okno."""


    def __init__(self, addcards, cfg: dict, fetch_queue, mark_row_done):
        super().__init__("Kolejka słówek", addcards)
        self._addcards = addcards
        self._cfg = cfg
        self._collection = mw.col
        self._state = QueueState(mw.col.path, cfg)
        self._stop_requested = False
        self._fetch_queue = fetch_queue
        self._mark_row_done = mark_row_done
        self._marked: set = {r["id"] for r in self._state.data["local_rows"] if r.get(cfg["flag_column"])}  # id wierszy już odhaczonych — PATCH tylko raz na wiersz
        self._picked: set = set()  # id zaptaszkowanych do AI; wyłącznie stan panelu
        self._done_count = 0
        self._suspend = False  # blokuje itemChanged przy zmianach programowych
        self._pending: dict = {}  # one in-flight PATCH per row
        self._refill_generation = 0
        self._selection_generation = 0
        self._bound_note = None
        self._bound_row_id = None
        self._local_rows: list[dict] = self._state.data["local_rows"]  # hasła spoza n8n; ujemne id
        self._adding: set[str] = set()  # hasła w trakcie zapisu do n8n (casefold)
        self._next_local_id = min([0] + [row["id"] for row in self._local_rows])  # zapasowe, ujemne id; nigdy nie wraca do użytku
        self._busy = False  # paczka AI w toku — nic nie przebudowuje listy

        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.setWidget(self._build_ui())
        addcards.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        addcards.resizeDocks([self], [1100], Qt.Orientation.Horizontal)
        self._rebuild(self._ordered(self._local_rows))
        self.refill()

    def _save_state(self) -> bool:
        try:
            self._state.save()
            return True
        except Exception:
            log.exception("word_queue: nie zapisano pliku stanu")
            tooltip("Kolejka: nie zapisano pliku stanu — sprawdź Logi.", parent=mw)
            return False

    def _owe(self, rows: dict) -> None:
        """Cards for these rows are (about to be) in the collection; n8n must hear about it."""
        self._state.data["owed"].update({str(row_id): word for row_id, word in rows.items()})
        self._save_state()

    def _settle_owed(self) -> None:
        """After a refill: finish PATCHes lost to a crash or a network error."""
        listed = {(self._list.item(i).data(Qt.ItemDataRole.UserRole) or {}).get("id")
                  for i in range(self._list.count())}
        for key, word in list(self._state.data["owed"].items()):
            row_id = int(key)
            if row_id in self._marked or row_id not in listed:  # done, or row deleted in n8n
                self._state.drop_drafts({row_id})
                del self._state.data["owed"][key]
                continue
            try:
                has_cards = bool(ai_senses.find_word_notes(word, self._cfg))
            except Exception:
                log.exception("word_queue: nie sprawdzono kart dla %r", word)
                continue
            if has_cards:
                self._state.drop_drafts({row_id})
                self._set_row(None, True, row_id=row_id)
            else:
                self._state.data["owed"].pop(key)  # crash before commit: keep the draft, report nothing
        self._save_state()

    def _resume_drafts(self):
        if self._busy or mw.col is not self._collection:
            return
        self._finish_batch(list(self._state.data["drafts"]), [], self._collection)

    def _stop_batch(self):
        self._stop_requested = True
        self._stop_btn.setEnabled(False)
        self._progress.setText("Zatrzymywanie po bieżącym haśle…")

    # -- UI -----------------------------------------------------------------

    def _build_ui(self) -> QWidget:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)

        bar = QHBoxLayout()
        self._counter = QLabel("")
        bar.addWidget(self._counter)
        bar.addStretch()

        self._order = QComboBox()
        self._order.setToolTip("Kolejność listy. „Najnowsze” pokazuje na górze hasła\n"
                               "dopisane ostatnio — te z dzisiejszej wklejki.")
        for label, value in (("Od początku", "id"), ("Najnowsze", "new"), ("Losowo", "random")):
            self._order.addItem(label, value)
        index = self._order.findData(self._cfg.get("order") or "id")
        self._order.setCurrentIndex(index if index >= 0 else 0)
        self._order.currentIndexChanged.connect(lambda _i: self._on_order_changed())
        bar.addWidget(self._order)

        self._hide_done = QCheckBox("Ukryj zrobione")
        self._hide_done.setToolTip("Schowaj zrobione (szare). Nie usuwa ich —\n"
                                  "prawy klik na pozycji cofa odhaczenie.")
        self._hide_done.setChecked(True)  # domyślnie widzisz tylko to, co zostało
        self._hide_done.toggled.connect(lambda _c: self._apply_hiding())
        bar.addWidget(self._hide_done)

        self._word_input = QLineEdit()
        self._word_input.setPlaceholderText("własne hasło → Enter")
        self._word_input.setMaximumWidth(200)
        self._word_input.setToolTip(
            "Hasła spoza kolejki n8n; kilka rozdziel przecinkiem.\n"
            "Trafiają na listę i mają te same zakładki oraz „AI: znaczenia”,\n"
            "a w razie braku połączenia zostają zapisane lokalnie.")
        self._word_input.returnPressed.connect(self._add_typed_word)
        bar.addWidget(self._word_input)

        paste_btn = QPushButton("+ lista")
        paste_btn.setToolTip("Wklej kolumnę haseł, po jednym na linię")
        paste_btn.clicked.connect(lambda _checked=False: self._paste_words())
        bar.addWidget(paste_btn)

        self._ai_btn = QPushButton("AI: znaczenia")
        self._ai_btn.setToolTip(
            "Dopasuj polskie znaczenia (diki, Cambridge EN-PL) do angielskich\n"
            "definicji (Cambridge EN-PL, Oxford, LDoCE) i utwórz po jednej karcie\n"
            "na każde znaczenie.\n"
            "Bierze zaptaszkowane hasła, a gdy nic nie zaptaszkowano — podświetlone."
        )
        self._ai_btn.clicked.connect(lambda _checked=False: self._ai_senses())
        bar.addWidget(self._ai_btn)

        done_btn = QPushButton("Zrobione →")
        done_btn.setToolTip("Odhacz w n8n i przejdź do następnego słówka")
        done_btn.clicked.connect(lambda _checked=False: self._done_and_next())
        bar.addWidget(done_btn)

        next_btn = QPushButton("Następne")
        next_btn.setToolTip("Przejdź dalej bez odhaczania (pominięcie)")
        next_btn.clicked.connect(lambda _checked=False: self.advance())
        bar.addWidget(next_btn)

        reload_btn = QPushButton("Odśwież")
        reload_btn.setToolTip("Pobierz kolejkę z n8n od nowa")
        reload_btn.clicked.connect(self.refill)
        bar.addWidget(reload_btn)
        layout.addLayout(bar)
        recovery = QHBoxLayout()
        self._progress = QLabel("")
        self._progress.setWordWrap(True)
        recovery.addWidget(self._progress, 1)
        self._stop_btn = QPushButton("Zatrzymaj po bieżącym haśle")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(lambda: self._stop_batch())
        recovery.addWidget(self._stop_btn)
        self._resume_btn = QPushButton("Odzyskane propozycje")
        self._resume_btn.setEnabled(bool(self._state.data["drafts"]))
        self._resume_btn.clicked.connect(lambda: self._resume_drafts())
        recovery.addWidget(self._resume_btn)
        layout.addLayout(recovery)

        split = QSplitter(Qt.Orientation.Horizontal, root)

        self._list = QListWidget(split)
        self._list.setMinimumWidth(160)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.itemChanged.connect(self._on_item_checked)
        self._list.itemSelectionChanged.connect(self._update_ai_label)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._list_menu)
        split.addWidget(self._list)

        self._tabs = _DictTabs(word_queue.dict_labels(self._cfg), split)
        split.addWidget(self._tabs)
        split.setStretchFactor(1, 1)  # zakładki zjadają całą nadmiarową szerokość
        split.setSizes([220, 880])

        layout.addWidget(split)
        return root

    # -- kolejka ------------------------------------------------------------

    def _current_row(self) -> dict | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    _shown_word = ""  # hasło aktualnie w zakładkach; chroni przed zbędnym przeładowaniem

    def _show_urls(self, word: str, row: dict | None) -> None:
        if word == self._shown_word:
            return  # paczka z jednym hasłem nie przeładowuje tego, co już widać
        self._shown_word = word
        self._tabs.set_urls(word_queue.dict_urls(word, self._cfg, row), word)

    def _add_typed_word(self) -> None:
        """Enter w polu obok listy: dopisz hasło (albo kilka po przecinku)."""
        self._add_local_rows(word_queue.parse_words(self._word_input.text()))
        self._word_input.clear()

    def _paste_words(self) -> None:
        """Przycisk „+ lista": okno na wklejenie kolumny haseł, po jednym na linię."""
        text, accepted = QInputDialog.getMultiLineText(
            self, "Własne hasła", "Po jednym na linię (albo po przecinku):")
        if accepted:
            self._add_local_rows(word_queue.parse_words(text))

    def _add_local_rows(self, words: list[str]) -> None:
        """Dopisz hasła do tabeli n8n i na koniec listy; skocz na pierwsze z nich.

        Hasło, które już jest na liście, pomijamy — panel trzyma CAŁĄ tabelę,
        więc to jest zarazem kontrola duplikatów w n8n, bez dodatkowego zapytania.

        Gdy n8n nie przyjmie zapisu (offline, zła tabela), hasła zostają jako
        wiersze lokalne z UJEMNYM `id`: działa wszystko poza odhaczaniem, którego
        nie ma co wysyłać, przeżywają zamknięcie okna „Dodaj".
        """
        if not words:
            return
        if self._busy:
            tooltip("AI: poczekaj na koniec paczki.", parent=mw)
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
        fresh, skipped = [], []
        for word in words:
            if word.casefold() in known:
                skipped.append(word)
                continue
            known.add(word.casefold())
            self._next_local_id -= 1  # rezerwujemy od razu; równoległe zapisy nie kolidują
            fresh.append({"id": self._next_local_id, column: word})
        if skipped:
            shown = ", ".join(skipped[:8]) + (f" (+{len(skipped) - 8})" if len(skipped) > 8 else "")
            tooltip(f"Już na liście, pominięto: {shown}", parent=mw, period=4000)
        if not fresh:
            self._select_word(skipped[0] if skipped else "")
            return
        self._adding |= {row[column].casefold() for row in fresh}

        def done(future):
            try:
                saved, error = future.result()
            except Exception:  # noqa: BLE001
                log.exception("word_queue: dopisywanie wierszy rzuciło wyjątkiem")
                saved, error = [], "wyjątek (szczegóły w Logach)"
            self._adding -= {row[column].casefold() for row in fresh}
            if sip.isdeleted(self):
                return
            if error:
                # Offline albo zła tabela: hasła zostają w panelu, żeby dało się
                # z nimi pracować teraz i po ponownym otwarciu panelu.
                tooltip(f"n8n: {error}. Hasła zachowano lokalnie.",
                        parent=mw, period=8000)
                self._local_rows += fresh
                self._save_state()
                saved = fresh
            def append_when_idle():
                if sip.isdeleted(self) or mw.col is not self._collection:
                    return
                if self._busy:
                    QTimer.singleShot(250, append_when_idle)
                    return
                self._append_rows(saved)
            append_when_idle()

        mw.taskman.run_in_background(
            lambda: word_queue.add_rows([row[column] for row in fresh], self._cfg), done)

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
        if self._busy:
            tooltip("AI: poczekaj na koniec paczki.", parent=mw)
            return
        if self._pending:
            tooltip("n8n: poczekaj na zakończenie zapisu wierszy.", parent=mw)
            return
        self._refill_generation += 1
        generation = self._refill_generation
        def done(future):
            if sip.isdeleted(self) or generation != self._refill_generation:
                return
            try:
                rows, error = future.result()
            except Exception:
                log.exception("word_queue: pobieranie kolejki rzuciło wyjątkiem")
                return
            if error:
                tooltip(f"n8n: nie pobrano kolejki — {error}", parent=mw, period=5000)
                return
            if sip.isdeleted(self):
                return  # okno „Dodaj" zamknięte, zanim n8n odpowiedział
            # Stan bierzemy z tabeli, nie z pamięci sesji — po „Odśwież" zrobione
            # wciąż są na liście (schowane), więc pomyłkę da się cofnąć.
            # Wyjątkiem są wiersze lokalne: n8n o nich nie wie, więc ich ptaszki
            # przenosimy przez odświeżenie sami, inaczej wracałyby jako do zrobienia.
            remapped = self._state.resolve_local_rows(rows, self._cfg["word_column"])
            self._picked = {remapped.get(row_id, row_id) for row_id in self._picked}
            self._marked = ({r["id"] for r in rows if r.get(self._cfg["flag_column"])}
                            | {row_id for row_id in self._marked if row_id < 0})
            self._done_count = 0  # licznik jest per sesja, nie per tabela
            self._rebuild(self._ordered(rows + self._local_rows))
            self._settle_owed()

        mw.taskman.run_in_background(lambda: self._fetch_queue(self._cfg), done)

    def _rebuild(self, rows: list[dict]) -> None:
        """Przebuduj listę z podanych wierszy, zachowując wygląd odhaczonych.

        Ptaszki (wybór do AI) przeżywają przebudowę — od tego są — ale tylko dla
        wierszy, które nadal istnieją; inaczej znikający wiersz zawyżałby licznik.
        """
        self._picked &= {row.get("id") for row in rows}
        selected_id = self.current_row_id()
        self._selection_generation += 1
        with self._silent():  # addItem/setCheckState odpalają itemChanged — nie chcemy PATCH-y
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
        """Ptaszek = wybrane do AI. Zrobione widać kolorem, nie ptaszkiem."""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, row)  # _style_item czyta stąd hasło
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        row_id = row.get("id")
        item.setCheckState(Qt.CheckState.Checked if row_id in self._picked
                           else Qt.CheckState.Unchecked)
        self._style_item(item)
        return item

    def _on_order_changed(self) -> None:
        """Przestaw kolejność OD RAZU, nie dopiero przy następnym pobraniu —
        inaczej rozwijanka wygląda na zepsutą. Wybór przeżywa restart."""
        order = self._order.currentData()
        if self._busy:
            with self._silent():
                index = self._order.findData(self._cfg.get("order") or "id")
                self._order.setCurrentIndex(index if index >= 0 else 0)
            tooltip("AI: poczekaj na koniec paczki.", parent=mw)
            return
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

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        """Ptaszek = „weź to do AI". Wyłącznie stan panelu, n8n o nim nie wie.

        Zbieranie przez długą listę musi przetrwać przewijanie i zmianę
        zaznaczenia — od tego jest ptaszek, a nie podświetlenie, które gubi się
        przy pierwszym kliknięciu obok.
        """
        if self._suspend or item is None:
            return
        row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
        if row_id is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._picked.add(row_id)
        else:
            self._picked.discard(row_id)
        self._style_item(item)
        self._update_counter()
        self._update_ai_label()

    def _clear_picks(self) -> None:
        self._picked.clear()
        for i in range(self._list.count()):
            with self._silent():
                self._list.item(i).setCheckState(Qt.CheckState.Unchecked)
            self._style_item(self._list.item(i))
        self._update_counter()
        self._update_ai_label()

    def _list_menu(self, point) -> None:
        """Prawy klik: stan „zrobione" w n8n — ten, który stracił ptaszek."""
        item = self._list.itemAt(point)
        if item is None:
            return
        row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
        menu = QMenu(self)
        done = row_id in self._marked
        toggle = menu.addAction("Cofnij odhaczenie" if done else "Oznacz jako zrobione")
        toggle.triggered.connect(lambda _checked=False: self._set_row(item, not done))
        if self._picked:
            clear = menu.addAction(f"Wyczyść wybór do AI ({len(self._picked)})")
            clear.triggered.connect(lambda _checked=False: self._clear_picks())
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
        mówić prawdę o tabeli. Ptaszek do tego nie należy: on wybiera do AI."""
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
                if row_id < 0:
                    for row in self._local_rows:
                        if row["id"] == row_id:
                            row[self._cfg["flag_column"]] = done
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

        if row_id < 0:
            # Wiersz lokalny: nie ma go w tabeli, więc „zapis" się udał z definicji.
            # Idziemy tą samą ścieżką co PATCH, żeby licznik i styl miały jedno
            # miejsce obsługi.
            local = Future()
            local.set_result((1, None))
            finished(local)
            return

        try:
            mw.taskman.run_in_background(
                lambda: self._mark_row_done(row_id, self._cfg, done), finished
            )
        except Exception as error:
            failed = Future()
            failed.set_exception(error)
            finished(failed)

    def _style_item(self, item: QListWidgetItem) -> None:
        """Szare = zrobione w n8n, „☑" i pogrubienie = wybrane do AI.

        Wskaźnik checkboxa rysuje motyw i na liście kilkuset pozycji potrafi być
        niewidoczny — dlatego wybór niesie też TEKST pozycji, który wyrenderuje
        się zawsze. Wszystkie trzy sygnały czytamy z `self`, więc nie da się ich
        rozjechać z listy wywołań. setData emituje itemChanged, stąd wyciszenie.
        """
        row = item.data(Qt.ItemDataRole.UserRole) or {}
        row_id = row.get("id")
        picked = row_id in self._picked
        done = self._pending.get(row_id, row_id in self._marked)
        word = row.get(self._cfg["word_column"]) or "—"
        font = None
        if picked:
            font = QFont()
            font.setBold(True)
        with self._silent():
            waiting = str(row_id) in self._state.data["owed"] and row_id not in self._marked
            item.setText((f"☑ {word}" if picked else word) + (" · karty są, czeka n8n" if waiting else ""))
            # Rola = None przywraca domyślny wygląd motywu (jasny i ciemny).
            item.setData(Qt.ItemDataRole.ForegroundRole,
                         QBrush(Qt.GlobalColor.gray) if done else None)
            item.setData(Qt.ItemDataRole.FontRole, font)

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
        hide = self._hide_done.isChecked()
        for i in range(self._list.count()):
            item = self._list.item(i)
            row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
            item.setHidden(hide and row_id in self._marked)

    def advance(self) -> None:
        """Następna WIDOCZNA pozycja. Nic nie odhacza — od tego jest ptaszek."""
        for i in range(self._list.currentRow() + 1, self._list.count()):
            if not self._list.item(i).isHidden():
                self._list.setCurrentRow(i)
                return

    def _on_item_changed(self, current: QListWidgetItem, previous) -> None:
        """Zmiana pozycji (klik lub strzałki) → wpisanie hasła i słowniki.

        Qt wysyła `currentItemChanged` PRZED `selectionChanged`, więc przy
        Shift/Ctrl zaznaczenie jest tu jeszcze jednoelementowe i liczenie go w
        tym miejscu nic nie da. Decyzję odkładamy o jeden obrót pętli zdarzeń —
        inaczej każdy klik przy zaznaczaniu paczki pyta o zastąpienie hasła
        w rozpoczętej notatce.
        """
        if self._suspend or current is None:
            return
        QTimer.singleShot(0, lambda: self._apply_selection(current, previous))

    def _apply_selection(self, current: QListWidgetItem, previous) -> None:
        if sip.isdeleted(self) or self._busy or self._suspend or sip.isdeleted(current):
            return
        if self._list.currentItem() is not current:
            return  # zaznaczenie poszło dalej, zanim doszliśmy do tej pozycji
        if len(self._list.selectedItems()) > 1:
            return  # zaznaczasz paczkę — nie przestawiamy notatki ani zakładek
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
            tooltip("n8n: inne hasło — wiersz nie został odhaczony. Użyj „Zrobione →”, jeśli to ta sama pozycja.", parent=mw)
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

    # -- AI: znaczenia → karty ----------------------------------------------

    def _ai_senses(self) -> None:
        """Zaznaczone hasła → słowniki → model → jedno okno wyboru → jeden zapis.

        Hasła idą PO KOLEI: załaduj zakładki, zbierz tekst, zapytaj model, dalej.
        Bez nakładania kroków — paczka ma być odtwarzalna, a nie szybka o te
        kilka sekund, które i tak zjada ładowanie stron.
        """
        if self._busy or mw.col is not self._collection:
            return
        error = ai_senses.validate_mapping(self._cfg)
        if error:
            tooltip(f"AI: {error}", parent=mw, period=6000)
            return
        rows = [row for row in self._selected_rows() if str(row["id"]) not in self._state.data["owed"]]
        if not rows:
            tooltip("AI: wybierz słówko z listy albo dopisz własne hasło.", parent=mw)
            return
        if len(rows) > _BATCH_ASK and not askUser(
                f"Przetworzyć {len(rows)} haseł naraz? Każde to osobne pytanie do modelu.",
                parent=self):
            return
        # Dostawca i jego konfiguracja — tu, na głównym wątku. W tle zostaje samo
        # wywołanie modelu; import cudzego dodatku z wątku roboczego wysadzał Anki.
        provider, error = ai_senses.prepare_provider(self._cfg)
        if error:
            tooltip(f"AI: {error}", parent=mw, period=6000)
            return

        self._stop_requested = False
        self._set_busy(True)
        self._refill_generation += 1
        self._selection_generation += 1
        collection = mw.col
        column = self._cfg["word_column"]
        proposals: list[dict] = []
        cached = {p["row_id"]: p for p in self._state.data["drafts"]}
        errors: list[tuple[str, str]] = []
        source_texts = {}
        whole_pages = {}
        provider_name = ai_senses.provider_label(self._cfg)

        def valid():
            return not sip.isdeleted(self) and mw.col is collection

        def step(index):
            if not valid():
                self._unfreeze()
                return
            if index >= len(rows) or self._stop_requested:
                self._finish_batch(proposals, errors, collection)
                return
            word = clean_html_normalized(rows[index].get(column) or "")
            if not word:
                step(index + 1)
                return
            cached_proposal = cached.get(rows[index]["id"])
            if cached_proposal and cached_proposal["word"] == word:
                proposals.append(cached_proposal)
                QTimer.singleShot(0, lambda: step(index + 1))
                return
            self._progress.setText(f"AI: {index + 1}/{len(rows)} — {word}")
            self._show_urls(word, rows[index])

            def with_texts(texts):
                if not valid():
                    self._unfreeze()
                    return
                if not texts:
                    errors.append((word, "zakładki słownikowe się nie wczytały"))
                    step(index + 1)
                    return
                source_texts[index] = list(texts)
                whole_pages[index] = sorted(self._tabs.whole_page & set(texts))
                self._progress.setText(f"AI: {index + 1}/{len(rows)} — {word}; źródła: {', '.join(texts)}")
                mw.taskman.run_in_background(
                    lambda: ai_senses.generate(provider, word, texts, self._cfg),
                    lambda future: collected(index, word, future),
                )

            self._tabs.texts(with_texts)

        def collected(index, word, future):
            if not valid():
                self._unfreeze()
                return
            try:
                senses, error = future.result()
            except Exception:  # noqa: BLE001 — błąd dostawcy nie może wysadzać okna „Dodaj"
                log.exception("ai_senses: generowanie rzuciło wyjątkiem")
                senses, error = [], "wyjątek (szczegóły w Logach)"
            if error:
                errors.append((word, error))
            elif senses:
                proposals.append({"word": word, "senses": senses,
                                  "urls": word_queue.dict_urls(word, self._cfg, rows[index]),
                                  "row_id": rows[index].get("id"),
                                  "sources": source_texts[index], "whole_page": whole_pages[index],
                                  "provider": provider_name})
                self._state.data["drafts"] = [p for p in self._state.data["drafts"]
                                               if p["row_id"] != rows[index]["id"]] + [proposals[-1]]
                try:
                    self._state.save()
                except Exception:
                    log.exception("ai_senses: nie zapisano propozycji")
                    self._stop_requested = True
                    errors.append((word, "błąd zapisu propozycji na dysku"))
            step(index + 1)

        step(0)

    def _selected_rows(self) -> list[dict]:
        """Co idzie do AI: zaptaszkowane, a jak nic nie zaptaszkowano — podświetlone.

        Ptaszki wygrywają, bo są trwałe: zbierasz je przez całą listę, a klik
        w cokolwiek innego ich nie gubi. Podświetlenie zostaje dla jednorazówek.
        Schowane (zrobione) pomijamy — Ctrl+A zaznacza też je.
        """
        rows = [self._list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self._list.count())]
        picked = [row for row in rows if (row or {}).get("id") in self._picked]
        if picked:
            return picked
        items = self._list.selectedItems() or [self._list.currentItem()]
        return [item.data(Qt.ItemDataRole.UserRole) for item in items
                if item is not None and not item.isHidden()]

    def _update_ai_label(self) -> None:
        count = len(self._picked) or len(self._list.selectedItems())
        self._ai_btn.setText("AI: znaczenia" + (f" ({count})" if count > 1 else ""))

    def _unfreeze(self) -> None:
        """Paczka przerwana (inny profil, zamknięta kolekcja) nie może zostawić
        panelu wyłączonego na zawsze — widget bywa żywy dłużej niż jej powód."""
        if not sip.isdeleted(self) and self._busy:
            self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        """Paczka w toku: lista i wszystko, co przebudowuje panel, czeka."""
        self._busy = busy
        self._ai_btn.setEnabled(not busy)
        self._list.setEnabled(not busy)
        self._tabs.setEnabled(not busy)
        self._stop_btn.setEnabled(busy)
        self._resume_btn.setEnabled(not busy and bool(self._state.data["drafts"]))

    def _ai_failed(self, message: str) -> None:
        self._set_busy(False)
        tooltip(f"AI: {message}", parent=mw, period=6000)

    def _finish_batch(self, proposals: list[dict], errors: list[tuple[str, str]],
                      collection) -> None:
        """Wynik całej paczki: jedno okno wyboru, jedna transakcja, potem ptaszki."""
        self._set_busy(False)
        self._progress.setText("Propozycje zachowano. Anuluj pozwala wrócić do nich później.")
        summary = "; ".join(f"„{word}”: {error}" for word, error in errors[:3])
        if not proposals:
            self._ai_failed(summary or "model nie znalazł żadnego znaczenia")
            return
        if summary:
            tooltip(f"AI: pominięto {len(errors)} hasł(a) — {summary}", parent=mw, period=8000)

        for proposal in proposals:
            proposal["existing"] = ai_senses.existing_senses(proposal["word"], self._cfg)
        chosen = ai_senses.pick_senses(proposals, self, self._cfg)
        if not chosen:
            return
        # Okno wyboru bywa otwarte długo. Cel zapisu sprawdzamy PO nim, nie przed:
        # inna kolekcja albo zamknięte okno „Dodaj" to zapis nie tam, gdzie widziałeś.
        if (sip.isdeleted(self) or mw.col is not collection
                or sip.isdeleted(self._addcards) or self._addcards.editor.note is None):
            tooltip("AI: okno „Dodaj” albo profil zmieniły się w trakcie — nie zapisano.",
                    parent=mw, period=8000)
            return
        words = {word for word, _sense in chosen}
        done_words = {p["row_id"]: p["word"] for p in proposals
                      if p["word"] in words and p.get("row_id") is not None}
        # Debt goes to disk BEFORE the transaction: a crash after commit still reaches n8n.
        self._owe({row_id: word for row_id, word in done_words.items() if row_id not in self._marked})
        try:
            added, result = ai_senses.add_notes(self._addcards, chosen, self._cfg)
        except Exception:  # noqa: BLE001
            added, result = 0, None
            log.exception("ai_senses: zapis notatek rzucił wyjątkiem")
            tooltip("AI: nie zapisano kart (szczegóły w Logach)", parent=mw, period=6000)
        if not added:
            for row_id in done_words:
                self._state.data["owed"].pop(str(row_id), None)
            self._save_state()
            if result:
                tooltip(f"AI: {result}", parent=mw, period=8000)
            return
        self._state.drop_drafts(done_words)
        self._save_state()

        from aqt.operations import on_op_finished
        on_op_finished(mw, result, self)

        review = sum(1 for _word, sense in chosen if not sense.get("reviewed"))
        tag = self._cfg.get("ai_review_tag") or ""
        suffix = f", {review} do przejrzenia" + (f" (tag „{tag}”)" if tag else "") if review else ""
        subject = f"„{next(iter(words))}”" if len(words) == 1 else f"{len(words)} haseł"
        tooltip(f"AI: dodano {added} kart dla {subject}{suffix}", parent=mw, period=5000)

        # Karty są w talii, więc wiersze są zrobione — hook add_cards_did_add_note
        # tu nie leci (to nie okno „Dodaj" je zapisało), odhaczamy wprost.
        done = set(done_words)
        self._picked -= done  # zrobione znika z wyboru, żeby nie poszło drugi raz
        for i in range(self._list.count()):
            item = self._list.item(i)
            row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
            if row_id not in done:
                continue
            with self._silent():
                item.setCheckState(Qt.CheckState.Unchecked)
            self._style_item(item)
            if row_id not in self._marked:
                self._set_row(item, True)
        self._update_ai_label()

    def _update_counter(self) -> None:
        left = sum((self._list.item(i).data(Qt.ItemDataRole.UserRole) or {}).get("id") not in self._marked
                   for i in range(self._list.count()))
        picked = f" · ☑ {len(self._picked)} do AI" if self._picked else ""
        self._counter.setText(
            f"{left} do zrobienia{picked} · ✓ {self._done_count} w tej sesji")

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
            note[field] = word
            self._bound_note = note
            self._bound_row_id = self.current_row_id()
            editor.loadNote()
            if after:
                after(True)

        editor.saveNow(saved)
