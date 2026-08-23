# LLM Context — Anki Toolkit: Field Hider

## Zakres

Samodzielny dodatek ukrywa wybrane pola wyłącznie w oknie **Dodaj**. Nie ukrywa
pól w Browserze ani podczas edycji istniejącej notatki i nie zmienia danych
notatki.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | hooki edytora, konfiguracja i pozycja menu Narzędzia |
| `settings.py` | dialog wyboru typu notatki oraz ukrywanych pól |
| `config.json` | bezpieczny szablon ustawień |

## Niezmienniki

- Hook `editor_did_load_note` działa wyłącznie przy `editor.addMode`.
- Przycisk 👁 jedynie przełącza klasę CSS w bieżącym edytorze; nie zapisuje
  konfiguracji i nie dotyka notatki.
- `indices_to_hide()` pozostaje czystą funkcją testowalną bez Anki.
- Zapis przez `save_config()` nie może usuwać nieznanych kluczy konfiguracji.
- Dodatek nie zależy od żadnego innego dodatku Anki Toolkit.

## Interfejs

**Narzędzia → Anki Toolkit: Field Hider…** otwiera ustawienia. Użytkownik
wybiera typ notatki i zaznacza pola checkboxami. Szczegóły użytkowe są w
`README.md`.
