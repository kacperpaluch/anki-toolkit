# Plan podziału Anki Toolkit na niezależne dodatki

## Cel

Rozdzielić obecny scalony dodatek na niezależnie instalowalne dodatki Anki,
bez utraty konfiguracji ani danych użytkownika. W okresie przejściowym obecny
`anki-toolkit` pozostaje działającym pakietem referencyjnym; nie usuwamy z niego
funkcji, zanim ich zamiennik nie będzie gotowy do samodzielnego wydania.

## Docelowe dodatki

| Identyfikator źródłowy | Nazwa dla użytkownika | Obecny kod | Zależności funkcjonalne |
|---|---|---|---|
| `anki_toolkit_core` | Anki Toolkit Core | wybrane elementy `common/` | wymagany przez dodatki Toolkit |
| `anki_toolkit_content` | Anki Toolkit: Content | `ai_generator/`, `dictionary/`, `tts/`, `field_splitter/`, workflowy | Core |
| `anki_toolkit_learning` | Anki Toolkit: Learning | `filtered_deck/` | Core |
| `anki_toolkit_integrations` | Anki Toolkit: Integrations | `word_queue/`, `web_bridge/`, `supermemo/`, `oxford/` | Core |
| `anki_toolkit_audio_normalizer` | Anki Toolkit: Audio Normalizer | `audio_normalizer/` | Core |
| `anki_toolkit_audio_embed` | Anki Toolkit: Audio Embed | `audio_embed/` | Core |
| `anki_toolkit_html_cleanup` | Anki Toolkit: HTML Cleanup | `nbsp_remover/` | Core |
| `anki_toolkit_field_hider` | Anki Toolkit: Field Hider | `field_hider/` | Core |

`homograph_manager/` nie jest migrowany i zostanie usunięty dopiero w wydaniu
kończącym okres kompatybilności.

## Granice odpowiedzialności

- **Content** jest jednym dodatkiem, ponieważ workflowy wykonują kroki AI,
  słownika, TTS i rozdzielania pól w jednej, sekwencyjnej operacji.
- Każdy z czterech dodatków systemowych ma własne menu, hooki, ustawienia i
  konfigurację. Nie rejestruje globalnego submenu innego dodatku.
- Każdy dodatek ma prosty, natywny dialog konfiguracji dostępny z menu
  **Narzędzia**. `config.json` pozostaje wyłącznie szablonem i mechanizmem
  eksportu/importu, nie podstawowym interfejsem użytkownika.
- **Core** dostarcza wyłącznie stabilne usługi techniczne: nazwę dodatku,
  konfigurację, logowanie, HTTP, narzędzia tekstowe/HTML, progress oraz guard
  operacji edytora. Nie zawiera menu ani funkcji użytkowych.
- Dodatki nie importują kodu innych dodatków. Integracja między funkcjami może
  zachodzić wyłącznie przez publiczne API Core lub dane Anki.

## Konfiguracja i dane użytkownika

Każdy nowy dodatek jest właścicielem własnego `config.json` oraz konfiguracji
profilu Anki. Klucze po migracji nie są już zagnieżdżone pod nazwą modułu:

| Dodatek | Dotychczasowa sekcja | Nowy root konfiguracji | Dane trwałe |
|---|---|---|---|
| Content | `ai_generator`, `dictionary`, `tts`, `field_splitter`, `workflows`, `context_menu` | te same sekcje, bez `modules` | `ai_batches.json` → dane Content |
| Learning | `filtered_deck` | `deck_name` | brak |
| Integrations | `word_queue`, `web_bridge`, `supermemo`, `oxford` | te same cztery sekcje | bazy SM i Oxford pozostają przy Integrations |
| Audio Normalizer | `audio_normalizer` | zawartość sekcji | historia normalizacji → dane dodatku |
| Audio Embed | `audio_embed` | zawartość sekcji | brak |
| HTML Cleanup | `nbsp_remover` | zawartość sekcji | brak |
| Field Hider | `field_hider` | zawartość sekcji | brak |

Migrator uruchamia się tylko wtedy, gdy nowy dodatek nie ma jeszcze własnej
konfiguracji. Kopiuje dane (nie przenosi), zapisuje wersję migracji i nie
nadpisuje późniejszych zmian użytkownika. Stary dodatek zostaje wyłączony przed
włączeniem odpowiednika, aby nie zarejestrować tych samych hooków podwójnie.

## Kolejność wdrażania

1. Utworzyć Core oraz testowalny adapter konfiguracji/migracji.
2. Wydzielić: Field Hider, HTML Cleanup, Audio Embed i Audio Normalizer.
3. Wydzielić Learning (tylko Filtered Deck).
4. Wydzielić Integrations.
5. Wydzielić Content; dopiero wtedy wycofać scalony loader i Homograph Manager.

Każdy krok wydania wymaga: testów czystej logiki, `compileall`, `git diff --check`
oraz smoke testu hooków i menu w Anki.

## Układ źródeł w monorepo

Docelowo każdy dodatek znajduje się bezpośrednio w root repo jako
`<identyfikator>/`. Katalog
zawiera własne `__init__.py`, `manifest.json`, `config.json`, README, testy
pakietu i ewentualne `user_files/`. Wspólne źródła Core pozostają jednym
pakietem, wersjonowanym jawnie. Skrypt wydaniowy będzie tworzył archiwa z
pojedynczego katalogu dodatku, bez danych użytkownika.

Każdy dodatek zawiera `README.md` dla użytkownika oraz kompaktowy
`llm-context.md` dla pracy nad kodem: zakres odpowiedzialności, routing plików,
hooki, konfigurację i niezmienniki. Dokumentacja nie kopiuje pełnego
`config.json`; szczegóły konfiguracji opisuje README albo UI dodatku.

Każdy katalog dodatku zawiera też własny `.gitignore`, ignorujący co najmniej
`meta.json`, `user_files/`, logi i artefakty Pythona. `config.json` jest
wersjonowanym szablonem i nie może zawierać kluczy API ani konfiguracji profilu.
