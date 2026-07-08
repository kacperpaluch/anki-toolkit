# LLM Context — Web Bridge

Lokalny serwer HTTP wpisujący pola przysłane ze strony WWW do **otwartego okna „Dodaj"** w Anki. Uniwersalny (nie zna słowników) — dołączony userscript zna diki.pl / Oxford Learner's / Longman (LDOCE) / Cambridge (EN i EN-PL).

## Rola

Sluży jako most przeglądarka → edytor Anki bez tworzenia notatek. `POST {"fields": {...}}` wpisuje wskazane pola do edytora otwartego `AddCards` i przeładowuje widok; zapis karty robi użytkownik ręcznie. Alternatywa dla AnkiConnect `guiAddCards` (który zamyka+otwiera okno i podmienia całą notatkę) — tu okno zostaje, ruszane są tylko podane pola.

## Pliki

```
web_bridge/
├── __init__.py                  # całość: serwer HTTP, handler, wpis do edytora
├── dictionaries-to-anki.user.js # userscript (diki/Oxford/LDOCE/Cambridge) — dystrybucja
├── README.md                    # dokumentacja użytkowa
└── llm-context.md               # ten plik
```

Brak `logic.py` i brak zakładki UI (moduł mały, bez konfiguracji w GUI). Self-check pod `if __name__ == "__main__"` testuje `_join` (logika doklejania) bez Anki; reszta to glue do API edytora + `http.server`, więc jej sensowny test = kliknięcie w żywej Anki.

## Stack

Python 3.9+ (Anki 26.x → Python 3.13). Tylko stdlib: `http.server.ThreadingHTTPServer`, `threading`, `json`, `logging`. Zero zewnętrznych zależności, zero zależności od innych modułów wtyczki. Userscript: waniliowy JS + `GM_xmlhttpRequest`/`GM.xmlHttpRequest`.

## Model danych

Toggle: `config.json` → `modules.web_bridge`. Brak innej konfiguracji po stronie Pythona — `HOST, PORT = "127.0.0.1", 8766` to stałe w kodzie. Mapowanie pól żyje w userscripcie (`FIELDS = {headword:'ang', meaning:'pol', definition:'def'}`).

Protokół:

```
POST http://127.0.0.1:8766   Content-Type: application/json
{"fields": {"ang": "mother", "pol": "matka"}}                 # nadpisuje → 200 {"ok": true}
{"fields": {"przyklad": "..."}, "append": true}               # dokleja (sep. <br><br>)
{"fields": {"przyklad": "..."}, "append": true, "separator": "; "}
OPTIONS → 200 (+ nagłówki CORS)
```

`append` i `separator` opcjonalne (`do_POST`: `append=bool(body.get("append"))`, `separator=body.get("separator") or "<br><br>"`).

## Logika (`__init__.py`)

### `start_server(*_, **_)` — hook `profile_did_open`

- Idempotentne: `if _server is not None: return` (profile switch odpala hook ponownie; drugi start pomijany). `_server` = globalna referencja, żeby GC nie ubił serwera.
- `ThreadingHTTPServer((HOST, PORT), _Handler)` w `try/except OSError` — **port zajęty → warning w logu, brak wyjątku** (nie wysadza wtyczki). `serve_forever` w wątku daemon.

### `_Handler(BaseHTTPRequestHandler)`

- `_origin_allowed(origin)` — allowlista hostów `ALLOWED_ORIGIN_HOSTS` (domeny z userscripta). **Brak nagłówka `Origin` → dozwolone** (GM_xmlhttpRequest/curl go nie wysyłają; przeglądarka przy cross-origin POST wysyła ZAWSZE) — dzięki temu obca strona WWW nie wstrzyknie pól przez `fetch()`, nawet simple requestem `text/plain` omijającym preflight.
- `_cors()` — nagłówki CORS (`Allow-Origin: <origin>`, `Allow-Methods`, `Allow-Headers`) tylko gdy `Origin` obecny i na allowliście; faktyczną blokadą jest jednak walidacja w `do_POST`, nie CORS.
- `do_OPTIONS` — preflight → `200` (+ CORS jeśli origin dozwolony).
- `do_POST` — najpierw `_origin_allowed` (**niedozwolony `Origin` → `403` bez przetwarzania**), potem czyta `Content-Length` bajtów (cap `MAX_BODY` = 1 MB), `json.loads`, waliduje `body["fields"]` (musi być niepustym dict), woła `_run_on_main_sync(lambda: _apply_fields(fields))`. Poza 403 zawsze odpowiada `200` z `{"ok": not error, "error": error}` (błędy logiczne w polu `error`, nie w kodzie HTTP). Cały blok w `try/except` → wyjątek parsowania też ląduje jako `error`.
- `log_message` nadpisane na `pass` — cisza w konsoli Anki.

### `_apply_fields(fields, append=False, separator="<br><br>") -> str | None` (WĄTEK GŁÓWNY)

