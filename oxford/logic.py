"""Czysta logika Oxford (bez aqt/Anki) — wybór pól do uzupełnienia.

Eksport notatek Oxford5000 ma dokładnie ten sam schemat co talia docelowa
(typ `angielski`), więc mapowanie pól jest tożsamościowe — nie ma czego
konfigurować. Testy: `tests/test_oxford.py`.
"""


def fields_to_fill(entry: dict, existing: dict, match_field: str) -> dict:
    """Zwraca {pole: wartość} — tylko puste pola notatki, nigdy match_field.

    Klucze techniczne (`_level`) zaczynają się od podkreślenia i nigdy nie są
    nazwą pola notatki.
    """
    return {
        name: value for name, value in entry.items()
        if not name.startswith("_")
        and name != match_field
        and name in existing
        and not existing[name].strip()
        and value.strip()
    }


def truncate(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"
