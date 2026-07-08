# LLM Context — Kolejka słówek (`word_queue`)

Panel dokowany do okna „Dodaj": lista haseł z **n8n DataTable** + słowniki w `QWebEngineView`. Po dodaniu notatki wiersz w n8n dostaje `flag_column = true`. Klient n8n z failoverem (domowy adres → Tailscale).

## Rola

Zamyka pętlę zaczętą przez `web_bridge`: słownik → okno „Dodaj" → karta → wiersz odhaczony w n8n. Wcześniej ostatni krok trzeba było klikać ręcznie w `n8n-datatable-viewer`. Panel dokłada do tego przeglądanie kolejki bez wychodzenia z Anki — trzy słowniki w zakładkach, z **tym samym** userscriptem co w Tampermonkeyu.

## Pliki

```
word_queue/
├── __init__.py     # klient n8n (failover, stronicowanie, PATCH), hook, przycisk 📚, menu
├── panel.py        # WordQueuePanel (QDockWidget) + _DictTabs (QTabWidget z leniwym ładowaniem)
├── README.md
└── llm-context.md
```

Zakładka UI: `settings/word_queue_tab.py`. Self-check pod `if __name__ == "__main__"` w `__init__.py` (budowa query/body + failover, bez Anki i bez sieci); `panel.py` nie ma self-checku — to glue do Qt.

## Stack

Python 3.13 (Anki 26.x). Stdlib (`json`, `urllib.parse`, `logging`, `random`, `contextlib`) + `common.http` (`fetch_url`, `post_json`) + Qt (`QDockWidget`, `QListWidget`, `QSplitter`, `QWebEngineView`/`QWebEnginePage`/`QWebEngineProfile`/`QWebEngineScript`). Zależność od `web_bridge` **tylko przez plik** userscripta (odczyt tekstu) — brak importu.

## Model danych

`config.json` → `word_queue` (klucz API w `meta.json`, poza gitem):

```json
{
  "n8n_url": "", "fallback_url": "", "api_key": "", "table_id": "",
  "word_field": "ang", "word_column": "Slowko", "flag_column": "Anki",
  "link_columns": {"diki": "URL", "Longman": "Longman", "Oxford": "Oxford"},
  "page_size": 250, "max_rows": 5000, "random_order": false
}
```

`link_columns` = etykieta zakładki → kolumna z URL-em; kolejność kluczy = kolejność zakładek (JSON zachowuje ją w py3.7+).

## API n8n — fakty ustalone empirycznie

```
GET   {base}/api/v1/data-tables?limit=250              → {"data":[{id,name,columns}]}
GET   {base}/api/v1/data-tables/{id}/rows?<query>      → {"data":[...], "nextCursor": "base64"}
PATCH {base}/api/v1/data-tables/{id}/rows/update       → [ {...trafione wiersze} ]
      body: {"filter":{"type":"and","filters":[...]},"data":{col:bool},"returnData":true}
```

Nagłówek `X-N8N-API-KEY`. Pułapki, każda pokryta asercją w self-checku:

- **`limit` ≤ 250** — większe → `400 request/query/limit must be <= 250`. 992 wiersze = 4 żądania.
- **`filter` nie znosi `+`** — `urlencode` koduje spację jako `+`, n8n odpowiada `400 Parameter 'filter' must be url encoded`. Rozwiązanie: `json.dumps(separators=(",",":"))` (zwarty JSON, zero spacji) **oraz** `urlencode(..., quote_via=urllib.parse.quote)` (spacja → `%20`).
- **`nextCursor` to base64 z `{limit, offset}`** — nie niesie `filter` ani `sortBy`, więc te trzeba powtarzać przy każdej stronie, inaczej kolejna strona zwróci inne wiersze.
- **`dryRun` i `returnData` idą w body**, nie w query (`?dryRun=true` → `400 Unknown query parameter`).
- **`returnData: true`** → odpowiedź to lista trafionych wierszy; `[]` = filtr nic nie trafił. Przy `dryRun` lista ma po dwa wpisy na wiersz (`dryRunState: before|after`), bez `dryRun` — po jednym.
- **`skip` nie istnieje** jako parametr (`400 Unknown query parameter 'skip'`); offset tylko przez kursor.

## Logika (`__init__.py`)

### Failover — `_base_urls` / `_via_hosts`

```python
_active_url = None   # host, który ostatnio odpowiedział
def _base_urls(cfg): [_active_url, cfg["n8n_url"], cfg["fallback_url"]]  # dedup, rstrip('/'), bez pustych
def _via_hosts(cfg, call): # call(base) -> (wartość, błąd)
```

Pierwszy host bez błędu wygrywa i ląduje w `_active_url`; oba padły → `_active_url = None` i zwracany ostatni błąd. Świadome uproszczenia (komentarz `ponytail:` w kodzie): nie odróżniamy „host padł" od „żądanie było złe", więc przy 4xx pukamy niepotrzebnie do drugiego hosta; zapamiętany host trzyma się do pierwszej porażki, więc po powrocie do domu jedziemy przez Tailscale — to ten sam n8n.

