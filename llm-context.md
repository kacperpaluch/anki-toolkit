# LLM Context — Anki Toolkit

Szybkie podsumowanie projektu dla modeli AI i deweloperów.

---

## Czym jest ten projekt

Scalona wtyczka do Anki łącząca 8 narzędzi w jeden pakiet. Instalowana jako jeden dodatek (`addons21/anki-toolkit/`). Każdy moduł można niezależnie włączyć lub wyłączyć w ustawieniach. Awaria jednego modułu nie blokuje pozostałych.

---

## Stack

| Warstwa | Technologia |
|---|---|
| Język | Python 3.9+ |
| GUI | PyQt6 (dostarczany przez Anki) |
| HTTP | `urllib.request` (stdlib, brak zewnętrznych zależności) |
| HTML parsing | `html.parser` (stdlib) |
| Audio (normalizacja) | ffmpeg (zewnętrzny proces via `subprocess`) |
| AI | REST API (OpenAI / Anthropic / Google Gemini / OpenRouter / CometAPI / Mistral / NVIDIA NIM / OpenCode Go) |
| TTS | Kokoro lokalny serwer (OpenAI-compatible REST) lub OpenRouter TTS API |

**Brak `pip install`** — żadnych zewnętrznych pakietów Python. Jedyną zależnością systemową jest `ffmpeg` (dla `audio_normalizer`).

---

## Struktura i odpowiedzialności

```
anki-toolkit/
├── __init__.py                      # entry point: warunkowo importuje moduły i rejestruje hooki
├── config.json                      # SZABLON domyślny (faktyczna konfiguracja w profilu Anki)
├── config.md                        # dokumentacja konfiguracji
├── manifest.json                    # metadane dla Anki (package name: "anki-toolkit")
│
├── common/                          # współdzielone narzędzia i stałe
│   ├── __init__.py                  # re-eksport wszystkich symboli
│   ├── consts.py                    # ADDON_NAME (wyliczane z __name__ — nazwa folderu wtyczki)
│   ├── html.py                      # clean_html(), clean_html_normalized()
│   ├── text.py                      # unique(), safe_str(), unique_filename(), normalize_float(), split_separator_regex(), plural_pl(), apply_word_replacements()
│   ├── http.py                      # fetch_url(), fetch_text(), post_json() (POST z retry), extract_http_error(), RETRYABLE_STATUS_CODES
│   ├── config.py                    # get_full_config(), save_full_config(), get_module_config(), save_module_config()
│   ├── debug_log.py                 # setup_logging(), konfiguracja logowania wtyczki (plik + konsola)
│   ├── progress.py                  # start_progress()/update_progress()/finish_progress() — natywny pasek mw.progress dla batchy (Anki „busy" → backup/sync się odkłada)
│   └── ui.py                        # widgety Qt: palette (kolory zależne od motywu), hint_label, _expanding_line_edit, _api_key_widget, _scrollable, get_note_type_names, get_fields_for_note_type, get_sample_notes
│
├── settings/                        # dialog ustawień (wszystkie moduły, jeden UI)
│   ├── __init__.py                  # SettingsDialog, open_settings()
│   ├── status_tab.py                # Zakładka: Start — dashboard konfiguracji
│   ├── modules_tab.py               # Zakładka: Moduły
│   ├── dictionary_tab.py            # Zakładka: Słownik
│   ├── ai_generator_tab.py          # Zakładka: AI Generator (Prompty + Dostawcy; workflow przeniesiony do workflows_tab)
│   ├── workflows_tab.py             # Zakładka: Workflowy — lista workflowów + WorkflowEditDialog + checkboxy context_menu
│   ├── prompts_tab.py               # Zakładka: Prompty (edytor + podgląd + kolorowanie składni)
│   ├── prompt_wizard.py             # Dialog „Nowe zadanie AI” (opcjonalny szablon startowy)
│   ├── prompt_templates.py          # Startowe szablony promptów (czysta logika, testowalna)
│   ├── tts_tab.py                   # Zakładka: TTS
│   ├── audio_normalizer_tab.py      # Zakładka: Normalizacja
│   ├── narzedzia_tab.py             # Zakładka: Narzędzia
│   ├── deck_router_tab.py           # Zakładka: Deck Router — tabela reguł tag → talia + przycisk „Uporządkuj istniejące karty…”
│   ├── field_hider_tab.py           # Zakładka: Ukrywanie pól — combo typu notatki + checkboxy pól
│   ├── stats_tab.py                 # Zakładka: Statystyki — dashboard użycia AI
│   └── logs_tab.py                  # Zakładka: Logi — tryb debugowania + podgląd logów wtyczki
│
├── dictionary/                      # Moduł 1
│   ├── __init__.py
│   ├── service.py
│   ├── editor_ui.py
│   ├── browser_ui.py
│   ├── dictionary_service.py
│   └── ipa_service.py
│
├── user_files/                      # dane użytkownika — przeżywają aktualizację wtyczki
│   ├── usage_stats.json             # statystyki użycia AI
│   └── audio_normalizer_history.json
│
├── ai_generator/                    # Moduł 2
│   ├── __init__.py
│   ├── _generator.py
│   ├── editor_ui.py
│   ├── browser_ui.py                # batch AI (równoległy) + batch workflow (per-notatka) + Batch API Anthropic/OpenAI + CollectionOp
│   ├── field_generator.py
│   ├── batch_backfill.py            # Batch API Anthropic + OpenAI (async, ~50% taniej): rdzeń build/submit/poll/apply + backendy per dostawca, persystencja user_files/ai_batches.json
│   ├── template_engine.py
│   ├── stats.py                     # statystyki użycia (user_files/) + match_pricing()
│   ├── workflow.py                  # workflowy (lista): get_workflows/get_context_menu/migrate_workflows/execute_step (AI/Dict/TTS/Rozdziel)
│   └── providers/
│       ├── __init__.py              # rejestr + klasy OpenAI-compatible (OpenAI, OpenRouter, CometAPI, Mistral, NVIDIA NIM)
│       ├── base.py                  # BaseProvider + OpenAICompatProvider + _parse_chat_completion/_parse_messages
│       ├── openai_compat.py
│       ├── anthropic.py             # Anthropic Messages API (bez temperature — deprecated w ich API)
│       ├── google.py                # Google Gemini generateContent
│       ├── opencode_go.py           # OpenCode Go (Chat Completions + Anthropic Messages, auto-detect)
│       └── model_discovery.py
│
├── tts/                             # Moduł 3
│   ├── __init__.py
│   ├── config.py                    # _DEFAULTS, get_tts_config(), validate_config(), get_tasks()
│   ├── api.py                       # generate_audio(), _generate_kokoro(), _generate_openrouter(), fetch_openrouter_tts_models()
│   ├── processor.py                 # wspólne: build_note_work_items(), generate_for_items(), apply_results_to_note(); batch (CollectionOp) + process_single_note()
│   └── editor_ui.py                 # przycisk TTS w toolbarze edytora (async) + PPM na target_field → generuj/regeneruj TTS
│
├── filtered_deck/                   # Moduł 4
│   └── __init__.py
│
├── audio_normalizer/                # Moduł 5
│   ├── __init__.py
│   ├── config.py
│   ├── gui.py
│   ├── logic.py
│   └── watcher.py                   # auto-normalizacja: QFileSystemWatcher na katalogu mediów (debounce 3 s)
│
├── nbsp_remover/                    # Moduł 6
│   ├── __init__.py
│   ├── addcards.py
│   ├── cleaning.py
│   ├── collection.py
│   └── utils.py
│
├── field_splitter/                  # Moduł 7 — rozdzielanie pola na p1, p2, p3...
│   ├── __init__.py                  # setup_menu + add_to_context_menu + batch (CollectionOp)
│   └── splitting.py                 # czysta logika: split_field_value(), parse_target_fields()
│
├── sibling_manager/                 # Moduł 8 — dynamiczne zawieszanie siblingów
│   ├── __init__.py                  # hook reviewer'a + setup_menu (unsuspend all)
│   ├── logic.py                     # process_note() — czysta logika suspend/unsuspend
│   ├── README.md
│   └── llm-context.md
│
├── deck_router/                     # Moduł 9 — kierowanie kart do talii wg tagu
│   ├── __init__.py                  # hook add-cards + route_after_edit() + setup_menu (retro)
│   ├── logic.py                     # match_deck() — czysta logika dopasowania reguły
│   ├── README.md
│   └── llm-context.md
│
├── field_hider/                     # Moduł 10 — chowanie pól tylko w oknie „Dodaj”
│   ├── __init__.py                  # indices_to_hide() + hooki edytora + przycisk 👁
│   ├── README.md
│   └── llm-context.md
│
├── web_bridge/                      # Moduł 11 — mostek HTTP strona WWW → okno „Dodaj”
│   ├── __init__.py                  # serwer HTTP 127.0.0.1:8766 + _apply_fields do edytora
│   ├── dictionaries-to-anki.user.js # userscript: diki / Oxford / Longman / Cambridge → Anki
│   ├── README.md
│   └── llm-context.md
│
├── word_queue/                      # Moduł 12 — kolejka słówek z n8n DataTable + słowniki w Anki
│   ├── __init__.py                  # klient n8n (failover, kursor, PATCH), hook, 📚, setup_menu
│   ├── panel.py                     # WordQueuePanel (QDockWidget) + _DictTabs (leniwy QWebEngineView)
│   ├── README.md
│   └── llm-context.md
│
└── tests/
    └── test_pure_logic.py           # testy czystej logiki bez uruchamiania Anki
```

