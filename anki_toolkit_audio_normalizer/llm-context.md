# LLM Context — Anki Toolkit: Audio Normalizer

## Zakres

Normalizuje pliki media Anki przez `ffmpeg`, ręcznie lub automatycznie po zmianie
katalogu mediów.

## Niezmienniki

- `logic.process_media_dir()` jest workerem: otrzymuje ścieżkę i nigdy nie
  dotyka `mw`, kolekcji ani Qt.
- Ścieżkę media i `media.write_data()` pobieraj/wykonuj na głównym wątku.
- Historia należy do `user_files/audio_normalizer_history.json` i nie może trafić
  do repozytorium.
- Watcher jest pojedynczy, ma debounce 3 s i ignoruje własne zapisy normalizera.
- Konfiguracja jest dostępna z menu Narzędzia; zapis zachowuje obce klucze.

## Pliki

`logic.py` — czysta praca plikowa; `__init__.py` — Anki/UI/watcher;
`settings.py` — konfiguracja. Opis użytkowy: `README.md`.