**Timeouty są dobrane pod failover, nie pod niezawodność pojedynczego hosta:** `_get_json` woła `fetch_url(max_retries=1, timeout=5)`, bo domyślne 3 retry z backoffem blokowały ~20 s zanim kod spróbował drugiego adresu. `_mark_done` zostawia `post_json(max_retries=2, timeout=8)` — utrata PATCH-a to rozjazd z n8n, warto ponowić 429/5xx.

### Odczyt

- `fetch_tables(cfg)` → `[{"id","name"}]` dla rozwijanki w Ustawieniach (i jako test połączenia).
- `_queue_query(page_size, cursor=None)` → query string. **Bez filtra po fladze** — panel pobiera całą tabelę i sam chowa zrobione, inaczej „Odśwież" gubiłby wiersze odhaczone w tej sesji i cofnięcie ptaszka przestawałoby działać.
- `fetch_queue(cfg)` → `(rows, error)`; pętla po `nextCursor` wewnątrz jednego hosta (błąd → cała paczka od nowa na kolejnym hoście), przerwanie na `len(rows) >= max_rows`.

### Zapis

- `_payload(filters, flag_column, value)` → body PATCH-a (`value` bool — `False` cofa odhaczenie).
- `_set_flag(filters, cfg, value)` → `(liczba_trafionych, błąd)`; waliduje, że odpowiedź to lista.
- `mark_row_done(row_id, cfg, done=True)` — filtr po `id`; **ścieżka panelu**, trafia zawsze.
- `mark_word_done(word, cfg)` — filtr po `word_column`; **fallback bez panelu**, zawodzi przy formie innej niż w tabeli (`sprawl` vs `sprawling`).

### Hooki i wejścia

```python
gui_hooks.add_cards_did_add_note.append(word_queue.on_add_note)
gui_hooks.editor_did_init_buttons.append(word_queue.on_editor_buttons_init)  # przycisk 📚, tylko addMode
_menu_modules.append(word_queue)  # → setup_menu(): „Kolejka słówek (n8n)...”
```

`on_add_note(note)`: `_configured(cfg)` fałsz → moduł śpi. **Panel otwarty → `_panel.note_added()` i koniec** (patch po `id`; uwaga: każda dodana notatka odhacza bieżący wiersz, także dodana obok kolejki). Bez panelu: `clean_html_normalized(note[word_field])` → `mark_word_done` w tle; `matched == 0` → tylko log, błąd → tooltip.

