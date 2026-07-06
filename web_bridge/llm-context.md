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

- `_cors()` — echo `Origin` (fallback `*`), `Allow-Methods: POST, OPTIONS`, `Allow-Headers: Content-Type`. Dzięki temu userscript/`fetch` z `https://<słownik>` przechodzi bez konfiguracji AnkiConnect.
- `do_OPTIONS` — preflight → `200` + CORS.
- `do_POST` — czyta `Content-Length` bajtów, `json.loads`, waliduje `body["fields"]` (musi być niepustym dict), woła `_run_on_main_sync(lambda: _apply_fields(fields))`. Zawsze odpowiada `200` z `{"ok": not error, "error": error}` (błędy logiczne w polu `error`, nie w kodzie HTTP). Cały blok w `try/except` → wyjątek parsowania też ląduje jako `error`.
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
