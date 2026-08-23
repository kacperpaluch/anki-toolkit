# LLM Context — Anki Toolkit: Content

## Zakres

Jeden dodatek dla głównego przepływu tworzenia kart: generowanie AI, Batch API,
pobieranie wymowy ze słowników, TTS oraz rozdzielanie pola na kolejne pola.
Workflowy uruchamiają te kroki sekwencyjnie dla jednej notatki.

## Pliki i granice

| Obszar | Odpowiedzialność |
|---|---|
| `__init__.py` | ładowanie modułów Content, hooki edytora/profilu/menu Browsera |
| `content_settings.py` | dialog ustawień wyłącznie dla Content |
| `ai_generator/` | prompty, providerzy, workflowy i Batch API |
| `dictionary/` | pobieranie audio oraz IPA |
| `tts/` | generowanie audio przez Kokoro lub OpenRouter |
| `field_splitter/` | dzielenie pola źródłowego na pola docelowe |
| `common/` | współdzielone HTTP, konfiguracja, progress i operacje edytora |
| `settings/` | techniczne panele używane przez `content_settings.py` |

## Niezmienniki

- Kolekcja Anki i edytor pozostają na głównym wątku. HTTP, AI i TTS mogą działać
  w workerach; zapis wyniku wraca na główny wątek.
- Batch API zapisuje stan w `user_files/ai_batches.json`; wynik wpisuj tylko do
  pola, które nadal jest puste.
- Zapis konfiguracji musi zachować nieznane klucze i dane providerów.
- Nie importuj innych dodatków Toolkit. Audio Normalizer i Audio Embed reagują
  na pliki mediów niezależnie od Content.

## Interfejs

**Narzędzia → Anki Toolkit: Content → Ustawienia…** otwiera workflowy, AI,
TTS, słownik i Field Splitter. Browser ma jedno submenu Content; przyciski
edytora rejestrują AI, słownik i TTS.
