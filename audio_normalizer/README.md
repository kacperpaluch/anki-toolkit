# Audio Normalizer

Wyrównuje głośność mediów Anki przez `ffmpeg` (EBU R128).

Ustawienia (ścieżka `ffmpeg`, filtr, auto-normalizacja) są w **Narzędzia →
Anki Toolkit → Ustawienia… → Normalizacja audio**, a ręczny skan całej kolekcji
w **Narzędzia → Anki Toolkit → Normalizuj audio (ffmpeg)…**.

Historia plików jest w `user_files/audio_normalizer_<id>.json`, osobno dla
każdego katalogu mediów, więc te same nagrania nie są normalizowane drugi raz.
Przełączenie profilu odpina watcher i anuluje oczekujące podmiany plików.
Zmiany wykryte podczas normalizacji powodują dodatkowy skan po jej zakończeniu,
więc nowe nagrania nie wymagają kolejnego ręcznego uruchomienia.
