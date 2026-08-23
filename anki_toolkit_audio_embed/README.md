# Anki Toolkit: Audio Embed

Samodzielny dodatek, który zamienia `[sound:plik.mp3]` na odtwarzacz HTML5
`<audio>` w wybranych polach notatek. Działa niezależnie od źródła dźwięku.

## Użycie

- **Narzędzia → Anki Toolkit: Audio Embed**: ustawienia albo skan całej kolekcji.
- **Menu kontekstowe przeglądarki**: skan zaznaczonych notatek.
- Opcjonalnie automatycznie po synchronizacji.

Konfiguracja jest dostępna w interfejsie Anki; nie wymaga edycji JSON. Nie
włączaj jednocześnie starego modułu `audio_embed` w scalonym Anki Toolkit,
ponieważ oba dodatki rejestrują ten sam hook synchronizacji.
