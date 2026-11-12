# LLM Context — Anki Toolkit

Katalog główny repozytorium jest dodatkiem Anki (w `addons21` symlink
`anki-toolkit` → repo). Ma jedno `manifest.json`, jeden `config.json` (szablon
z sekcjami modułów), jedno menu **Narzędzia → Anki Toolkit** i jedno okno
ustawień. Konfiguracja profilu i dane runtime należą do `meta.json` oraz
`user_files/` i nie mogą trafić do Git.

## Układ

Anki ładuje tylko `__init__.py`; `tests/` nie jest częścią wczytywanego
pakietu i nie może być z niego importowane.

| Ścieżka | Zakres | Sekcje configu |
|---|---|---|
| `__init__.py` | import modułów, hooki profilu, przycisk edytora „Toolkit ▾” (moduły wystawiają `editor_actions(editor) -> [(etykieta, callback[, zaznaczone])]`, trzeci element robi z pozycji przełącznik z ptaszkiem; menu budowane przy kliknięciu z bieżącej notatki) oraz przypięte przyciski: `editor.pinned` to lista etykiet akcji ustawiana w podmenu „Przypnij do paska”; przycisk szuka akcji po etykiecie wśród pasujących do notatki, a gdy jej nie ma, pokazuje tooltip; menu pomija tylko przyciski faktycznie zbudowane w tym edytorze (`editor._atk_pinned`), bo Anki buduje pasek raz; zmiana etykiety akcji albo nazwy sekwencji odpina ją, menu Narzędzia (porządki w „Operacje na kolekcji”) i PPM Browsera (wspólne zaznaczenie, widoczność sekcji) | — |
| `editor_shortcuts.py` | skróty klawiszowe edytora ustawiane przez użytkownika (okno z „Toolkit ▾ → Skróty klawiszowe…”): etykieta akcji → kombinacja; `accept()` odrzuca kombinacje bez Ctrl/Meta (`common.shortcut_typing_problem`), zajęte w oknie edytora i głównym (QAction, QShortcut, przyciski, standardowe klawisze edycji) oraz powtórzone; skrótów formatowania z JS edytora Qt nie widzi; rejestracja przez `editor_did_init_shortcuts` w root, więc zmiana działa po ponownym otwarciu okna | `editor` |
| `settings_dialog.py` | wspólne okno: pogrupowany pasek boczny nad panelami modułów (`PAGES`), otwiera się na ostatnio oglądanej stronie (w ramach sesji Anki, `_last_page`), wiązania między panelami (Konta i klucze → prompty, TTS) | wszystkie |
| `common/` | konfiguracja (`check_config()` przy otwarciu profilu i Ustawień porównuje typy z szablonem `config.json` i proponuje wartości domyślne), HTTP (wspólny domyślny User-Agent, bez przenoszenia sekretów przy przekierowaniu, `post_create` bez ponowień niepewnych), HTML, logi, progress (`load_notes()` czyta duże zaznaczenie Browsera z paskiem i Anuluj), raporty sesji (`reports.record_report(title, text, retry, failed)` — Diagnostyka, czyszczone przy zamknięciu profilu), operacje edytora i zapis batchy Browsera (`save_detached_notes`, opcjonalny callback raportu po zapisie), widżety ustawień | — |
| `settings/` | Konta i klucze (wszystkie klucze i połączenia: `ai_generator.providers`, klucz TTS, n8n/Cloudflare w `word_queue`), sekwencje (workflowy i widoczność PPM), prompty AI, TTS, słownik, rozdzielanie pól (`narzedzia_tab.py`), Diagnostyka (`logs_tab.py`: raporty sesji, logi, tryb debug) | `workflows`, `context_menu`, `debug` (pozostałe sekcje zapisują panele modułów) |
| `ai_generator/` | prompty, dostawcy, wykonywanie workflowów — `ai_generator/llm-context.md` | `ai_generator` (czyta też `workflows`, `context_menu`) |
| `dictionary/` | audio i IPA ze słowników — `dictionary/llm-context.md` | `dictionary` |
| `tts/` | TTS przez OpenRouter — `tts/llm-context.md` | `tts` |
| `field_splitter/` | kopiowanie części pola do pól docelowych | `field_splitter` |
| `integrations/` | kolejka n8n, panel słowników, Web Bridge, JS stron słowników (`page_js`) — `integrations/llm-context.md` | `word_queue`, `web_bridge` |
| `html_cleanup/` | reguły „znajdź → zamień” przy dodawaniu i dla kolekcji | `html_cleanup` |
| `field_hider/` | ukrywanie pól tylko w oknie Dodaj | `field_hider` |

