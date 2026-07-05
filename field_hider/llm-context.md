# LLM Context — Field Hider

Moduł chowający wybrane pola w edytorze Anki **tylko w oknie „Dodaj”** (tryb `ADD_CARDS`).

## Rola

Wstrzykuje CSS ukrywający wskazane pola per typ notatki, wyłącznie gdy `editor.addMode` jest prawdziwe. W przeglądarce i przy edycji istniejącej karty hook kończy się od razu — pola zostają widoczne. Ukrycie jest czysto wizualne (nic nie jest kasowane w notatce). Pochodzi z osobnej minimalnej wtyczki `anki-hide`; różnica wobec oryginału: guard na `addMode` (oryginał chował wszędzie).

## Pliki

```
field_hider/
├── __init__.py    # całość: config, indices_to_hide(), hooki edytora, przycisk 👁
├── README.md      # dokumentacja użytkowa
└── llm-context.md # ten plik
```

Zakładka UI: `settings/field_hider_tab.py` (`FieldHiderTab`). Brak osobnego pliku `logic.py` — czyste jądro `indices_to_hide()` jest w `__init__.py` (moduł jest mały). Self-check pod `if __name__ == "__main__"`.

## Stack

Python 3.9+. Brak zewnętrznych zależności. Używa `gui_hooks.editor_did_load_note`, `gui_hooks.editor_did_init_buttons`, `editor.addMode`, `editor.note`, `note.note_type()`, `editor.web.eval(...)`, `editor.addButton(...)`.

## Model danych

Config: `config.json` → `"field_hider": {"hidden_fields": {typ_notatki: [nazwy_pól]}}`. Toggle: `modules.field_hider`.

```json
"field_hider": {
    "hidden_fields": {
        "angielski": ["p1", "p2", "p3", "p1-nauka", "p2-nauka", "p3-nauka"]
    }
}
```

`_DEFAULTS = {"hidden_fields": {}}`. Odczyt przez `get_module_config("field_hider", _DEFAULTS)` (import owinięty w `try/except ImportError`, żeby self-check dało się uruchomić samodzielnie).

## Logika

### `indices_to_hide(field_names, targets) -> list[int]` (czysta)

- Zwraca 0-based indeksy pól, których nazwa jest w `targets`, w kolejności pól typu notatki.
- `targets` normalizowane do `set` (akceptuje listę/set/None).
- Indeks pola = jego `data-index` w DOM edytora, więc mapuje bezpośrednio na selektor CSS.

### `on_editor_load_note(editor)` — hook `editor_did_load_note`

1. `if not getattr(editor, "addMode", False): return` — **jedyny mechanizm ograniczający chowanie do okna „Dodaj”**. `addMode` to bool ustawiany w `Editor.__init__` (`editorMode is EditorMode.ADD_CARDS`); w przeglądarce/edycji = `False`.
2. `nt = editor.note.note_type()`; `idx = indices_to_hide([f["name"] for f in nt["flds"]], targets)` gdzie `targets = hidden_fields.get(nt["name"], [])`.
3. Buduje selektor `body:not(.hf-reveal) .field-container[data-index="{i}"]` dla każdego `i` → `{ display: none !important; }`. Pusty `idx` → pusty CSS (czyści ewentualny poprzedni styl przy przeładowaniu notatki innego typu).
4. Wstrzykuje/aktualizuje `<style id="hf-style">` w `<head>` przez `editor.web.eval` (idempotentne — element tworzony raz, potem tylko `textContent`). CSS przekazany przez `json.dumps` (escaping).

### `on_editor_buttons_init(buttons, editor)` — hook `editor_did_init_buttons`

- `if not getattr(editor, "addMode", False): return buttons` — przycisk 👁 dodawany **tylko** w oknie „Dodaj” (w przeglądarce nic by nie chował, więc zbędny).
- `editor.addButton(icon=None, cmd="hf_toggle", func=_on_toggle, label="👁", tip=...)`.

### `_on_toggle(editor)`

- `editor.web.eval("document.body.classList.toggle('hf-reveal');")` — dodanie klasy `hf-reveal` na `<body>` wyłącza selektor `body:not(.hf-reveal) ...`, więc pola się pokazują. Ponowne kliknięcie chowa. Stan tylko w DOM, nie w configu.

## Rejestracja w root `__init__.py`

```python
if _enabled("field_hider"):
    from . import field_hider
    gui_hooks.editor_did_load_note.append(field_hider.on_editor_load_note)
    gui_hooks.editor_did_init_buttons.append(field_hider.on_editor_buttons_init)
```

Brak `setup_menu` — moduł nie dokłada nic do menu Narzędzia (nie trafia do `_menu_modules`).

## UI — `FieldHiderTab` (`settings/field_hider_tab.py`)

- `QComboBox` typów notatek (`get_note_type_names()`), pod nim przewijalna lista `QCheckBox` pól (`get_fields_for_note_type()`), zaznaczone = ukryte.
- Stan roboczy `self._hidden: {typ: [pola]}` inicjowany z configu; `_store_current()` zapisuje checkboxy aktywnego typu do mapy **przed** przełączeniem (przy `currentTextChanged` i w `apply`), więc edycja wielu typów w jednej sesji nie gubi danych.
- `apply(cfg)` → `cfg["field_hider"]["hidden_fields"] = dict(self._hidden)`; typy z pustą listą są przy zapisie usuwane z mapy (`_store_current` robi `pop`).
- Zarejestrowana w `settings/__init__.py` (grupa „System", ikona 🙈, tytuł „Ukrywanie pól").

## Zależności

- `common.get_module_config`, `common.ui.{hint_label, get_note_type_names, get_fields_for_note_type}`.
- Brak zależności od innych modułów wtyczki.

## Anki API używane

- `gui_hooks.editor_did_load_note`, `gui_hooks.editor_did_init_buttons`
- `editor.addMode`, `editor.note`, `note.note_type()["flds"]`/`["name"]`, `editor.web.eval(js)`, `editor.addButton(...)`
- `mw.col.models.all()` / `by_name()` (pośrednio przez helpery `common.ui`)