`_toggle_panel(addcards)`: brak konfiguracji → tooltip; panel istnieje → `setVisible(not isVisible())`; inaczej tworzy `WordQueuePanel` i podpina `destroyed → _forget_panel` (zamknięcie okna „Dodaj" wraca do fallbacku po słowie).

## Logika (`panel.py`)

### `_dict_profile()` — jeden `QWebEngineProfile` na proces

Nazwany (`"ankitoolkit-dict"`) → **trwałe ciasteczka** (zgody RODO, logowanie) przeżywają restart. Wstrzykuje `QWebEngineScript` z treścią `web_bridge/dictionaries-to-anki.user.js`:

- `InjectionPoint.DocumentReady` — `document.body` istnieje (userscript wiesza `MutationObserver`).
- `ScriptWorldId.MainWorld` — **konieczne**: w izolowanym świecie skrypt nie dopiąłby przycisków do DOM strony ani nie zobaczyłby jej `fetch`.
- `setRunsOnSubFrames(False)`.

Userscript sam dispatchuje po `location.hostname`, więc `@match` jest niepotrzebny; brak `GM_xmlhttpRequest` → wpada w gałąź `fetch()`, a `http://127.0.0.1` jest dla Chromium *potentially trustworthy*, więc nie leci przez blokadę mixed content. Origin (`https://www.diki.pl`) jest na allowliście `web_bridge.ALLOWED_ORIGIN_HOSTS`, preflight obsługuje `do_OPTIONS`.

### `_DictTabs(QTabWidget)` — leniwe ładowanie

`_labels` (indeks → etykieta), `_views` (lista), `_pending` (indeks → URL czekający na pierwsze wejście). `set_urls(dict)` zapisuje pending, wyszarza zakładki bez URL-a (`setTabEnabled`), przeskakuje z wyszarzonej na `min(self._pending)`, woła `_load_current()`. `_load_current` robi `pop` z `_pending`, więc powrót do zakładki nie przeładowuje strony. Mapowanie po **indeksie**, nie po `tabText()` (accelerator `&` by je popsuł).

### `WordQueuePanel(QDockWidget)`

Stan: `_marked` (zbiór `id` z `flag_column == true`), `_done_count` (licznik per sesja), `_suspend` (flaga wyciszenia sygnałów).

- **`_silent()` — kontekstmenedżer, oś całej klasy.** `QListWidgetItem.setCheckState` **i `setData`** emitują `itemChanged` tak samo jak kliknięcie użytkownika. Bez wyciszenia `_style_item()` (ustawia `ForegroundRole`) wywoływał `_on_item_checked` → drugi PATCH i podwójne zliczenie (objaw: „zaznaczam 1, licznik pokazuje 2"). Menedżer **przywraca poprzednią wartość**, nie `False` — inaczej `_set_check` wewnątrz `_rebuild` odciszyłby resztę przebudowy i cała lista wysłałaby PATCH-e przy starcie. Używa go każda zmiana programowa; ręcznych `_suspend = True` w klasie nie ma.
- `refill()` → `fetch_queue` w tle → `random.shuffle` gdy „Losowo" → **`_marked` odtwarzane z flagi wiersza, nie z pamięci sesji** → `_rebuild(rows)`.
- `_rebuild(rows)` → w `_silent()` czyści i wypełnia listę (`_make_item`), potem `_apply_hiding()`, `_update_counter()`, `_select_first_visible()` (nie startuj od schowanego, zrobionego hasła).
- `_make_item(row)` → tekst = `row[word_column]`, `UserRole` = cały wiersz, flaga `ItemIsUserCheckable`, `CheckState` z `_marked`, `_style_item`.
- `_on_item_changed(current, _prev)` → `_prefill(word)` + `_tabs.set_urls({etykieta: row[kolumna]})`.
- `_on_item_checked(item)` → gdy nie `_suspend`: `_set_row(item, checked)`.
- `_set_row(item, done)` → `mark_row_done(row_id, cfg, done)` w tle; sukces → aktualizacja `_marked`/`_done_count`, `_style_item`, `_apply_hiding`, licznik. **Błąd → `_set_check(item, not done)`** (rollback; lista ma mówić prawdę o n8n).
- `note_added()` → `_prefill(word)` **zawsze** (Anki wywołuje hook po `_load_new_note()`, więc notatka jest już pusta — bez tego drugie znaczenie pisałbyś w puste pole), potem PATCH tylko gdy `row_id not in _marked`. Wyjątek/błąd → `_marked.discard(row_id)`, żeby następna karta ponowiła.
- `_done_and_next()` (przycisk „Zrobione →") → stawia ptaszek **zwyczajnie** (bez `_silent`, żeby PATCH poszedł tą samą ścieżką co klik myszą) i woła `advance()`. Nawigacja natychmiast, PATCH w tle.
- `advance()` → następna **widoczna** pozycja (pomija ukryte); `_apply_hiding()` → `setHidden(hide and checked)`.
- `_on_shuffle_toggled(checked)` → tasuje **natychmiast** (inaczej checkbox wygląda na zepsuty), odznaczenie sortuje po `id`; zapisuje `random_order` przez `save_full_config`.
- `_prefill(word)` → `note[word_field] = word; editor.loadNote()`.

### Semantyka, którą łatwo zepsuć refaktorem

| Zachowanie | Dlaczego |
|---|---|
| dodanie karty **nie** przeskakuje dalej | jedno hasło = kilka znaczeń = kilka kart |
| odhaczenie przy **pierwszym** dodaniu | „ostatnie" jest niepoznawalne; kolumna znaczy „obsłużone" |
| ptaszek = **stan** (`true`/`false`), nie akcja | cofanie pomyłki bez wchodzenia do viewera n8n |
| lista = **cała tabela**, zrobione tylko schowane | „Odśwież" z filtrem `false` gubiłby wiersze i blokował cofanie |
| `_marked` z flagi wiersza, nie z sesji | przeżywa „Odśwież" |

## Zakładka `settings/word_queue_tab.py`

`QFormLayout` z **`setFieldGrowthPolicy(ExpandingFieldsGrow)`** — bez tego macOS trzyma pola przy `sizeHint` i adresy są obcięte. Klucz API przez `common.ui._api_key_widget` (echo Password + „Pokaż"). Combo tabel: placeholder trzyma `table_id` z konfiguracji, więc brak kliknięcia „Pobierz listę" nie kasuje wyboru; `_load_tables()` woła `fetch_tables` z **wartościami z pól** (`_current_cfg()`), nie z zapisanej konfiguracji, i wypełnia `addItem(name, id)` — `apply()` bierze `currentData()`.

## Zmiana w `common/http.py`

`post_json(..., method: str = "POST")` — n8n wymaga `PATCH`. Verb trafia do `urllib.request.Request(method=method)` i do komunikatów logu; retry i nagłówki bez zmian. Zamiast drugiego klienta HTTP.

## Anki API używane

- `gui_hooks.add_cards_did_add_note`, `gui_hooks.editor_did_init_buttons`
- `aqt.dialogs.open("AddCards", mw)`; `AddCards` dziedziczy z `QMainWindow` → `addDockWidget`, `resizeDocks`
- `editor.addMode`, `editor.parentWindow`, `editor.note`, `editor.loadNote()`, `editor.addButton(...)`
- `mw.taskman.run_in_background(task, on_done)` — HTTP nigdy na wątku GUI; `future.result()` w callbacku
- `aqt.utils.tooltip`, `common.config.get_full_config` / `save_full_config`
