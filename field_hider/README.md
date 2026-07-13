# Field Hider

Chowa wybrane pola w edytorze **tylko w oknie „Dodaj”** — w przeglądarce i przy edycji istniejących kart pola pozostają widoczne.

## Po co to

Wiele typów notatek ma pola pomocnicze wypełniane później automatycznie (np. `p1`, `p2`, `p1-nauka` uzupełniane przez AI/TTS/rozdzielanie pól). Przy ręcznym dodawaniu karty tylko rozpraszają — wpisujesz jedno–dwa pola źródłowe, reszta jest pusta. Field Hider chowa je w oknie **Dodaj**, żeby edytor był czysty, ale nie rusza ich nigdzie indziej.

## Zasada działania

- Konfiguracja = mapa `{typ notatki: [nazwy pól do ukrycia]}`.
- Chowanie działa **wyłącznie w trybie `ADD_CARDS`** (okno „Dodaj”). Sprawdzane przez `editor.addMode` — w przeglądarce i przy edycji istniejącej karty hook kończy się od razu, pola zostają widoczne.
- Ukrycie jest czysto wizualne (wstrzyknięty CSS `display: none` na `.field-container` po indeksie pola) — **nic nie jest kasowane ani zmieniane w notatce**. Pole nadal istnieje i może zostać wypełnione później.
- Przycisk **👁** w pasku edytora (widoczny tylko w oknie „Dodaj”) tymczasowo pokazuje schowane pola bez zmiany konfiguracji — przydatne, gdy raz na jakiś czas chcesz wpisać coś ręcznie.

## Kiedy się odpala

| Wyzwalacz | Kiedy |
|---|---|
| **Okno „Dodaj”** | Hook `editor_did_load_note` — przy każdym załadowaniu notatki wstrzykuje CSS chowający pola z reguły dla danego typu notatki |
| **Przycisk 👁** | `editor_did_init_buttons` — dodawany tylko w oknie „Dodaj”; przełącza klasę `hf-reveal` na `<body>`, co odsłania/chowa pola |

## Konfiguracja

**Ustawienia → Konserwacja → Ukrywanie pól:**

1. Wybierz **typ notatki** z listy.
2. Zaznacz pola, które mają być **ukryte** w oknie „Dodaj”.
3. Powtórz dla innych typów notatek (stan zapamiętywany przy przełączaniu).

Pola są pobierane z kolekcji, więc nie wpiszesz literówki. Typ notatki bez zaznaczonych pól nie jest zapisywany.

Odpowiednik w `config.json`:

```json
"field_hider": {
    "hidden_fields": {
        "angielski": ["p1", "p2", "p3", "p1-nauka", "p2-nauka", "p3-nauka"],
        "Oxford": ["p1", "p2", "p3"]
    }
}
```

## Włączanie / wyłączanie

**Ustawienia → Moduły** (lub `config.json` → `modules.field_hider`). Zmiana wymaga restartu Anki.
