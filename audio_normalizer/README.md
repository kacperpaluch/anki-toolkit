# Normalizacja audio (`audio_normalizer/`)

Wyrównuje głośność mediów Anki przez `ffmpeg` (EBU R128).

Ustawienia (ścieżka `ffmpeg`, filtr, auto-normalizacja) są w **Narzędzia →
Anki Toolkit → Ustawienia… → Normalizacja audio**, a ręczny skan całego katalogu mediów (po potwierdzeniu)
w **Narzędzia → Anki Toolkit → Normalizuj audio (ffmpeg)…**.

Z włączoną auto-normalizacją watcher obserwuje katalog mediów i ~3 s po zmianie
normalizuje nowe pliki (TTS, słowniki, synchronizacja, ręczne dodanie). Włączenie
lub wyłączenie tej opcji działa po restarcie Anki.

Historia plików jest w `user_files/audio_normalizer_<id>.json`, osobno dla
każdego katalogu mediów, więc te same nagrania nie są normalizowane drugi raz.
Przełączenie profilu odpina watcher i anuluje oczekujące podmiany plików,
także przerywając działający ffmpeg. Plik roboczy powstaje poza katalogiem
mediów (w folderze profilu), więc normalizacja nie nadpisze ani nie usunie
innego nagrania. Pojedynczy plik ma limit 10 minut.
Zmiany wykryte podczas normalizacji powodują dodatkowy skan po jej zakończeniu,
więc nowe nagrania nie wymagają kolejnego ręcznego uruchomienia.
