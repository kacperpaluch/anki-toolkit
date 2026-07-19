"""Czysta logika mapowania SuperMemo → talia docelowa (bez aqt/Anki).

Wydzielone tu, żeby dało się testować bez uruchamiania Anki (wzór jak
audio_embed/logic.py). Tylko stdlib.
"""


def clean_pos(value: str) -> str:
    """SuperMemo zapisuje część mowy jako "n)", "adj)" — obetnij nawias."""
    return value.strip().rstrip(")").strip()


def build_query(note_type: str, src_field: str, word: str) -> str:
    """Zapytanie Anki dopasowujące dokładnie pole SM. Escapuje cudzysłów/backslash,
    żeby słowo z apostrofem/spacją nie rozbiło składni ani nie wstrzyknęło filtra."""
    safe = word.replace("\\", "\\\\").replace('"', '\\"')
    return f'note:"{note_type}" "{src_field}:{safe}"'


def truncate(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def fields_to_fill(sm_fields: dict, existing: dict, field_map: dict,
                   match_field: str) -> dict:
    """Zwraca {pole_docelowe: wartość} do ustawienia.

    Wypełnia tylko puste pola docelowe (nie nadpisuje ręcznej/wygenerowanej
    treści) i pomija pole, po którym szukano słowa. `existing` to bieżące
    wartości pól notatki docelowej (brak klucza = pola nie ma w modelu).
    """
    out = {}
    for src_field, dst_field in field_map.items():
        if dst_field == match_field:
            continue
        if dst_field not in existing or existing[dst_field].strip():
            continue
        value = sm_fields.get(src_field, "")
        if src_field == "PartOfSpeech":
            value = clean_pos(value)
        if value.strip():
            out[dst_field] = value
    return out
