"""Dok przy oknie „Dodaj": słowniki wewnątrz Anki + kolejka słówek z n8n.

Bierze wiersz z DataTable (flag_column == false), wpisuje `Slowko` do pola
notatki i ładuje gotowe URL-e z kolumn (diki / Longman / Oxford) w QWebEngineView.
Do stron wstrzykiwany jest TEN SAM userscript, którego używasz w przeglądarce —
jego przyciski gadają z mostkiem web_bridge na 127.0.0.1:8766. Dzięki temu
istnieje jedna wersja skryptu, a nie dwie.

Po dodaniu notatki (hook w __init__) wiersz jest odhaczany po `id`, ale panel
ZOSTAJE na słówku — jedno hasło bywa kilkoma kartami (kilka znaczeń).

Ptaszek przy słówku to STAN wiersza w n8n, nie jednorazowa akcja: zaznaczenie
ustawia flagę na true, odznaczenie na false. Dzięki temu pomyłkę cofasz jednym
kliknięciem. Nic nie znika z listy samo — od chowania jest „Ukryj zrobione".

Przyciski: „Zrobione →" = ptaszek + skok dalej (koniec z tym hasłem),
„Następne" = skok bez odhaczania (pominięcie).

Zakładki ładują się leniwie — Chromium na zakładkę to ~100 MB, a Longmana
z Oxfordem często nawet nie otwierasz.
"""

import logging
import random
from concurrent.futures import Future
from contextlib import contextmanager
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QBrush,
    QCheckBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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

from . import ai_senses
from .html import clean_html_normalized

def get_full_config():
    return mw.addonManager.getConfig(__package__) or {}


def save_full_config(config):
    mw.addonManager.writeConfig(__package__, config)

log = logging.getLogger(__name__)

# Ten sam plik, który wgrywasz do Tampermonkeya. Jedno źródło prawdy.
_USERSCRIPT_PATH = Path(__file__).resolve().parent / "dictionaries-to-anki.user.js"

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
        self._loaded: dict[int, bool] = {}   # indeks → strona dojechała (AI czeka na to)
        for index, label in enumerate(self._labels):
            view = QWebEngineView(self)
            view.setPage(QWebEnginePage(_dict_profile(), view))
            # ok=False też kończy czekanie: pusta zakładka jest lepsza niż zawieszony przycisk AI.
            view.loadFinished.connect(lambda _ok, i=index: self._loaded.__setitem__(i, True))
            self._views.append(view)
            self.addTab(view, label)
        self.currentChanged.connect(lambda _i: self._load_current())

    def set_urls(self, urls: dict[str, str]) -> None:
        """urls: etykieta → URL. Brak/pusty URL = zakładka wyszarzona."""
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
        self._load_current()

    def _load_current(self) -> None:
        self._start_load(self.currentIndex())

    def _start_load(self, index: int) -> None:
        url = self._pending.pop(index, None)
        if url:
            self._loaded[index] = False
            self._views[index].load(QUrl(url))

    def _enabled(self) -> list[int]:
        return [i for i in range(len(self._labels)) if self.isTabEnabled(i)]

    def texts(self, callback, timeout_ms: int = 20000) -> None:
        """{etykieta: tekst strony} dla włączonych zakładek — do promptu AI.

        Dociąga zakładki, które jeszcze nie wisiały: leniwe ładowanie oszczędza
        pamięć przy przeglądaniu, ale model potrzebuje diki (PL) razem z Oxfordem
        (EN). Zakładka, która nie dojedzie w `timeout_ms`, jest pomijana —
        lepszy prompt z dwóch słowników niż przycisk, który nigdy nie oddaje.

        ponytail: odpytujemy timerem zamiast pilnować sygnałów loadFinished na
        krzyż. Ćwierć sekundy opóźnienia przy akcji, która i tak trwa sekundy.
        """
        for index in self._enabled():
            self._start_load(index)
        remaining = [timeout_ms]

        def ready():
            if sip.isdeleted(self):
                return
            if any(not self._loaded.get(i) for i in self._enabled()) and remaining[0] > 0:
                remaining[0] -= 250
                QTimer.singleShot(250, ready)
                return
            self._collect(callback)

        ready()

    def _collect(self, callback) -> None:
        indexes = [i for i in self._enabled() if self._loaded.get(i)]
        if not indexes:
            callback({})
            return
        result: dict[str, str] = {}
        missing = [len(indexes)]

        def got(text, label):
            result[label] = text or ""
            missing[0] -= 1
            if missing[0] == 0 and not sip.isdeleted(self):
                callback(result)

        for index in indexes:
            self._views[index].page().toPlainText(
                lambda text, label=self._labels[index]: got(text, label)
            )


