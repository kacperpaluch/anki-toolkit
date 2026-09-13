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
| `settings/` | panele zakładek używane przez `content_settings.py` |

## Niezmienniki

- Kolekcja Anki i edytor pozostają na głównym wątku. HTTP, AI i TTS mogą działać
  w workerach; zapis wyniku wraca na główny wątek.
- Worker nie dotyka notatki otwartej w edytorze. Ścieżki edytorowe pracują na
  kopii (`common.editor_operation.detach_note`) i wracają przez `merge_note()`,
  które pomija wyniki bieżącego kroku, jeśli użytkownik zmienił jakiekolwiek pole
  (mogło być jego źródłem). `merge_editor_note()` sprawdza tożsamość kolekcji,
  wczytuje świeżą notatkę po przełączeniu edytora, zapisuje istniejącą notatkę
  z powiadomieniem `OpChanges` i odświeża webview po każdym kroku workflow.
- Operacja niszcząca dotychczasową treść (regeneracja audio) wykonuje się dopiero
  po tym, jak powstanie zastępnik. Brak wyniku = pole zostaje nietknięte.
- Batch API zapisuje stan w `user_files/ai_batches.json`; plik jest wspólny dla
  wszystkich profili, więc każdy rekord i job nosi `col` i jest widoczny tylko w
  swojej kolekcji. Wynik wpisuj tylko do pola, które nadal jest puste, a pola
  czekające w kolejce (`inflight_fields()`) nie mogą trafić do kolejnej wysyłki.
  Właściciel jest przechwytywany przed uruchomieniem workera. Rekordy bez `col`
  są zachowane do ręcznego przypisania; nigdy nie zakładaj, że należą do aktualnego
  profilu. `submit()` serializuje wysyłki i ponownie deduplikuje pola pod blokadą.
- Zapis konfiguracji musi zachować nieznane klucze i dane providerów.
- Nie importuj innych dodatków Toolkit. Audio Normalizer i Audio Embed reagują
  na pliki mediów niezależnie od Content.

## Interfejs

**Narzędzia → Anki Toolkit: Content…** otwiera od razu okno ustawień
(workflowy, AI, TTS, słownik, Field Splitter, Diagnostyka) — bez pośredniego
submenu. Zakładka Diagnostyka pokazuje bufor logów wtyczki (`common.debug_log`,
inicjowany w `__init__.py`) — tam trafia historia batchy i błędów.
Ten sam dialog podpięty jest pod przycisk Config w menedżerze dodatków
(`setConfigAction`). Browser ma jedno submenu Content; przyciski edytora
rejestrują AI, słownik i TTS.