### Moduły

| Katalog | Co robi | Punkt wejścia |
|---|---|---|
| `common/` | Współdzielone narzędzia: HTML cleaning, HTTP z retry, konfiguracja, widgety Qt, natywny pasek postępu (`progress.py`) — używane przez wszystkie moduły | importowane selektywnie |
| `dictionary/` | Pobiera audio MP3 i IPA z Oxford/Cambridge/Diki/Longman przez scraping HTML; **cache media**: deterministyczna nazwa `dict_{source}_{safe_word}.mp3`, przed fetchem `os.path.exists` w media dir → reuse istniejącego pliku i pominięcie sieci (fetchowane tylko brakujące źródła; persistencja cross-run); edytor (async, `saveNow` przed fetchowaniem) + submenu batchowe (w tle, z paskiem postępu i anulowaniem; zapis jednym `CollectionOp` = jeden krok undo) | `on_editor_buttons_init`, `add_to_context_menu` |
| `ai_generator/` | Generuje treść pól kart przez AI (8 dostawców); fallback modeli (per-prompt `fallback_provider`+`fallback_model` nadpisuje per-dostawca `fallback_model`); per-prompt `temperature` (nadpisuje temperaturę domyślną dostawcy, dziedziczona też przez fallback); batch w tle **równoległy** (`parallel_requests`, per-job `FieldGenerator`) z paczkami i anulowaniem, zapis jednym `CollectionOp`; **workflowy** (lista nazwanych, `config["workflows"]`) — każdy to pozycja w PPM przeglądarki i opcjonalny przycisk edytora (`editor_button`); batch workflow w przeglądarce przetwarza notatki **równolegle** (`_on_workflow_browser`, `ThreadPoolExecutor(parallel_requests)`, per-notatka `FieldGenerator`; kroki w obrębie notatki sekwencyjne), edytor sekwencyjnie jedną notatkę (`run_workflow_editor`); kroki przez `execute_step(note, step, ai_generator=None)` (AI/Słownik/TTS/Rozdziel pole), krok AI z parametrem `fields` (`empty`/`manual`/lista pól); dwa domyślne pipeline'y („Generuj wszystko: puste→TTS→rozdziel→zablokowane", „Rozdziel + generuj naukę (p1–p3)") to teraz zwykłe workflowy; `migrate_workflows()` konwertuje starą sekcję `workflow`; widoczność wbudowanych sekcji PPM przez `config["context_menu"]`; `reasoning_effort` z fallbackiem; pola `manual_only` pomijane w batchu/workflow, dostępne przez submenu „Generuj zablokowane" lub PPM | `on_editor_buttons_init`, `add_to_context_menu`, `migrate_workflows` |
| `tts/` | Generuje audio MP3 przez Kokoro lub OpenRouter TTS API; przycisk w edytorze + submenu w przeglądarce; "Uruchom wszystkie" działa jako jedna operacja; Anuluj odwołuje niewystartowane żądania (`cancel_futures`); zapis batcha jednym `CollectionOp` | `on_editor_buttons_init`, `add_to_context_menu` |
| `filtered_deck/` | Tworzy talię filtrowaną z formularzem ustawień; nazwa talii i deck docelowy konfigurowalne | `setup_menu(parent_menu)` |
| `audio_normalizer/` | Normalizuje głośność plików audio ffmpegiem (EBU R128); po normalizacji synchronizuje zmodyfikowane pliki z Anki media DB przez `write_data()` | `setup_menu(parent_menu)` |
| `nbsp_remover/` | Czyści HTML w polach kart: `&nbsp;` i `<div>`; czysta funkcja `clean_field()` jest współdzielona przez hook dodawania kart, masowe czyszczenie kolekcji (`CollectionOp`) i testy | `setup_menu(parent_menu)` + auto-hook |
| `field_splitter/` | Rozdziela pole źródłowe (np. `przyklad`) po separatorze (`<br><br>`) i **kopiuje** części do pól docelowych (`p1`, `p2`, `p3`…); source nietknięte; browser context menu (batch) + Tools menu (kolekcja); zapis jednym `CollectionOp` | `add_to_context_menu(browser, menu)` + `setup_menu(parent_menu)` |
| `sibling_manager/` | Dynamiczne zawieszanie siblingów: po odpowiedzi na kartę (hook `reviewer_did_answer_card`) zawiesza NEW siblingi dopóki aktywna karta nie dojrzeje (interval ≥ próg, default 30 dni); gdy dojrzeje uwalnia wszystkie zawieszone na raz; karty w nauce/review nie są dotykane; tag `tk-sib-suspended` na notatce; `ignore_tag` wyłącza moduł per-notatka; **sync catch-up**: hook `sync_did_finish` → batch scan wszystkich notatek z NEW siblingami (`process_note_sync` — sprawdza wszystkie non-NEW karty, nie zna konkretnej odpowiedzi); `process_note`/`process_note_sync` zwracają `(suspended, unsuspended)`; **logi**: `log.info` z licznikami po review + po sync scan; **tooltip** po sync scan ("zawieszono X, odwieszono Y", gated przez `show_tooltip`); reaktywny alternatywa dla SibPush; Tools menu → unsuspend all + manual sync catch-up (`CollectionOp`); batch ops zwracają `_changes_for_ui()` (OpChanges `card`/`note`/`study_queues`) po realnej mutacji zamiast pustego `OpChanges()` — inaczej UI nie odświeżało się od razu | `gui_hooks.reviewer_did_answer_card` + `gui_hooks.sync_did_finish` + `setup_menu(parent_menu)` |
| `deck_router/` | Kierowanie kart do talii wg **tagu notatki** (+ opcjonalnie szablonu) — uzupełnia natywny Deck Override (tylko per-szablon). Reguła `{tag, template?, deck}`; `match_deck(tags, template_name, rules)` (czysta) zwraca deck pierwszej pasującej reguły albo `None` (tag na notatce **oraz** szablon zgodny/pusty=wszystkie); `_apply(col, note_ids, rules)` przenosi karty `col.set_deck` do `col.decks.id(deck, create=True)`, pomija już-właściwe i bez dopasowania (notatka bez reguły nietknięta); trzy wyzwalacze: hook `add_cards_did_add_note` (okno Dodaj), `route_after_edit(parent, note_ids)` wołane z `ai_generator/browser_ui._save_changed_notes` (po AI-batchu/workflow; guard `_module_enabled()`+reguły w środku, soft-import = brak twardej zależności), `setup_menu`/`run_reorganize(rules=None)`/`confirm_reorganize` → retro `col.find_notes` po tagach reguł (`CollectionOp`); UI `DeckRouterTab` (tabela, szablon+talia z list rozwijanych z kolekcji, talia edytowalna, przycisk „Uporządkuj istniejące karty…" działający na regułach z tabeli) | `gui_hooks.add_cards_did_add_note` + `route_after_edit` + `setup_menu(parent_menu)` |
| `field_hider/` | Chowa pola w edytorze **tylko w oknie „Dodaj”** (guard `editor.addMode` — w przeglądarce/edycji istniejącej karty hook wychodzi od razu). `indices_to_hide(field_names, targets)` (czysta) → 0-based indeksy pól do ukrycia; `on_editor_load_note` wstrzykuje `<style id="hf-style">` z `body:not(.hf-reveal) .field-container[data-index="i"]{display:none!important}` przez `editor.web.eval` (idempotentne, CSS przez `json.dumps`); ukrycie **czysto wizualne**, nic nie kasuje w notatce; `on_editor_buttons_init` dodaje przycisk 👁 (tylko w „Dodaj”) togglujący klasę `hf-reveal` na `<body>` → tymczasowo odsłania. Config `{typ_notatki: [pola]}`; UI `FieldHiderTab` (combo typu + checkboxy pól, `_store_current()` przed przełączeniem typu). Adaptacja wtyczki `anki-hide` (dodano guard `addMode`). Brak `setup_menu` | `gui_hooks.editor_did_load_note` + `gui_hooks.editor_did_init_buttons` |
| `web_bridge/` | Lokalny serwer HTTP `127.0.0.1:8766` (stdlib `ThreadingHTTPServer`, wątek daemon) wpisujący pola przysłane ze strony WWW do **otwartego okna „Dodaj”** — uniwersalny most przeglądarka→edytor bez tworzenia notatek (alternatywa dla AnkiConnect `guiAddCards`, który zamyka+otwiera okno i podmienia całą notatkę). `POST {"fields":{nazwa:wartość}, "append"?:bool, "separator"?:str}` → `_apply_fields(fields, append, separator)` (na wątku głównym przez `mw.taskman.run_on_main` + `threading.Event`, timeout 5 s): `aqt.dialogs._dialogs["AddCards"][1]` (None→błąd „okno nie otwarte”), wpisuje **tylko istniejące** pola (`name in note`); `append` → `_join(existing, value, sep)` dokleja przez separator (domyślnie `<br><br>`), inaczej **nadpisuje**; `editor.loadNote()`+`activateWindow()`; nie zapisuje notatki (zatwierdza user). Handler zwraca `200 {"ok":bool,"error":str?}`; `Origin` spoza allowlisty `ALLOWED_ORIGIN_HOSTS` (domeny słowników; **brak nagłówka = dozwolone** — GM_xmlhttpRequest/curl go nie wysyłają, a przeglądarka przy cross-origin POST zawsze) → `403`, więc obca strona nie wstrzyknie pól nawet simple requestem omijającym preflight; body cap `MAX_BODY` 1 MB; `_cors()` (+OPTIONS preflight) tylko dla dozwolonych originów → działa z `https://<słownik>` bez konfiguracji AnkiConnect; port zajęty → warning, moduł nie wstaje. Self-check (`__main__`) na `_join`. Dołączony userscript `dictionaries-to-anki.user.js` (diki→`ang`/`pol`; Oxford `h1.headword`→`ang`, `.def`→`def`, `.x`→`przyklad` append; LDOCE `.HWD`→`ang`, `.DEF`→`def`, `.EXAMPLE`→`przyklad` append; Cambridge `.hw.dhw`→`ang`, `.def`→`def`, `.eg`→`przyklad` append, `.dtrans-se`→`pol` [tylko EN-PL]; `clean()` ucina końcowy `:`; `GM_xmlhttpRequest`/`GM.xmlHttpRequest` omija mixed content https→http). Brak zakładki, brak `setup_menu`, tylko stdlib | `gui_hooks.profile_did_open` → `start_server` |
| `word_queue/` | Kolejka haseł z **n8n DataTable** + słowniki w `QWebEngineView` dokowane do okna „Dodaj”. Klient n8n z **failoverem** (`_via_hosts`: ostatni działający → `n8n_url` → `fallback_url`/Tailscale; zwycięzca cache'owany w `_active_url`; `_get_json` = `fetch_url(max_retries=1, timeout=5)`, bo domyślne 3 retry blokowały ~20 s przed próbą drugiego hosta; `_mark_done` = `post_json(method="PATCH", max_retries=2)`). `fetch_queue` pobiera **całą tabelę** stronicując po `nextCursor` (base64 `{limit,offset}` — `sortBy` trzeba powtarzać; `limit` ≤ 250; bezpiecznik `max_rows`); **bez filtra po fladze**, bo panel chowa zrobione sam — inaczej „Odśwież” gubiłby wiersze odhaczone w sesji i blokował cofanie. `_queue_query`: `json.dumps(separators=(",",":"))` + `quote_via=quote` (n8n zwraca `400 must be url encoded`, gdy spacja wyjdzie jako `+`). `_set_flag(filters, cfg, value)` → PATCH `{filter, data:{flag:bool}, returnData:true}` (`dryRun`/`returnData` w **body**, nie query); `mark_row_done(id)` = ścieżka widocznego panelu (trafia zawsze), `mark_word_done(word)` = fallback bez panelu albo przy panelu ukrytym (zawodzi przy `sprawl` vs `sprawling`). `panel.py`: `_DictTabs` ładuje URL dopiero przy pierwszym wejściu w zakładkę (Chromium ≈100 MB), mapuje po indeksie nie `tabText()`, a zakładki bez URL-a wyszarza i ładuje `about:blank`, żeby nie zostawała strona poprzedniego hasła; `_dict_profile()` = nazwany `QWebEngineProfile` (trwałe ciasteczka) wstrzykujący **ten sam** `web_bridge/dictionaries-to-anki.user.js` w `MainWorld`/`DocumentReady`; `_silent()` (kontekstmenedżer, przywraca **poprzedni** stan) wycisza `itemChanged` przy zmianach programowych — `setCheckState` **i `setData`** je emitują, bez tego `_style_item` powodował drugi PATCH i podwójne zliczenie. Ptaszek = **stan** wiersza (`true`/`false`, rollback przy błędzie), dodanie karty przy widocznym panelu odhacza po `id` ale **nie przeskakuje** (jedno hasło = kilka znaczeń; `_prefill` wpisuje hasło z powrotem, bo hook leci po `_load_new_note()`). Self-check (`__main__`): query, body, failover | `gui_hooks.add_cards_did_add_note` → `on_add_note`, `gui_hooks.editor_did_init_buttons` → `on_editor_buttons_init` (📚), `setup_menu` |
| `settings/` | Zbiorczy dialog ustawień dla wszystkich modułów | `open_settings()` |

---

## Jak Anki ładuje wtyczkę

Anki importuje `anki-toolkit/__init__.py` przy starcie. Główny `__init__.py`:
1. Czyta sekcję `modules` z konfiguracji
2. Importuje tylko włączone moduły (`true` w sekcji `modules`)
3. Rejestruje hooki edytora (natychmiast, bez `main_window_did_init`); przy włączonym `ai_generator` wywołuje raz `migrate_workflows()` (stary `workflow` → `workflows`); kolejność to AI/workflowy → słownik → TTS, więc przyciski workflowów są pierwsze
4. Rejestruje **jeden** centralny hook `_on_browser_context_menu` — tworzy submenu **Anki Toolkit**, wywołuje `ai_generator.add_to_context_menu` (workflowy + submenu pól), a sekcje pozostałych modułów (dictionary/tts/field_splitter) tylko gdy włączone i niewyłączone w `config["context_menu"]` (czytane świeżo przy każdym kliknięciu)
5. Po załadowaniu okna głównego tworzy submenu **Narzędzia → Anki Toolkit** i przekazuje je do `setup_menu(parent_menu)` każdego modułu
6. Dodaje na końcu submenuu separator i pozycję **Ustawienia...**

Wyłączony moduł nie jest importowany w ogóle — brak hooków, brak wpisów w menu.

### Wzorce hooków

```python
# Editor — przycisk w toolbarze edytora
gui_hooks.editor_did_init_buttons.append(fn)

# Browser — menu kontekstowe (prawy klik) — SCENTRALIZOWANE w root __init__.py
# Moduły NIE rejestrują własnych hooków; zamiast tego eksportują:
#   add_to_context_menu(browser, menu)
# Root tworzy submenu "Anki Toolkit" i przekazuje je do każdego modułu.
addHook("browser.onContextMenu", _on_browser_context_menu)  # tylko w root

# Menu Narzędzia — po załadowaniu okna głównego
gui_hooks.main_window_did_init.append(fn)
```

### Sygnatura `setup_menu`

```python
def setup_menu(parent_menu=None):
    menu = parent_menu or mw.form.menuTools  # fallback jeśli wywołane poza root __init__
    action = QAction("...", mw)
    menu.addAction(action)
```

---

## Konfiguracja

### Jak działa przechowywanie konfiguracji

- `config.json` w folderze wtyczki to **szablon domyślny** — nigdy nie jest nadpisywany
- `mw.addonManager.getConfig(name)` zwraca konfigurację użytkownika (nadpisuje defaults)
- `mw.addonManager.writeConfig(name, dict)` zapisuje do profilu Anki (`addons21/{id}/meta.json`)
- Zmiany wprowadzone w **Narzędzia → Anki Toolkit → Ustawienia...** są trwałe między sesjami
- `common/config.py` udostępnia helpery: `get_full_config()`, `save_full_config()`, `get_module_config(module_key, defaults)`, `save_module_config(module_key, cfg)` — używane przez wszystkie moduły

### Dialog ustawień (`settings/`)

Otwarcie: **Narzędzia → Anki Toolkit → Ustawienia...**

Struktura:
```
settings/
├── __init__.py              # SettingsDialog, open_settings()
├── status_tab.py            # StatusTab — dashboard gotowości, postęp Batch API, pipeline, lista problemów
├── modules_tab.py           # ModulesTab
├── dictionary_tab.py        # DictionaryTab
├── ai_generator_tab.py      # AIGeneratorTab + model discovery + embedded PromptsTab; dostawcy jako lista+detal (bez workflow)
├── workflows_tab.py         # WorkflowsTab + WorkflowEditDialog — lista workflows + kroki + checkboxy context_menu
├── prompts_tab.py           # PromptsTab (embedded in AI Generator tab, not standalone)
├── prompt_wizard.py         # NewPromptDialog — dialog „Nowe zadanie AI”
├── prompt_templates.py      # TEMPLATES + build_prompt() + guess_field() — czysta logika
├── tts_tab.py               # TTSTab
├── audio_normalizer_tab.py  # AudioNormalizerTab
├── narzedzia_tab.py         # NarzedziaTab
├── stats_tab.py             # StatsTab — dashboard użycia AI
└── logs_tab.py              # LogsTab — tryb debugowania + podgląd bufora logów
```

Zakładki (9 zakładek):
- **Start** — dashboard: wiersz „Szybki dostęp" (przyciski-skróty do AI/Workflowy/TTS/Słownik), klikalne kafelki kroków reprezentatywnego workflow (✓/⚠/○) w `FlowLayout` (zawijane, bez strzałek), globalny status (Gotowe / N rzeczy do zrobienia — liczony tylko z modułów faktycznie używanych), sekcja „Do zrobienia" (jedyne miejsce z problemami, przyciski Napraw), wiersz pozostałych modułów; reprezentatywny workflow = ten z `editor_button`, inaczej pierwszy; workflowy zawsze aktywne w PPM (brak stanu „wyłączony"); `refresh(cfg)` odbudowuje zawartość — SettingsDialog wywołuje ją przy każdym przejściu na Start z configiem zebranym z **niezapisanego** stanu pozostałych zakładek (`_collect_config()`)
- **Moduły** — włącz/wyłącz każdy moduł (wymaga restartu)
- **Słownik** — pola, format IPA, wiktionary_ipa_fallback, diki_ipa_fallback + diki_ipa_fallback_source, przyciski w edytorze, limity sieci (max_retries, page_timeout, mp3_timeout)
- **AI Generator** — podzakładki **Prompty**, **Dostawcy** (workflow przeniesiony do osobnej zakładki Workflowy); każdy prompt zapisuje dostawcę, model, opcjonalnie `temperature` (nadpisuje temperaturę domyślną dostawcy; „— domyślna dostawcy" = dziedzicz) oraz `fallback_provider` i `fallback_model` (nadpisuje fallback dostawcy); listy modeli filtrują po dowolnym fragmencie nazwy; dostawcy AI są rozdzieleni na karty z polem „Model zapasowy" (fallback_model), **limity RPM + maks. równoległych są per dostawca** na jego karcie (OpenRouter ma dodatkowo „tylko :free"), a limity batch/parallel_requests/retry/request timeout są w **zwijanej** sekcji **Zaawansowane** (domyślnie schowana)
- **Workflowy** — `WorkflowsTab`: lista nazwanych workflowów (Dodaj/Edytuj/Usuń, ▲▼ = kolejność w PPM), `WorkflowEditDialog` (nazwa, `editor_button`, kroki AI/Słownik/TTS/Rozdziel z parametrami — dialogi `_pick_ai_fields`/`_pick_dicts`); na dole checkboxy `context_menu` (widoczność wbudowanych sekcji PPM); `apply()` zapisuje `config["workflows"]` i `config["context_menu"]` (jedyne miejsce zapisu tych kluczy)
- **TTS** — dostawca (Kokoro / OpenRouter), klucz API OpenRouter (lub współdzielony z AI), model (z przyciskiem Pobierz), głosy (QTableWidget z checkboxami + przyciskami ▶ podglądu per głos — `generate_audio` z krótkim sample → `av_player.play_file`), zadania TTS (Dodaj/Edytuj/Usuń), speed, wydajność (max_workers, max_retries, timeout)
- **Normalizacja** — ścieżka ffmpeg (z przyciskiem "Sprawdź"), opcje loudnorm, liczba wątków
- **Narzędzia** — trzy sekcje jako QGroupBox: Talia filtrowana (deck_name, search_deck), Czyszczenie HTML (show_tooltip, auto_run_startup, skip_field), Rozdzielanie pól (source_field, separator, target_fields jako tekst przecinkami, overwrite checkbox)
- **Statystyki** — dashboard użycia AI: wybór zakresu (dziś / 7 / 30 / 365 dni / wszystko / własny zakres dat od–do przez QDateEdit z kalendarzem), tabela per model (requesty, błędy, tokeny wej./wyj., wygenerowane pola, **szacowany koszt**) + osobna tabela **TTS** (requesty, błędy, znaki, pliki, koszt per znak; `record_tts()` wołane z `tts/api.generate_audio()` dla Kokoro i OpenRouter), licznik zaktualizowanych notatek, przyciski Odśwież/Pobierz ceny (OpenRouter)/Resetuj; przycisk „Pobierz ceny" zapisuje pełny katalog cen (chat + TTS) w configu pod `pricing.catalog`, a dopasowanie przez `stats.match_pricing()` (normalizacja nazw: data-sufiks, kropki/myślniki, prefix-match) odbywa się przy każdym odświeżeniu — modele pojawiające się w statystykach później też dostają ceny; dane z `ai_generator/stats.py`
- **Logi** — checkbox trybu debugowania (config `debug.enabled`, działa od razu po przełączeniu), podgląd bufora logów wtyczki w pamięci (`common/debug_log.py`, ostatnie 2000 wpisów, auto-odświeżanie co 2 s), przyciski Odśwież/Kopiuj/Wyczyść; bez debugowania rejestrowane INFO+, z debugowaniem DEBUG+

### Sekcja `modules` — włączanie/wyłączanie modułów

```json
"modules": {
    "dictionary":        true,
    "ai_generator":      true,
    "tts":               true,
    "filtered_deck":     true,
    "audio_normalizer":  true,
    "nbsp_remover":      true,
    "field_splitter":    true,
    "sibling_manager":   true,
    "deck_router":       true,
    "field_hider":       true,
    "web_bridge":        true,
    "word_queue":        true
}
```

Brakujący klucz = `true` (domyślnie włączony). Zmiana wymaga restartu Anki.

### Sekcje konfiguracyjne modułów

| Sekcja | Moduł | Edycja przez UI |
|---|---|---|
| `dictionary` | `dictionary/` | Zakładka Słownik |
| `tts` | `tts/` | Zakładka TTS |
| `ai_generator` | `ai_generator/` | Zakładka AI Generator (w tym `skip_tags`) + Prompty |
| `audio_normalizer` | `audio_normalizer/` | Zakładka Normalizacja |
| `filtered_deck` | `filtered_deck/` | Zakładka Narzędzia (sekcja Talia filtrowana) |
| `nbsp_remover` | `nbsp_remover/` | Zakładka Narzędzia (sekcja Czyszczenie HTML) |
| `field_splitter` | `field_splitter/` | Zakładka Narzędzia (sekcja Rozdzielanie pól) |
| `sibling_manager` | `sibling_manager/` | Zakładka Narzędzia (sekcja Sibling Manager) |
| `deck_router` | `deck_router/` | Zakładka Deck Router (tabela reguł tag → talia) |
| `field_hider` | `field_hider/` | Zakładka Ukrywanie pól (combo typu notatki + checkboxy pól) |
| `web_bridge` | `web_bridge/` | — (tylko toggle; port w kodzie, mapowanie pól w userscripcie) |
| `word_queue` | `word_queue/` | Zakładka Kolejka słówek (adresy n8n + klucz API + rozwijanka tabel + mapowanie kolumn) |
| `workflows` | `ai_generator/` | Zakładka Workflowy (lista nazwanych workflowów) |
| `context_menu` | `ai_generator/` | Zakładka Workflowy (widoczność wbudowanych sekcji PPM) |

---

## Kluczowe pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Master entry point — tu dodajesz nowe moduły i wpisy w `modules` |
| `config.json` | Szablon domyślny (nie nadpisywany — patrz wyżej) |
| `common/consts.py` | `ADDON_NAME` — wyliczane z `__name__` (nazwa folderu wtyczki), używane przez wszystkie moduły; config działa nawet gdy folder nie nazywa się `anki-toolkit` |
| `common/html.py` | `clean_html()`, `clean_html_normalized()` — czyszczenie HTML, używane przez dictionary, ai_generator, tts |
| `common/text.py` | `unique()`, `safe_str()`, `unique_filename()`, `normalize_float()`, `split_separator_regex()` (separator splitu z tolerancją białych znaków), `plural_pl()` (polska liczba mnoga), `apply_word_replacements()` (zamiana całych słów, case-insensitive z zachowaniem wielkiej litery — używane przez TTS przed syntezą) |
| `common/http.py` | `fetch_url()` / `fetch_text()` (GET z retry), `post_json()` (POST bytes z retry na 429/5xx; param `method="POST"` pozwala wysłać `PATCH` — używa `word_queue`; zwraca `(bytes\|None, err\|None)` — używane przez providerów AI i TTS), `extract_http_error()` (parsuje JSON body HTTPError), `RETRYABLE_STATUS_CODES` |
| `common/config.py` | `get_full_config()`, `save_full_config()`, `get_module_config()`, `save_module_config()` |
| `common/progress.py` | `start_progress(label, total, title)` → cancel_flag, `update_progress(cancel_flag, label, done, total)` (czyta `mw.progress.want_cancel()` na głównym wątku), `finish_progress()` — natywny pasek `mw.progress` dla batchy (dictionary/tts/ai_generator/audio_normalizer); trzyma Anki „busy", więc automatyczny backup/sync się odkłada i nie zasłania przycisku Anuluj |
| `common/debug_log.py` | Bufor logów w pamięci (deque 2000 wpisów) — `setup_logging()` (handler na loggerze pakietu, wołane przy starcie), `set_debug()`, `get_log_lines()`, `get_log_seq()`, `clear_log()`; wszystkie moduły logują przez `logging.getLogger(__name__)` i propagują do tego bufora |
| `common/ui.py` | Widgety Qt: `palette()` (kolory zależne od motywu — jedno źródło dla wszystkich zakładek), `hint_label()`, `_expanding_line_edit`, `_filterable_combo` (QCompleter z MatchContains), `_api_key_widget`, `_scrollable`, `collapsible_section(title, expanded)` (zwijana sekcja „zaawansowane" — toggle ▸/▾), `FlowLayout` (zawijanie kafelków do nowego wiersza), `get_note_type_names`, `get_fields_for_note_type`, `get_sample_notes` |
| `settings/__init__.py` | Dialog ustawień — `open_settings()`, `SettingsDialog`; nawigacja **pionowa**: `QListWidget` (ikony + nieklikalne nagłówki grup TREŚĆ/SYSTEM/WGLĄD) + `QStackedWidget`; `_open_tab(title)` i `_on_nav_changed(row)` mapują wiersz→stronę (status_tab nawiguje po `title`); kolejność zakładek wg zadania |
| `settings/status_tab.py` | Zakładka Start — dashboard: wiersz „Szybki dostęp" (skróty), sekcja „Batch API — postęp" (`_add_batch_progress` — widoczna tylko gdy coś działa: paski `QProgressBar` „wysłane/wszystkie zapytania" per zadanie z `batch_backfill.active_jobs()`, batche w toku per dostawca z `pending_batches()`, przyciski „Sprawdź batche teraz" → `check_pending_batches(silent=False)` i „Odśwież" → `refresh(self._last_cfg)`), kafelki kroków reprezentatywnego workflow w `FlowLayout` (zawijane), globalny status, lista „Do zrobienia", wiersz modułów pomocniczych; workflowy zawsze aktywne (z PPM) — brak stanu „wyłączony"; `refresh(cfg)` przebudowuje widok (`_clear_layout` odpina widgety natychmiast, by uniknąć widm) |
| `settings/modules_tab.py` | Zakładka Moduły — `ModulesTab` |
| `settings/dictionary_tab.py` | Zakładka Słownik — `DictionaryTab` |
| `settings/ai_generator_tab.py` | Zakładka AI Generator — `AIGeneratorTab`; podzakładki Prompty + Dostawcy (edytor workflow usunięty — przeniesiony do `workflows_tab.py`); nazwy dostawców z rejestru `PROVIDERS`/`PROVIDER_LABELS`; dostawcy jako lista z detalem (✓/○ wg klucza API, aktualizowane na żywo); combo modelu ładowane z `cached_models` (cache przeżywa restart); przycisk **Pobierz** fetchuje z API i aktualizuje combo + `cached_models` w `apply()`; pole „Model zapasowy" (fallback_model) per dostawca; **limit RPM + maks. równoległych per dostawca** (OpenRouter dodatkowo checkbox „tylko :free", zapisywany jako `rate_limit_free_only`); zwijana sekcja Zaawansowane (`collapsible_section`, domyślnie schowana): batch/parallel/retry/timeout |
| `settings/workflows_tab.py` | Zakładka Workflowy — `WorkflowsTab` (lista workflowów + checkboxy `context_menu`) i `WorkflowEditDialog` (nazwa, `editor_button`, kroki); helpery `_pick_ai_fields` (empty/manual/konkretne pola), `_pick_dicts` (wybór słowników, pusty = pomiń), `_step_label`; `apply()` zapisuje `config["workflows"]` + `config["context_menu"]` |
| `settings/prompts_tab.py` | Zakładka Prompty — `PromptsTab`; lista zadań pogrupowana nagłówkami per typ notatki (nieklikalne wiersze) + combobox filtra po typie notatki nad listą; cała lista renderowana z `self._data` przez `_rebuild_list(select_key)` (add/delete/move/filtr nie synchronizują itemów ręcznie); kolejność generowania (▲▼ przesuwa tylko w obrębie tego samego typu + dopisek „zależy od"), wybór dostawcy, modelu i temperatury per prompt (QDoubleSpinBox z wartością specjalną „— domyślna dostawcy") (pobieranie modeli przyciskiem **Pobierz** + filtrowanie MatchContains + cache `cached_models` z configu), pola dostawcy/modelu zapasowego (`fallback_provider` + `fallback_model` z własnym przyciskiem **Pobierz** — listy współdzielone z dostawcą głównym), comboboxy typu notatki i pola docelowego z danymi z kolekcji, checkbox „Tylko na żądanie" (`manual_only`), przyciski „Wstaw pole ▾" i „Wstaw warunek ▾", kolorowanie składni (`_TemplateHighlighter`), walidacja na żywo, przycisk „Podgląd…" (`PromptPreviewDialog`) |
| `settings/prompt_wizard.py` | `NewPromptDialog` — jednostronicowy dialog nowego zadania: typ notatki, pole docelowe, dostawca, model, checkbox „Tylko na żądanie" (`manual_only`) + opcjonalny szablon startowy (domyślnie pusty); po wybraniu szablonu mapowanie pól, blok `{% if %}` z checkboxa |
| `settings/prompt_templates.py` | `TEMPLATES` (definicja, przykłady, część mowy, IPA, pusty), `build_prompt()`, `guess_field()` — czysta logika bez Anki, testowana w `tests/` |
| `settings/tts_tab.py` | Zakładka TTS — `TTSTab`; głosy OpenRouter w `QTableWidget` z checkboxami + przyciskami ▶ — `_play_voice_sample(voice)` → `generate_audio` w tle → `av_player.play_file("_tts_preview.mp3")`; sekcja „Wydajność i sieć" (wątki/retry/timeout) w zwijanej `collapsible_section` (domyślnie schowana) |
| `settings/audio_normalizer_tab.py` | Zakładka Normalizacja — `AudioNormalizerTab` |
| `settings/narzedzia_tab.py` | Zakładka Narzędzia — `NarzedziaTab` |
| `settings/stats_tab.py` | Zakładka Statystyki — `StatsTab`, dashboard użycia AI (czyta `ai_generator/stats.py`) |
| `settings/logs_tab.py` | Zakładka Logi — `LogsTab`, tryb debugowania + podgląd bufora logów (czyta `common/debug_log.py`) |
| `ai_generator/stats.py` | Lokalne statystyki użycia — `record_request()`, `record_note()`, `record_tts()` (TTS: requesty/błędy/znaki/pliki per model), `get_stats(days=None, start=None, end=None)` (zwraca też sekcję `tts`), `reset_stats()`, `match_pricing()` (dopasowanie cennika OpenRouter do kluczy statystyk); liczniki per dzień kalendarzowy, zapis do `user_files/usage_stats.json` (migracja legacy przy imporcie), thread-safe (`threading.Lock`) |
| `ai_generator/_generator.py` | Tylko `get_config()` — sekcja `ai_generator` z configu; bez singletona, każde uruchomienie tworzy świeży `FieldGenerator(get_config())` (brak współdzielonego stanu, zmiany ustawień działają od razu) |
| `ai_generator/providers/__init__.py` | Rejestr providerów AI + fabryka `get_provider()`; 5 klas zgodnych z OpenAI (`OpenAIProvider`/`OpenRouterProvider`/`CometAPIProvider`/`MistralProvider`/`NvidiaProvider`) jako cienkie podklasy `OpenAICompatProvider` |
| `ai_generator/providers/base.py` | `BaseProvider` (ABC — implementuj `call_api()`) + wspólne parsery `_parse_chat_completion()`/`_parse_messages()`; `OpenAICompatProvider` z gotowym `call_api()` dla endpointów Bearer-auth Chat Completions |
| `ai_generator/providers/openai_compat.py` | Helpery dla OpenAI-compatible Chat Completions: wykrywa modele OpenAI reasoning, pomija `temperature`, parsuje `message.content` string/list, wykrywa błąd unsupported `reasoning_effort` |
| `ai_generator/providers/opencode_go.py` | OpenCode Go — auto-detect formatu (Chat Completions vs Anthropic Messages), `User-Agent` header, reasoning jako wolny tekst |
| `ai_generator/providers/model_discovery.py` | Pobieranie dostępnych modeli z API każdego providera; bliźniacze endpointy przez wspólny `_fetch_simple()`, dispatcher `fetch_models()` |
| `ai_generator/batch_backfill.py` | Backfill przez **Batch API** (async, ~50% taniej) dla `anthropic` i `openai` — osobny od ścieżki sync, bez fallbacku. Rdzeń niezależny od dostawcy: `build_items(notes, config, only_fields)` → `(items, skipped)` (wspólny `iter_note_fields`, `custom_id="i{n}"`, prompt ze stanu notatki z chwili wysyłki, tylko dostawcy z `_ELIGIBLE_PROVIDERS`), `summarize(items)` (podsumowanie per dostawca/model do dialogu), `submit(items, config)` grupuje i tworzy **osobny rekord na backend/model** (Anthropic: jeden batch; OpenAI: batch per model — API wymaga jednego modelu; OpenAI akceptuje `create` i _asynchronicznie_ failuje batche ponad limit kolejki org (~2M), więc dzielimy na paczki `_chunk_by_tokens` poniżej `openai_batch_token_budget` (dom. 1,5M, est. `len//4 + openai_batch_output_reserve`) i wysyłamy do wyczerpania budżetu **z odjęciem `_pending_openai_tokens()`** (naszych batchy w locie, pole `enq_tokens` w rekordzie); reszta odłożona). Create bywa też odrzucany **synchronicznie** 400-tką „Enqueued token limit" — pierwszy błąd create **kończy przebieg**, błąd enqueued ustawia **backoff 30 min** (`_openai_blocked_until`, `openai_budget_left()` → 0), a plik wgrany pod nieudany create jest kasowany (`_delete_openai_file`). **Auto-dosyłanie**: `add_job(nids, only_fields, total, sent)` zapisuje zaznaczenie jako zadanie w `ai_batches.json` (liczniki `total`/`sent` → `record_job_progress(records)` → string „S/T zapytań (p%)"); `active_jobs`/`finish_job`/`job_expired` (24h) + `inflight_fields()` ((nid,field) w oczekujących batchach) obsługują cykl `browser_ui._advance_jobs` (timer co minutę → kolejny plaster pustych pól pod budżetem). `poll_results(config)` dispatch po `record["provider"]` → `_POLLERS` → **znormalizowany** wynik `{custom_id, ok, text, in_tok, out_tok}` (log INFO per zakończony batch); batch z błędem odpytania starszy niż `_BATCH_MAX_AGE_D` (7 dni, `_batch_expired`) → status `expired` (trwale nieodpytywalny, np. 404 po retencji — inaczej wisiałby w `in_progress` i `inflight_fields()` blokowałoby jego pola na zawsze), `apply_results(col, ended)` (MAIN THREAD) pisze **tylko w puste pola**, dedup per nid, brakujące wyniki (OpenAI expired) liczone jako `failed`, `stats.record_request(provider, ...)`; **nie** oznacza batchy — `mark_applied(bids)` woła caller **po commicie notatek**, potem `cleanup_openai_files(records, config)` (tło) kasuje pliki wejściowe/wynikowe ze storage OpenAI. Backendy: Anthropic (`_submit_anthropic`/`_poll_anthropic` — inline requests, `results_url`, temperature pominięte), OpenAI (`_submit_openai`/`_poll_openai` — upload JSONL przez Files API multipart `_multipart`, `create batch(input_file_id)`, download `output_file_id`; body przez `add_temperature_if_supported`/`add_reasoning_effort_if_supported`). Rekord ma pole `provider` (stare bez niego = `anthropic`). Persystencja `user_files/ai_batches.json` (`in_progress`/`applied`/`expired`, lista `jobs`). UI + auto-poll przy `profile_did_open` w `browser_ui.check_pending_batches` |
| `ai_generator/field_generator.py` | Główna logika generowania — `process_note(note, only_fields=None, overwrite=False)`; selekcja pól wydzielona do `iter_note_fields(note, config, only_fields, overwrite)` (skip_tags, note_type, only_fields, manual_only, puste pole) współdzielonej z `batch_backfill`; `only_fields` filtruje scope pól, `overwrite=True` nadpisuje pełne; pola z `manual_only=True` pomijane gdy `only_fields=None` (batch/workflow/przycisk AI); zwraca `dict[str, str]` wypełnionych pól; błędy konfiguracji providera → `last_error` + cache porażki (bez dialogów z wątku tła); **fallback modeli**: gdy `provider.call_api()` zwróci `None`, sprawdza per-prompt `fallback_provider`+`fallback_model` (wyższy priorytet), potem per-dostawca `fallback_model`; fallback używa tego samego promptu, ale może użyć innego dostawcy i modelu; statystyki fallbacku zliczane osobno; **RateLimiter**: singleton z kubełkiem per dostawca; każdy kubełek = równomierne tempo (odstęp `60/rpm` między startami żądań, anti-burst dla darmowych tierów typu Mistral 0.83 req/s) + semafor jednoczesności (`max_concurrent`); flaga `free_only` (tylko OpenRouter) zawęża limit do modeli `:free`, inaczej dotyczy wszystkich żądań dostawcy; `configure(provider, rpm, max_concurrent, free_only)` z `_configure_rate_limit()` (back-compat: stare `free_model_rate_limit`/`free_model_max_concurrent` dla OpenRoutera); context manager `slot(provider, model)` owija oba `call_api` (główne + fallback), no-op gdy brak limitu; TPM (tokeny/min) nie egzekwowane — łapie je backoff 429 |
| `ai_generator/editor_ui.py` | UI edytora — przycisk per workflow z `editor_button` (przed przyciskiem AI), główny przycisk AI (wszystkie puste), async (`run_in_background` + `saveNow`), ochrona `_GENERATING`; rejestruje `gui_hooks.editor_will_show_context_menu` → PPM na polu: „Wygeneruj/Regeneruj `pole` przez AI" (tylko pola z promptem, `overwrite=True`) |
| `ai_generator/workflow.py` | Workflowy — `get_workflows()`/`get_context_menu()`/`migrate_workflows()`; `execute_step(note, step, ai_generator=None) -> (modified, error)` obsługuje moduły ai/dictionary/tts/field_splitter (bg, bez zapisu do kolekcji; zapis robi caller na main thread); `ai_generator` opcjonalny — batch równoległy podaje per-notatka `FieldGenerator`, workflow edytora per-przebieg (provider trzyma stan per-żądanie, `None` = świeża instancja dla kroku); `_resolve_ai_fields(step, cfg)` mapuje `fields` (empty/manual/lista) na `only_fields`; `run_workflow_editor(editor, workflow)` — sekwencyjne kroki, guard `_RUNNING`; stałe `DEFAULT_CONTEXT_MENU` + `_DEFAULT_PIPELINES` (re-seed przy migracji) |
| `ai_generator/browser_ui.py` | UI przeglądarki — `add_to_context_menu` iteruje `get_workflows()` (każdy = jedna pozycja), potem submenu `Generuj pola ▸`/`Generuj zablokowane ▸` gated przez `context_menu` (`ai_fields`/`ai_blocked`); `_all_configured_target_fields(config, manual_only=False)` rozdziela listy pól; batch AI równoległy (per-job `FieldGenerator`, paczki batch_limit+sleep, `overwrite=False`) przez `_run_batch`; batch workflow `_on_workflow_browser(browser, workflow)` **równoległy** (`ThreadPoolExecutor(parallel_requests)`, paczki batch_limit+sleep, per-notatka `FieldGenerator` podawany do `execute_step`; notatki preloadowane na main thread, kroki per-notatka sekwencyjne); zapis zmienionych notatek jednym `CollectionOp` (`update_notes`); submenu **Batch API (Anthropic/OpenAI, tańszy)** — `_on_batch_submit(only_fields=...)` (build_items + dialog `askUser` + submit w tle) dla pól auto (`target_fields`) oraz — gdy istnieją — pól `manual_only` (`manual_fields`: „…wszystkie zablokowane" + per-pole „Batch (zablokowane): `<pole>`"; jawny `only_fields` omija guard `manual_only` w `iter_note_fields`) i `check_pending_batches(silent)` (poll w tle → `apply_results` na main thread → `CollectionOp` → `mark_applied` **dopiero po commicie** → `cleanup_openai_files` w tle → `_advance_jobs`; wynik logowany INFO obok tooltipa); `_advance_jobs(config)` buduje itemy notatka-po-notatce i **przerywa na `openai_budget_left()`** (kolejka pełna / backoff → wychodzi od razu), odfiltrowuje `inflight_fields()` (dedup też między zadaniami), nadaje unikalne `custom_id` i dosyła następny plaster (guard `_advance_running` przeciw równoległym przebiegom; błędy z `submit` logowane i w tooltipie, sukces z postępem z `record_job_progress`); zadanie kończone gdy `build_items` puste albo `job_expired`. `check_pending_batches(silent=True)` wołane z `profile_did_open`, **cyklicznie co minutę** (QTimer w `__init__.py`, referencja na `mw`) i z sekcji „Batch API — postęp" na zakładce Start ustawień; `_on_batch_submit` po udanej wysyłce woła `add_job(nids, only_fields, total, sent)` |
| `dictionary/service.py` | Logika biznesowa słownika — `process_note_group()`; używa `clean_html_normalized()` z common |
| `dictionary/editor_ui.py` | UI edytora — przyciski słownikowe; `saveNow(start)` + `run_in_background` + guard `_FETCHING`; odtwarza audio po pobraniu; rejestruje `gui_hooks.editor_will_show_context_menu` → PPM na `source_field` lub `target_field` (np. `ang`/`audio`): „Pobierz wymowę: [słownik]" per włączony przycisk |
| `dictionary/browser_ui.py` | UI przeglądarki — submenu batch |
| `dictionary/dictionary_service.py` | Scrapery HTML dla 4 słowników; używa `fetch_url`, `fetch_text` z common |
| `dictionary/ipa_service.py` | Scrapery IPA + parser Wiktionary API; używa `fetch_text` z common |
| `tts/config.py` | Konfiguracja TTS — `_DEFAULTS`, `get_tts_config()`, `validate_config()`, `get_tasks()`, `resolve_openrouter_key()` |
| `tts/api.py` | API TTS — `generate_audio()`, `_generate_kokoro()`, `_generate_openrouter()`, `fetch_openrouter_tts_models()` |
| `tts/processor.py` | Przetwarzanie notatek; tryby zadań: `single` / `split` (audio obok słowa, w to samo pole) / `split_audio` (same tagi `[sound:...]` sklejone do osobnego pola docelowego, bez słów; `split_contexts` to krotka 4-elem. z `mode`) — wspólne `build_note_work_items()`, `generate_for_items()` (pula wątków, anulowanie z `cancel_futures`, używa nazwy zwracanej przez `write_data`), `apply_results_to_note()`; batch `process_task_async()`/`process_tasks_async(browser, nids, tasks)` (zapis jednym `CollectionOp`); `process_single_note(note, config, tasks=None, overwrite=False) -> (changed, error)` — `overwrite=True` stripuje `[sound:...]` z target fields przed generowaniem; bez zapisu do kolekcji, używane przez workflow i PPM w edytorze |
| `tts/editor_ui.py` | Przycisk TTS w edytorze — `saveNow(start)`, `_GENERATING`, `validate_config()`; używa wspólnych funkcji procesora; rejestruje `gui_hooks.editor_will_show_context_menu` → PPM na `target_field` zadania TTS: „Generuj/Regeneruj TTS: [label]" (Regeneruj = `overwrite=True`, strip sound tags) |
| `audio_normalizer/logic.py` | ffmpeg wrapper + historia przetworzonych plików |
| `nbsp_remover/cleaning.py` | Czysta funkcja `clean_field()` + regexy do czyszczenia HTML |
| `nbsp_remover/collection.py` | Masowe czyszczenie kolekcji przez `CollectionOp` + `clean_field()` |
| `tests/test_pure_logic.py` | Testy bez Anki: template engine, common HTML, `nbsp_remover.cleaning.clean_field()` |

---

## Jak dodać nowy moduł

1. Utwórz katalog `nazwa_modulu/` z `__init__.py` zawierającym `setup_menu(parent_menu=None)`
2. W `__init__.py` (root) dodaj blok:
   ```python
   if _enabled("nazwa_modulu"):
       from . import nazwa_modulu
       _menu_modules.append(nazwa_modulu)
   ```
3. Dodaj `"nazwa_modulu": true` do sekcji `modules` w `config.json`
4. Opcjonalnie dodaj zakładkę w `settings/__init__.py` i sekcję konfiguracyjną w `config.json`

## Jak dodać nowego providera AI

1. API zgodne z OpenAI Chat Completions: dodaj cienką podklasę `OpenAICompatProvider` w `ai_generator/providers/__init__.py` (ustaw `API_URL`, `LABEL`, opcjonalnie `SUPPORTS_REASONING_EFFORT`). Inny format: utwórz `ai_generator/providers/moj_provider.py` dziedzicząc po `BaseProvider` i zaimplementuj `call_api()` (możesz użyć `_parse_chat_completion()` / `_parse_messages()` z bazy)
2. Zarejestruj klasę w `ai_generator/providers/__init__.py` w słowniku `PROVIDERS`
3. Dodaj etykietę do `PROVIDER_LABELS` tamże (UI ustawień buduje listy dostawców z rejestru)
4. Dodaj sekcję `providers.moj_provider` w `config.json`

---

## Zależności między plikami

```
common/                         ← współdzielone narzędzia (html, http, text, config, ui)
    ├── consts.py               ← ADDON_NAME — używane przez WSZYSTKIE moduły
    ├── html.py                 ← clean_html / clean_html_normalized — używane przez dictionary, ai_generator, tts
    ├── text.py                 ← unique / safe_str / unique_filename / normalize_float — używane przez tts, ai_generator
    ├── http.py                 ← RETRYABLE_STATUS_CODES, fetch_url, fetch_text, post_json (POST/PATCH z retry), extract_http_error — używane przez providers, dictionary, tts, word_queue
    ├── config.py               ← get_full_config, get_module_config — używane przez tts/config.py, nbsp_remover/utils.py
    ├── progress.py             ← start_progress / update_progress / finish_progress (natywny mw.progress) — używane przez dictionary, tts, ai_generator, audio_normalizer batche
    └── ui.py                   ← widgety Qt, palette, hint_label, _expanding_line_edit, _api_key_widget, _scrollable — używane przez settings

dictionary/__init__.py          ← re-eksport: on_editor_buttons_init, add_to_context_menu (używa common/ui dla widgetów, common/consts dla ADDON_NAME)
    └── service.py              ← czysta logika biznesowa (ProcessNoteResult, process_note_group); używa common/clean_html_normalized
    └── editor_ui.py            ← przyciski edytora (saveNow + run_in_background + _FETCHING); PPM na source_field lub target_field → _on_fetch_audio_editor; używa common/ADDON_NAME
    └── browser_ui.py           ← add_to_context_menu (submenu przeglądarki + batch); używa common/ADDON_NAME
    └── dictionary_service.py   (DictionaryService singleton); używa common/http fetch_url, fetch_text
    └── ipa_service.py          (IPAService singleton); używa common/http fetch_text

ai_generator/__init__.py        ← re-eksport: on_editor_buttons_init, add_to_context_menu
    └── _generator.py           ← zarządzanie stanem generatora (config-aware cache, reset); używa common/ADDON_NAME
    └── editor_ui.py            ← przyciski workflowów (editor_button) przed AI; saveNow(start) przed zadaniem, _GENERATING guard; PPM na polu → _on_generate_field_editor (only_fields, overwrite=True)
    └── browser_ui.py           ← add_to_context_menu (workflowy z get_workflows; submenu "Generuj pola ▸"/"Generuj zablokowane ▸" gated przez context_menu; batch AI równoległy + batch workflow _on_workflow_browser (też równoległy, per-dostawca RateLimiter); zapis przez CollectionOp)
    └── field_generator.py      (FieldGenerator — logika bez UI); process_note(note, only_fields=None, overwrite=False); pola manual_only pomijane gdy only_fields=None; używa common/clean_html_normalized, safe_str
        └── template_engine.py  (render_template, template_structure_problems — czyste funkcje)
        └── stats.py            (record_request / record_note — statystyki użycia, bez zależności od Anki)
        └── providers/          (BaseProvider/OpenAICompatProvider + 7 implementacji + model_discovery); używa common/http.post_json (retry w jednym miejscu)
    └── workflow.py             (workflowy: get_workflows/migrate_workflows/execute_step AI/Dict/TTS/Rozdziel, _RUNNING guard); używa common/ADDON_NAME

tts/__init__.py                 ← add_to_context_menu + exports on_editor_buttons_init
    └── config.py               (_DEFAULTS, get_tts_config, validate_config, get_tasks); używa common/config get_module_config
    └── api.py                  (generate_audio dispatcher, fetch_openrouter_tts_models); używa common/http.post_json, common/normalize_float; urllib.request tylko do GET w fetch_openrouter_tts_models
    └── processor.py            (build_note_work_items, generate_for_items, apply_results_to_note, process_task_async, process_tasks_async, process_single_note(note, config, tasks=None, overwrite=False); używa common/unique_filename, clean_html, split_separator_regex
    └── editor_ui.py            (przycisk TTS w edytorze; saveNow + _GENERATING + validate_config; PPM na target_field → _on_tts_field_editor (overwrite=True dla Regeneruj)); używa processor.process_single_note

audio_normalizer/__init__.py
    ├── gui.py                  (run_normalization → mw.taskman.run_in_background + natywny pasek common/progress; _sync_media_files); używa common/ADDON_NAME
    │   └── logic.py            (process_collection — po anulowaniu dozbiera wyniki dokończonych ffmpeg-ów, normalize_file)
    │       └── config.py       (wartości domyślne: FFMPEG_CMD, LOUDNORM_OPTS, MAX_WORKERS)
    └── watcher.py              (auto-normalizacja: QFileSystemWatcher + debounce 3 s + guard _normalizing; profile_did_open)

settings/__init__.py            (SettingsDialog, open_settings); używa common/ADDON_NAME, get_full_config, save_full_config
    ├── status_tab.py           (StatusTab — dashboard pipeline'u, refresh(cfg) wołane przy przejściu na Start)
    ├── modules_tab.py          (ModulesTab)
    ├── dictionary_tab.py       (DictionaryTab); używa common/ui widgetów
    ├── ai_generator_tab.py     (AIGeneratorTab); używa common/ui widgetów, ai_generator/providers PROVIDERS+PROVIDER_LABELS
    ├── prompts_tab.py          (PromptsTab); używa common/ui widgetów + get_note_type_names, get_fields_for_note_type, get_sample_notes, palette; template_engine render_template/IF_PATTERN
    ├── prompt_wizard.py        (NewPromptDialog); używa prompt_templates + common/ui
    ├── prompt_templates.py     (TEMPLATES, build_prompt, guess_field — bez zależności od Anki)
    ├── tts_tab.py              (TTSTab); używa common/ui widgetów, tts/api fetch_openrouter_tts_models
    ├── audio_normalizer_tab.py (AudioNormalizerTab); używa common/ui widgetów
    ├── narzedzia_tab.py        (NarzedziaTab); używa common/ui widgetów
    ├── workflows_tab.py        (WorkflowsTab + WorkflowEditDialog); używa common/ui widgetów, ai_generator/workflow DEFAULT_CONTEXT_MENU
    ├── deck_router_tab.py      (DeckRouterTab — tabela reguł + _collect_rules + przycisk „Uporządkuj istniejące karty…" → deck_router.confirm_reorganize); używa common/ui hint_label
    ├── field_hider_tab.py      (FieldHiderTab — combo typu notatki + checkboxy pól; _store_current() zapisuje stan przed przełączeniem typu); używa common/ui hint_label, get_note_type_names, get_fields_for_note_type
    ├── logs_tab.py             (LogsTab); używa common/debug_log
    └── stats_tab.py            (StatsTab); używa ai_generator/stats get_stats, reset_stats

nbsp_remover/
    ├── cleaning.py             (clean_field + regexy; testowalne bez Anki)
    ├── addcards.py             (hook dodawania kart; używa clean_field)
    ├── collection.py           (masowe czyszczenie przez CollectionOp + clean_field; jeden krok undo)
    └── utils.py                (config + tooltipy)

field_splitter/
    ├── splitting.py            (split_field_value + parse_target_fields; testowalne bez Anki)
    └── __init__.py             (add_to_context_menu + setup_menu + _run_batch CollectionOp)

sibling_manager/
    ├── logic.py                (process_note — reactive, reviewer hook; process_note_sync — batch, sync catch-up; _cleanup_tag; używa anki.cards CARD_TYPE_NEW/QUEUE_TYPE_SUSPENDED)
    └── __init__.py             (on_reviewer_did_answer_card hook + on_sync_did_finish hook + _run_sync_scan CollectionOp + setup_menu: unsuspend all + manual sync catch-up; używa common/config get_module_config)

deck_router/
    ├── logic.py                (match_deck(tags, template_name, rules) — pierwsza pasująca reguła wygrywa; bez importów Anki, testowalne)
    └── __init__.py             (on_add_note hook + route_after_edit CollectionOp + run_reorganize/confirm_reorganize/setup_menu retro; _apply przenosi col.set_deck do col.decks.id(create=True); używa common/config get_module_config)

field_hider/
    └── __init__.py             (indices_to_hide(field_names, targets) — czyste jądro, testowalne + self-check pod __main__; on_editor_load_note wstrzykuje CSS chowający pola przez editor.web.eval, guard editor.addMode = tylko okno „Dodaj"; on_editor_buttons_init dodaje przycisk 👁 togglujący hf-reveal; używa common/config get_module_config)
```

---

## Uwagi o Anki API

- `mw.col.get_note(nid)` — pobierz notatkę po ID
- `mw.col.update_note(note)` — zapisz zmiany (Anki 2.1.45+); używaj zamiast `note.flush()`; pomijaj dla nowych notatek (`note.id == 0`, okno AddCards)
- `mw.col.media.write_data(filename, bytes)` — zapisz plik do media
- `aqt.operations.CollectionOp` — operacja na kolekcji w tle z undo (używane przez nbsp_remover)
- `mw.progress.start/update/finish` — pasek postępu (blokuje UI)
- `mw.addonManager.getConfig(name)` — odczyt konfiguracji (merged z defaults)
- `mw.addonManager.writeConfig(name, dict)` — zapis do profilu Anki (nie do `config.json`)
- Wywołania Qt UI (`showWarning`, `tooltip`) z wątku tła zawsze przez `mw.taskman.run_on_main`