class WordQueuePanel(QDockWidget):
    """Dok po prawej stronie okna „Dodaj". Żyje tak długo jak to okno."""

    def __init__(self, addcards, cfg: dict, fetch_queue, mark_row_done):
        super().__init__("Kolejka słówek", addcards)
        self._addcards = addcards
        self._cfg = cfg
        self._fetch_queue = fetch_queue
        self._mark_row_done = mark_row_done
        self._marked: set = set()  # id wierszy już odhaczonych — PATCH tylko raz na wiersz
        self._done_count = 0
        self._suspend = False  # blokuje itemChanged przy zmianach programowych
        self._pending: dict = {}  # one in-flight PATCH per row
        self._refill_generation = 0
        self._selection_generation = 0
        self._bound_note = None
        self._bound_row_id = None

        self.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.setWidget(self._build_ui())
        addcards.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        addcards.resizeDocks([self], [1100], Qt.Orientation.Horizontal)
        self.refill()

    # -- UI -----------------------------------------------------------------

    def _build_ui(self) -> QWidget:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)

        bar = QHBoxLayout()
        self._counter = QLabel("")
        bar.addWidget(self._counter)
        bar.addStretch()

        self._shuffle = QCheckBox("Losowo")
        self._shuffle.setToolTip("Pomieszaj kolejność listy natychmiast (jak „Pomieszaj” w viewerze)")
        self._shuffle.setChecked(bool(self._cfg["random_order"]))
        self._shuffle.toggled.connect(self._on_shuffle_toggled)
        bar.addWidget(self._shuffle)

        self._hide_done = QCheckBox("Ukryj zrobione")
        self._hide_done.setToolTip("Schowaj odhaczone. Nie usuwa ich — odkryj i odznacz, by cofnąć.")
        self._hide_done.setChecked(True)  # domyślnie widzisz tylko to, co zostało
        self._hide_done.toggled.connect(lambda _c: self._apply_hiding())
        bar.addWidget(self._hide_done)

        self._ai_btn = QPushButton("AI: znaczenia")
        self._ai_btn.setToolTip(
            "Dopasuj polskie znaczenia z diki do definicji z Oxforda/Longmana\n"
            "i utwórz po jednej karcie na każde znaczenie"
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

        split = QSplitter(Qt.Orientation.Horizontal, root)

        self._list = QListWidget(split)
        self._list.setMinimumWidth(160)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.itemChanged.connect(self._on_item_checked)
        split.addWidget(self._list)

        self._tabs = _DictTabs(list(self._cfg["link_columns"]), split)
        split.addWidget(self._tabs)
        split.setStretchFactor(1, 1)  # zakładki zjadają całą nadmiarową szerokość
        split.setSizes([220, 880])

        layout.addWidget(split)
        return root

    # -- kolejka ------------------------------------------------------------

    def _current_row(self) -> dict | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

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
            if self._shuffle.isChecked():
                random.shuffle(rows)
            # Stan bierzemy z tabeli, nie z pamięci sesji — po „Odśwież" zrobione
            # wciąż są na liście (schowane), więc pomyłkę da się cofnąć.
            self._marked = {r["id"] for r in rows if r.get(self._cfg["flag_column"])}
            self._done_count = 0  # licznik jest per sesja, nie per tabela
            self._rebuild(rows)

        mw.taskman.run_in_background(lambda: self._fetch_queue(self._cfg), done)

    def _rebuild(self, rows: list[dict]) -> None:
        """Przebuduj listę z podanych wierszy, zachowując wygląd odhaczonych."""
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
        item = QListWidgetItem(row.get(self._cfg["word_column"]) or "—")
        item.setData(Qt.ItemDataRole.UserRole, row)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        row_id = row.get("id")
        done = self._pending.get(row_id, row_id in self._marked)
        if row_id in self._pending:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked)
        self._style_item(item, done)
        return item

    def _on_shuffle_toggled(self, checked: bool) -> None:
        """Tasuj OD RAZU, nie dopiero przy następnym pobraniu — inaczej checkbox
        wygląda na zepsuty. Stan zapamiętujemy, żeby przeżył restart."""
        rows = [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
        ]
        if checked:
            random.shuffle(rows)
        else:
            rows.sort(key=lambda r: r.get("id") or 0)  # z powrotem kolejność z tabeli
        self._rebuild(rows)

        self._cfg["random_order"] = checked
        full = get_full_config()
        full.setdefault("word_queue", {})["random_order"] = checked
        save_full_config(full)

    def _on_item_checked(self, item: QListWidgetItem) -> None:
        """Ptaszek = stan wiersza w n8n, w obie strony. Odznaczenie cofa pomyłkę."""
        if self._suspend:
            return
        self._set_row(item, item.checkState() == Qt.CheckState.Checked)

    def _done_and_next(self) -> None:
        """Przycisk „Zrobione”: odhacz bieżące słówko i przejdź do następnego.

        Ptaszek stawiamy zwyczajnie (bez _silent), żeby _on_item_checked wysłał
        PATCH tą samą ścieżką co kliknięcie myszą. Nawigujemy od razu — PATCH
        leci w tle, a gdyby padł, rollback odznaczy pozycję na liście.
        """
        item = self._list.currentItem()
        if item is None:
            return
        if item.checkState() != Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Checked)
        self.advance()

    def _set_row(self, item: QListWidgetItem, done: bool) -> None:
        """Zapisz stan w n8n. Przy błędzie cofa ptaszek — lista ma mówić prawdę o n8n."""
        row_id = (item.data(Qt.ItemDataRole.UserRole) or {}).get("id")
        if row_id is None:
            return
        if row_id in self._pending:
            self._set_check(item, self._pending[row_id])
            return
        previous = row_id in self._marked
        if previous == done:
            self._set_check(item, done)
            return
        self._refill_generation += 1  # an older GET must not overwrite this PATCH
        self._pending[row_id] = done
        with self._silent():
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        self._set_check(item, done)

        def finished(future):
            try:
                matched, error = future.result()
                if not error and matched != 1:
                    error = f"oczekiwano 1 wiersza, zmieniono {matched}; odśwież kolejkę"
            except Exception:
                log.exception("word_queue: PATCH rzucił wyjątkiem")
                error = "wyjątek (szczegóły w Logach)"
            self._pending.pop(row_id, None)
            if sip.isdeleted(self):
                return
            if error:
                tooltip(f"n8n: nie zapisano wiersza {row_id} — {error}", parent=mw, period=5000)
            else:
                self._marked.add(row_id) if done else self._marked.discard(row_id)
                self._done_count += 1 if done else -1
            # Shuffle may have rebuilt the QListWidget while HTTP was running.
            for i in range(self._list.count()):
                current = self._list.item(i)
                if current.data(Qt.ItemDataRole.UserRole).get("id") == row_id:
                    self._set_check(current, row_id in self._marked)
                    with self._silent():
                        current.setFlags(current.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    self._style_item(current, row_id in self._marked)
            self._apply_hiding()
            self._update_counter()

        try:
            mw.taskman.run_in_background(
                lambda: self._mark_row_done(row_id, self._cfg, done), finished
            )
        except Exception as error:
            failed = Future()
            failed.set_exception(error)
            finished(failed)

    def _set_check(self, item: QListWidgetItem, checked: bool) -> None:
        with self._silent():
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _style_item(self, item: QListWidgetItem, done: bool) -> None:
        # setData też emituje itemChanged — bez wyciszenia _on_item_checked
        # zobaczyłby „zmianę”, wysłał drugi PATCH i policzył słówko dwa razy.
        with self._silent():
            # ForegroundRole = None przywraca domyślny kolor motywu (jasny i ciemny).
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
        hide = self._hide_done.isChecked()
        for i in range(self._list.count()):
            item = self._list.item(i)
            item.setHidden(hide and item.checkState() == Qt.CheckState.Checked)

    def advance(self) -> None:
        """Następna WIDOCZNA pozycja. Nic nie odhacza — od tego jest ptaszek."""
        for i in range(self._list.currentRow() + 1, self._list.count()):
            if not self._list.item(i).isHidden():
                self._list.setCurrentRow(i)
                return

    def _on_item_changed(self, current: QListWidgetItem, previous) -> None:
        """Zmiana zaznaczenia (klik lub strzałki): wpisz słówko, załaduj słowniki."""
        if self._suspend or current is None:
            return
        row = current.data(Qt.ItemDataRole.UserRole)
        word = row.get(self._cfg["word_column"]) or ""
        def ready(accepted):
            if accepted:
                self._tabs.set_urls(
                    {label: row.get(column) or "" for label, column in self._cfg["link_columns"].items()}
                )
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
        item = self._list.currentItem()
        if item is not None:
            self._set_row(item, True)

    # -- AI: znaczenia → karty ----------------------------------------------

    def _ai_senses(self) -> None:
        """Tekst otwartych słowników → model → wybór znaczeń → po karcie na znaczenie."""
        row = self._current_row()
        word = (row or {}).get(self._cfg["word_column"]) or ""
        if not word:
            tooltip("AI: najpierw wybierz słówko z listy.", parent=mw)
            return
        self._ai_btn.setEnabled(False)

        def with_texts(texts):
            if sip.isdeleted(self):
                return
            if not texts:
                self._ai_failed("zakładki słownikowe się nie wczytały")
                return
            mw.taskman.run_in_background(
                lambda: ai_senses.generate(word, texts, self._cfg),
                lambda future: self._on_senses(word, future),
            )

        self._tabs.texts(with_texts)

    def _ai_failed(self, message: str) -> None:
        self._ai_btn.setEnabled(True)
        tooltip(f"AI: {message}", parent=mw, period=6000)

    def _on_senses(self, word: str, future) -> None:
        try:
            senses, error = future.result()
        except Exception:  # noqa: BLE001 — błąd dostawcy nie może wysadzać okna „Dodaj"
            log.exception("ai_senses: generowanie rzuciło wyjątkiem")
            senses, error = [], "wyjątek (szczegóły w Logach)"
        if sip.isdeleted(self):
            return
        if error:
            self._ai_failed(error)
            return
        self._ai_btn.setEnabled(True)

        chosen = ai_senses.pick_senses(senses, word, self)
        if not chosen or sip.isdeleted(self):
            return
        try:
            added, error = ai_senses.add_notes(self._addcards, word, chosen, self._cfg)
        except Exception:  # noqa: BLE001
            log.exception("ai_senses: zapis notatek rzucił wyjątkiem")
            tooltip("AI: nie zapisano kart (szczegóły w Logach)", parent=mw, period=6000)
            return
        if error:
            tooltip(f"AI: {error}", parent=mw, period=8000)
        if not added:
            return

        mw.reset()
        review = sum(1 for sense in chosen if sense["match"] != "exact")
        tag = self._cfg.get("ai_review_tag") or ""
        suffix = f", {review} do przejrzenia" + (f" (tag „{tag}”)" if tag else "") if review else ""
        tooltip(f"AI: dodano {added} kart dla „{word}”{suffix}", parent=mw, period=5000)

        # Karty są w talii, więc wiersz jest zrobiony — hook add_cards_did_add_note
        # tu nie leci (to nie okno „Dodaj" je zapisało), odhaczamy wprost.
        item = self._list.currentItem()
        if item is not None and self.current_row_id() not in self._marked:
            self._set_row(item, True)

    def _update_counter(self) -> None:
        left = self._list.count() - len(self._marked)
        self._counter.setText(f"{left} do zrobienia · ✓ {self._done_count} w tej sesji")

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
            if confirm and existing and existing != clean_html_normalized(word):
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