Przed zmianą czytaj `AGENTS.md`, a potem tylko kontekst właściwego modułu.

## Konfiguracja

- Moduły czytają swoją sekcję przez `common.get_module_config(klucz, domyślne)`
  (starszy kod AI Generatora i Słownika czyta pełny config przez `ADDON_NAME`).
  Zapis poza oknem ustawień idzie przez `update_module_config`, który scala
  zmiany i zachowuje nieznane klucze.
- Dostawcy CLI współdzielą konfigurację z `ai_generator.providers`; effort
  ustawia się wyłącznie przy dostawcy.
- Panel ustawień: `__init__(cfg)` czyta pełny config, `apply(cfg)` zapisuje
  tylko własne sekcje (Konta i klucze zapisuje wyłącznie klucze/połączenia
  wewnątrz sekcji `ai_generator`, `tts`, `word_queue`; panele funkcji ich nie
  zapisują), opcjonalne `validate() -> str | None` blokuje zapis.
  Okno zapisuje całość jednym `writeConfig` i nakłada na strony wspólny
  nagłówek (ikona, tytuł, opis z `PAGES`).
- `SettingsDialog` łączy żywe ustawienia dostawców z Konta i klucze z edytorem promptów (domyślne modele) oraz klucz TTS z podglądem głosów.
- `_unify_forms()` w `settings_dialog.py` rozciąga pola `QFormLayout` i wyrównuje
  formularze do lewej — styl macOS domyślnie zostawia pola w minimalnym rozmiarze.
  Pola liczbowe z tekstem zamiast minimum („bez limitu”) ustawiaj przez `common.ui.set_special_value()`, bo macOS ich nie poszerza.
  Edytowalne listy dostają rząd przycisków z `common.ui.list_buttons()` (akcje
  po lewej, ▲▼ po prawej, dwuklik = Edytuj, Delete = Usuń) — nie składaj go ręcznie.
  Dialog edycji wpisu waliduje w `accept()` (zostaje otwarty), nie po `exec()` —
  inaczej wpisane dane przepadają; usunięcie promptu lub sekwencji pyta `askUser`.
- `setConfigAction` musi zwracać `None` — `False` otwiera w Anki edytor JSON.

- PPM Browsera ma jeden dispatcher w root: wczytuje zaznaczenie, przekazuje
  `notes=` modułom, respektuje widoczność i usuwa puste submenu. Reguły AI
  i regenerowania są w `ai_generator/llm-context.md`.
- `common.editor_operation.save_detached_notes(..., on_saved=None)` pozostaje
  wspólną ścieżką Browsera: kontrola profilu, świeży odczyt, odrzucenie konfliktów,
  jeden `CollectionOp`/undo. Callback raportu dostaje identyfikatory pominiętych
  notatek dopiero po udanym zapisie; pozostałe moduły zachowują tooltipy, a z `title=`
  także wpis w raportach sesji. `retry` ponawia tylko notatki z błędem i musi być
  idempotentny (ponowne uruchomienie wypełnia tylko to, czego brakuje); rodzica
  bierze przez `live_parent()`, bo Browser mógł zostać zamknięty.

## Niezmienniki małych modułów

- HTML Cleanup: `cleaning.clean_field()` jest jedynym silnikiem reguł (Dodaj
  i skan kolekcji); liczniki są kluczowane indeksem reguły z tej samej listy.
  Reguły domyślne są tylko w szablonie `config.json` (`default_rules()` je czyta);
  `with_rules()` uzupełnia brakujący klucz i zachowuje pustą listę. `MAX_PASSES`/`MAX_FIELD_CHARS` ograniczają
  rozrost; `_clean_note` zbiera zmiany przed mutacją, a `ValueError` limitu dotyczy całej notatki: Dodaj ją przepuszcza bez czyszczenia, skan kolekcji pomija. Skan kolekcji przez
  `CollectionOp` (jeden krok undo). Regex jest walidowany tylko w `validate()` panelu.
- Field Hider: hook `editor_did_load_note` działa wyłącznie przy `editor.addMode`;
  pozycja „Pokaż schowane pola” w menu „Toolkit ▾” tylko przełącza klasę CSS (stan ptaszka w `editor._atk_fh_reveal`); `indices_to_hide()` jest czysta.
