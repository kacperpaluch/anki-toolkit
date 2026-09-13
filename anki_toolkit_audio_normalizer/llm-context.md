# LLM Context — Anki Toolkit: Audio Normalizer

## Zakres

Normalizuje pliki media Anki przez `ffmpeg`, ręcznie lub automatycznie po zmianie
katalogu mediów.

## Niezmienniki

- `logic.process_media_dir()` jest workerem: otrzymuje ścieżkę i nigdy nie
  dotyka `mw`, kolekcji ani Qt.
- Ścieżkę media i `media.write_data()` pobieraj/wykonuj na głównym wątku.
- Historia w `user_files/audio_normalizer_<hash-katalogu>.json` używa mtime_ns
  i rozmiaru pliku; zapis jest atomowy. Stara historia bez właściciela nie jest importowana.
- Watcher jest pojedynczy, ma debounce 3 s i jest odpinany przy zamykaniu profilu.
  Zdarzenia podczas pracy ustawiają flagę ponownego skanu (także własne zapisy;
  historia zapobiega kolejnej konwersji). Callback sprawdza kolekcję i anulowanie.
- Worker sprawdza anulowanie oraz niezmienność pliku przed podmianą; zbiera
  wyniki już zakończonych zadań również po anulowaniu pozostałych.
- Konfiguracja jest dostępna z menu Narzędzia; zapis zachowuje obce klucze.

## Pliki

`logic.py` — czysta praca plikowa; `__init__.py` — Anki/UI/watcher;
`settings.py` — konfiguracja. Opis użytkowy: `README.md`.
