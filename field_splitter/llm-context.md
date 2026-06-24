# LLM Context — field_splitter

## Co robi

Rozdziela zawartość pola źródłowego (np. `przyklad`) po separatorze (np. `<br><br>`) i **kopiuje** części do kolejnych pól docelowych (`p1`, `p2`, `p3`…). Pole źródłowe nie jest modyfikowane — to kopia, nie przeniesienie. Działa na dwa sposoby:
1. **Batch w przeglądarce** — PPM → Anki Toolkit → „Rozdziel pole ..." na zaznaczonych notatkach
2. **Cała kolekcja** — Narzędzia → Anki Toolkit → „Rozdziel pola w kolekcji..." (z potwierdzeniem)

Oba tryby zapisują zmiany jednym `CollectionOp` = jeden krok undo.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | `setup_menu(parent_menu=None)` (Tools menu) + `add_to_context_menu(browser, menu)` (browser context menu) + `_process_note()` (rdzeń) + `_run_batch(nids, on_complete=None)` (`CollectionOp`, batch w tle, jeden undo; `on_complete` odpala się na każdym wyjściu — po `on_success` oraz na miękkich returnach „brak notatek"/„brak pól docelowych" — żeby łańcuch zewnętrzny szedł dalej; używane przez full pipeline w `ai_generator.browser_ui`) |
| `splitting.py` | Czysta logika: `split_field_value(value, separator, target_fields) -> dict` i `parse_target_fields(raw) -> list`; testowalne bez Anki; zawiera self-check w `__main__` |

## Przepływ danych

### Browser batch

```
PPM w przeglądarce → Anki Toolkit → Rozdziel pole przyklad → p1, p2, p3...
  → add_to_context_menu dodała akcję z aktualną etykietą (source + 3 cele)
  → _run_batch(browser.selected_notes())
      → _get_config() — czyta source_field, separator, target_fields, overwrite
      → CollectionOp (w tle, z undo):
          → dla każdej notatki (nid):
              → _process_note(note, cfg):
                  → split_field_value(note[source], separator, targets)
                      → regex.split po separatorze (whitespace-tolerant)
                      → mapowanie części → {p1: part1, p2: part2, ...}
                  → dla każdego (tf, part):
                      → jeśli tf nie istnieje w notatce: pomiń
                      → jeśli overwrite=False i tf ma treść: pomiń
                      → jeśli current != part: note[tf] = part, changed=True
              → zbieranie zmienionych notatek
          → col.update_notes(changed_notes)   ← jeden krok undo
      → tooltip z licznikiem (plural_pl)
```

### Cała kolekcja

```
Narzędzia → Anki Toolkit → Rozdziel pola w kolekcji...
  → _run_on_collection()
      → cfg = _get_config(); walidacja target_fields
      → nids = mw.col.find_notes("")
      → QMessageBox.question (potwierdzenie z licznikiem)
      → _run_batch(nids)   ← ten sam rdzeń co browser
```

## Konfiguracja (sekcja `field_splitter` w config.json)

```json
"field_splitter": {
    "source_field": "przyklad",
    "separator": "<br><br>",
    "target_fields": "p1, p2, p3, p4, p5",
    "overwrite": true
}
```

| Pole | Domyślnie | Opis |
|---|---|---|
| `source_field` | `"przyklad"` | Pole z danymi do rozdzielenia (nie jest modyfikowane) |
| `separator` | `"<br><br>"` | Separator części (whitespace-tolerant — spacja w separatorze dopasowuje dowolny ciąg whitespace w treści) |
| `target_fields` | `"p1, p2, p3, p4, p5"` | Pola docelowe oddzielone przecinkami; parser: `parse_target_fields()` |
| `overwrite` | `true` | `true` = nadpisuj zawsze; `false` = wypełniaj tylko puste pola docelowe |

Edytowalne przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia** (sekcja "Rozdzielanie pól"). Odczyt w module przez `get_module_config(_MODULE_KEY, _DEFAULTS)` z `common/config.py`.

## Czysta logika — `splitting.py`

`split_field_value(value, separator, target_fields) -> dict`:
1. Pusty value lub brak separatora/cele → `{}`
2. Buduje regex separatora (whitespace-tolerant — inline kopii logiki z `common/text.py::split_separator_regex`, żeby moduł był testowalny bez importów Anki)
3. `regex.split(value)` → części, `.strip()` + odfiltrowanie pustych
4. Mapowanie `i → target_fields[i]` z pominięciem pustych nazw i nadmiarowych części
5. Zwraca `{target_field: part}`

`parse_target_fields(raw) -> list`:
- Split po przecinkach, `.strip()`, odfiltrowanie pustych

Self-check w `if __name__ == "__main__"`: uruchamia `split_field_value` na realnym przykładzie z trzema nagraniami i asserts (3 części, pierwsze słowo każdej części, brak separatora w częściach, zachowanie `[sound:...]`).

## Zależności

- Stdlib: `re`
- Anki API: `aqt.operations.CollectionOp`, `col.update_notes`, `col.find_notes`, `col.get_note`, `browser.selected_notes()`
- Własne: `common.get_module_config`, `common.plural_pl`
- PyQt6: `QAction`, `QMessageBox` (tylko `__init__.py`)
- Brak pip packages
- Brak zależności od innych modułów toolkitu (dictionary, ai_generator, tts)
