# LLM Context — Anki Toolkit

Katalog główny repozytorium jest dodatkiem Anki (w `addons21` symlink
`anki-toolkit` → repo). Ma jedno `manifest.json`, jeden `config.json` (szablon
z sekcjami modułów), jedno menu **Narzędzia → Anki Toolkit** i jedno okno
ustawień. Konfiguracja profilu i dane runtime należą do `meta.json` oraz
`user_files/` i nie mogą trafić do Git.

## Układ

Anki ładuje tylko `__init__.py`; `tests/` i `workload_service/` nie są częścią
wczytywanego pakietu i nie mogą być z niego importowane.

| Ścieżka | Zakres | Sekcje configu |
|---|---|---|
| `__init__.py` | import modułów, hooki edytora/profilu, timer batchy, menu Narzędzia i PPM Browsera | — |
| `settings_dialog.py` | wspólne okno: pogrupowany pasek boczny nad panelami modułów (`PAGES`) | wszystkie |
| `common/` | konfiguracja, HTTP, HTML, logi, progress, operacje edytora, widżety ustawień | — |
| `settings/` | panele „Tworzenie kart”: workflowy, AI, TTS, słownik, rozdzielanie, diagnostyka | — |
| `ai_generator/` | prompty, dostawcy, workflowy, Batch API — `ai_generator/llm-context.md` | `ai_generator`, `workflows`, `context_menu`, `debug` |
| `dictionary/` | audio i IPA ze słowników — `dictionary/llm-context.md` | `dictionary` |
| `tts/` | TTS przez OpenRouter — `tts/llm-context.md` | `tts` |
| `field_splitter/` | kopiowanie części pola do pól docelowych | `field_splitter` |
| `integrations/` | kolejka n8n, panel słowników, AI: znaczenia, Web Bridge — `integrations/llm-context.md` | `word_queue`, `web_bridge` |
| `workload/` | plan nauki (tylko odczyt kolekcji) — `workload/llm-context.md` | `workload` |
| `audio_normalizer/` | ffmpeg loudnorm, ręcznie lub przez watcher | `audio_normalizer` |
| `html_cleanup/` | reguły „znajdź → zamień” przy dodawaniu i dla kolekcji | `html_cleanup` |
| `field_hider/` | ukrywanie pól tylko w oknie Dodaj | `field_hider` |

Przed zmianą czytaj `AGENTS.md`, a potem tylko kontekst właściwego modułu.

## Konfiguracja

- Moduły czytają swoją sekcję przez `common.get_module_config(klucz, domyślne)`
  (starszy kod AI Generatora i Słownika czyta pełny config przez `ADDON_NAME`).
  Zapis poza oknem ustawień idzie przez `update_module_config`, który scala
  zmiany i zachowuje nieznane klucze.
- Panel ustawień: `__init__(cfg)` czyta pełny config, `apply(cfg)` zapisuje
  tylko własne sekcje, opcjonalne `validate() -> str | None` blokuje zapis.
  Okno zapisuje całość jednym `writeConfig` i nakłada na strony wspólny
  nagłówek (ikona, tytuł, opis z `PAGES`).
- `_unify_forms()` w `settings_dialog.py` rozciąga pola `QFormLayout` i wyrównuje
  formularze do lewej — styl macOS domyślnie zostawia pola w minimalnym rozmiarze.
  Pola liczbowe z tekstem zamiast minimum („bez limitu”, „auto (z historii)”)
  ustawiaj przez `common.ui.set_special_value()`, bo macOS ich nie poszerza.
- `setConfigAction` musi zwracać `None` — `False` otwiera w Anki edytor JSON.
- `logic.py` i `snapshot.py` Workloadu nie mogą mieć importów względnych ani
  aqt: `workload_service/` ładuje je po ścieżce, a domyślne wartości bierze
  z sekcji `workload` w głównym `config.json`.

## Niezmienniki małych modułów

- Audio Normalizer: `logic.process_media_dir()` jest workerem — dostaje ścieżkę
  i nie dotyka `mw`, kolekcji ani Qt; ścieżka mediów i `media.write_data()`
  zostają na głównym wątku. Historia `user_files/audio_normalizer_<hash>.json`
  (mtime_ns + rozmiar, zapis atomowy). Jeden watcher z debounce 3 s, odpinany
  przy zamykaniu profilu; zdarzenia w trakcie pracy ustawiają ponowny skan.
  Worker sprawdza anulowanie i niezmienność pliku przed podmianą.
- HTML Cleanup: `cleaning.clean_field()` jest jedynym silnikiem reguł (Dodaj
  i skan kolekcji); liczniki są kluczowane indeksem reguły z tej samej listy.
  Reguły domyślne są tylko w szablonie `config.json` (`default_rules()` je czyta);
  `with_rules()` uzupełnia brakujący klucz i zachowuje pustą listę. `MAX_PASSES`/`MAX_FIELD_CHARS` ograniczają
  rozrost; `_clean_note` zbiera zmiany przed mutacją. Skan kolekcji przez
  `CollectionOp` (jeden krok undo). Regex jest walidowany tylko w `validate()` panelu.
- Field Hider: hook `editor_did_load_note` działa wyłącznie przy `editor.addMode`;
  przycisk 👁 tylko przełącza klasę CSS; `indices_to_hide()` jest czysta.

## Workload Service

`workload_service/` to osobny klient headless: przeczytaj jego `README.md` oraz
kontekst Workload. Własna replika, oficjalny sync, tylko limity nowych;
bez bezpośredniego dostępu do bazy serwera. Stan i token w `user_files/` —
Compose montuje `../user_files`, czyli ten sam katalog co dane dodatku; nie
nadawaj plikom usługi nazw używanych przez dodatek (`ai_batches.json`,
`audio_normalizer_*.json`) i odwrotnie.

Usługa: `WORKLOAD_CONFIG` w Compose nadpisuje plik; `dashboard.py` czyta historię
i uruchamia `worker.py run` jako osobny proces. Dostęp do kolekcji nadal tylko
w głównym wątku workera, chroniony flock. Panel nie udostępnia plików wolumenu.

`notifications.py` wysyła raport udanego run/restore i jeden alert na trwający identyczny błąd;
`notification_state.json` utrwala deduplikację. Pełny sync wstrzymuje harmonogram przez
`intervention.json`; ręczny `download` robi backup, sprawdza limity i zastępuje tylko replikę.
Błąd maila nie zmienia sukcesu sync. `mail.json` zawiera sekret SMTP i pozostaje
w `user_files/`; Compose montuje katalog hosta zamiast nazwanego wolumenu.