1. `addcards = aqt.dialogs._dialogs.get("AddCards")[1]` — instancja otwartego okna „Dodaj" albo `None` (ten sam wzorzec co AnkiConnect). `None` → zwraca błąd `Okno „Dodaj" nie jest otwarte`.
2. `note = editor.note`; `None` → błąd.
3. `written = [name for name in fields if name in note]` — bierze **tylko pola istniejące** w tym typie notatki. Pusta lista → błąd `Żadne z podanych pól nie istnieje...` (z listą przysłanych nazw).
4. Dla istniejących: `append` → `note[name] = _join(note[name], fields[name], separator)`; inaczej `note[name] = fields[name]` (**nadpisuje**). Potem `editor.loadNote()` (przeładowanie webview) → `addcards.activateWindow()`. Zwraca `None` (sukces).
- Nie zapisuje notatki do kolekcji — to robi użytkownik Enterem.

### `_join(existing, value, separator) -> str` (czysta)

`base = existing.strip(); return (base + separator + value) if base else value`. Puste/białe pole → sama `value`; inaczej doklejenie przez separator. Wydzielona, żeby self-check (`__main__`) testował ją bez Anki (dlatego `import aqt` owinięty w `try/except ImportError`). Używana dla przykładów (`append: true`, separator `<br><br>` = ten sam, po którym `field_splitter` rozdziela pole na `p1`/`p2`/`p3`).

### `_run_on_main_sync(fn, timeout=5) -> str | None`

- Handler HTTP jest na wątku roboczym, edytor tylko na głównym. `threading.Event` + `mw.taskman.run_on_main(wrapper)`; `wrapper` łapie wyjątek → `box["error"]`, w `finally` `done.set()`.
- `done.wait(timeout)` — timeout 5 s → zwraca `Anki nie odpowiedziało w czasie (zajęte?)`. Inaczej `box["error"] or box["value"]`.

## Userscript `dictionaries-to-anki.user.js`

- `@match` diki.pl / oxfordlearnersdictionaries.com / ldoceonline.com / dictionary.cambridge.org (`.../dictionary/...`); `@grant GM_xmlhttpRequest` + `GM.xmlHttpRequest`; `@connect 127.0.0.1, localhost`.
- `send(fields, opts={})` — preferuje `GM_xmlhttpRequest`/`GM.xmlHttpRequest` (omija **mixed content** https→http://127.0.0.1 i CORS); fallback `fetch` (działa w Chrome, w Safari padnie na mixed content). `opts.append` → dokłada `append:true` do body. `makeBtn(label, getFields, opts)` przekazuje `opts` do `send`.
- `clean(s)` = `replace(/\s+/g,' ').trim().replace(/\s*:$/,'')` — normalizacja białych znaków **+ obcięcie końcowego dwukropka** (Cambridge kończy definicje na `:`).
- `inject()` dispatch po `location.hostname`:
  - **diki**: `.dictionaryEntity .hws .hw` → `ang`; `.foreignToNativeMeanings > li` (span.hw) → `pol`; przyciski `→ hasło` / `→ Anki` / `→ oba`.
  - **Oxford**: `h1.headword`→`ang`; `.def`→`def` (definicja w `.sensetop`, **nie** bezpośrednim dzieckiem `.sense`); `.x`→`przyklad` (append).
  - **LDOCE**: `.HWD`→`ang` (nie `.HYPHENATION` — ma kropki „in‧vade"); `.DEF`→`def` (w `.Sense`; `.defRef` = linki, nie łapią się); `.EXAMPLE`→`przyklad` (append; zagnieżdżona ikona audio bez tekstu, `textContent`=zdanie).
  - **Cambridge** (`.../dictionary/...`, EN i EN-PL): `.hw.dhw`→`ang`; `.def`→`def`; `.eg`→`przyklad` (append); `.dtrans-se`→`pol` (tłumaczenie sensu; istnieje tylko na EN-PL, na EN selektor nic nie zwraca).
- `injectButtons(selector, label, field, opts)` — generyczny: przy każdym elemencie dokłada przycisk piszący `{field: text}` z `opts`. Dedupe przez `el.dataset.ankiDone` (niezależne od sąsiadów). `MutationObserver` na `document.body` re-injectuje po zmianach DOM (SPA/leniwe ładowanie).

## Konsumenci userscripta

Dwa, ten sam plik: (1) menedżer userscriptów w przeglądarce; (2) `word_queue/panel.py` → `_dict_profile()` wstrzykuje jego treść jako `QWebEngineScript` (`MainWorld`, `DocumentReady`) do `QWebEngineView` w panelu przy oknie „Dodaj". W (2) `GM_*` nie istnieje → używana jest gałąź `fetch()`; przechodzi, bo `http://127.0.0.1` jest dla Chromium *potentially trustworthy* (nie mixed content), a `Origin` (`https://www.diki.pl` itd.) siedzi w `ALLOWED_ORIGIN_HOSTS`; preflight łapie `do_OPTIONS`. **Fallback na `fetch` jest wymagany** — usunięcie go zabije ścieżkę w Anki. `@match` jest ignorowany w (2), bo `inject()` dispatchuje po `location.hostname`.

## Rejestracja w root `__init__.py`

```python
if _enabled("web_bridge"):
    from . import web_bridge
    gui_hooks.profile_did_open.append(web_bridge.start_server)
```

Brak `setup_menu` (nie dokłada nic do menu Narzędzia) i brak zakładki w `settings/`.

## Anki API używane

- `gui_hooks.profile_did_open`
- `aqt.dialogs._dialogs["AddCards"][1]` (instancja okna „Dodaj")
- `editor.note`, `note[name] = ...`, `name in note`, `editor.loadNote()`, `addcards.activateWindow()`
- `mw.taskman.run_on_main(fn)`
