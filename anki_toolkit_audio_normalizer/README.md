# Anki Toolkit: Audio Normalizer

Samodzielny dodatek wyrównujący głośność mediów Anki przez `ffmpeg` (EBU R128).

W **Narzędzia → Anki Toolkit: Audio Normalizer** skonfigurujesz ścieżkę `ffmpeg`,
filtr i auto-normalizację, a także uruchomisz ręczny skan. Dodatek zachowuje
historię plików w `user_files/`, więc nie normalizuje bez potrzeby tych samych
mediów drugi raz. Nie włączaj równocześnie starego modułu `audio_normalizer`.

Historia jest rozdzielona według katalogu mediów (`user_files/audio_normalizer_<id>.json`).
Stary wspólny plik historii pozostaje nietknięty, ale nie jest używany, ponieważ
nie określa kolekcji; pierwszy skan po aktualizacji może ponownie przetworzyć audio.
Przełączenie profilu odpina watcher i anuluje oczekujące podmiany plików.
Zmiany wykryte podczas normalizacji powodują dodatkowy skan po jej zakończeniu,
więc nowe nagrania nie wymagają kolejnego ręcznego uruchomienia.
