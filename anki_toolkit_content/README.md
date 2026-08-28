# Anki Toolkit: Content

Główny dodatek do budowania treści kart: generowanie pól przez AI, pobieranie
wymowy i IPA ze słowników, tworzenie audio przez TTS oraz rozdzielanie pola
z przykładami na kolejne pola notatki. Workflowy uruchamiają te kroki
sekwencyjnie dla jednej notatki.

Ustawienia: **Narzędzia → Anki Toolkit: Content** (ten sam dialog otwiera
przycisk **Config** przy dodatku w **Narzędzia → Dodatki**).

## Moduły

| Moduł | Do czego służy |
|---|---|
| [AI Generator](ai_generator/README.md) | Wypełnianie pól przez modele językowe — wielu dostawców, prompty per pole, workflowy, Batch API i fallback modeli |
| [Dictionary](dictionary/README.md) | Audio MP3 z wymową oraz transkrypcje IPA z czterech słowników online |
| [TTS](tts/README.md) | Generowanie audio przez lokalne Kokoro albo OpenRouter |
| [Field Splitter](field_splitter/README.md) | Kopiowanie części pola źródłowego (po separatorze) do kolejnych pól docelowych |

Każdy moduł ma własny `README.md` z pełnym opisem użycia i konfiguracji;
AI Generator, Dictionary i TTS mają dodatkowo `llm-context.md` z granicami
technicznymi.

## Dostawcy AI bez klucza API

Oprócz dostawców na klucz (OpenAI, Anthropic, Google, OpenRouter, CometAPI,
Mistral, NVIDIA, OpenCode Go) są dwaj dostawcy lokalni: **Codex CLI** i
**Claude CLI**. Uruchamiają zainstalowany i zalogowany oficjalny klient
(`codex` albo `claude`), więc generowanie idzie na limity Twojej subskrypcji —
ChatGPT albo Claude — zamiast na płatne API. Dodatek nigdy nie widzi tokenu.
Szczegóły i wymagania: [AI Generator → Dostawcy
lokalni](ai_generator/README.md#dostawcy-lokalni--generowanie-bez-klucza-api).

## Konfiguracja i dane

`config.json` jest bezpiecznym szablonem domyślnym — rzeczywiste ustawienia
profilu trafiają do `meta.json` dodatku. Dane trwałe (stan Batch API) należą do
`user_files/`. Klucze API, `meta.json` i `user_files/` są ignorowane przez Git.

## Współpraca z pozostałymi dodatkami

Content nie importuje innych dodatków Toolkit. Audio Normalizer i Audio Embed
reagują na pliki mediów niezależnie — wystarczy, że są zainstalowane.
