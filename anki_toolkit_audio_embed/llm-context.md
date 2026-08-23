# LLM Context — Anki Toolkit: Audio Embed

## Zakres

Samodzielny dodatek zamienia `[sound:plik]` na element HTML5 `<audio>` tylko w
skonfigurowanych polach i typach notatek. Nie pobiera ani nie generuje dźwięku;
działa na mediach już zapisanych przez Anki, TTS, słownik albo użytkownika.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | hooki Anki, akcje menu, `CollectionOp`, konfiguracja |
| `logic.py` | czysta, idempotentna konwersja tekstu i pól notatki |
| `settings.py` | dialog konfiguracji dostępny z Narzędzia |
| `config.json` | bezpieczny szablon domyślnych ustawień |

## Niezmienniki

- Nie zmieniaj pola głównego audio, jeśli użytkownik nie umieści go jawnie na
  liście pól.
- Konwersja musi być idempotentna: ponowny skan nie może zmieniać istniejącego
  `<audio>`.
- Wszystkie odczyty i zapisy notatek są w funkcji `CollectionOp`; worker nie
  dotyka kolekcji bezpośrednio.
- Skan po synchronizacji uruchamia się z opóźnieniem, aby zakończyły się inne
  hooki synchronizacji.
- Konfigurację zmieniaj wyłącznie przez `get_config()` / `save_config()`;
  zapis ma zachować nieznane klucze konfiguracji profilu.

## Interfejs

- **Narzędzia → Anki Toolkit: Audio Embed**: ustawienia i skan kolekcji.
- PPM w Browserze: skan zaznaczonych notatek.
- `scan_on_sync` włącza automatyczny, cichy skan po synchronizacji.

Nie dodawaj zależności od innych dodatków Anki Toolkit. Opis użytkowy jest w
`README.md`.
