# LLM Context — filtered_deck

## Co robi

Tworzy talię filtrowaną w Anki z jednego z predefiniowanych presetów (dialog Qt z QComboBox). Dostępne przez **Narzędzia → Anki Toolkit → Utwórz talię filtrowaną (preset)...**. Presety obejmują całą kolekcję (brak filtra `deck:`) i nie zmieniają harmonogramu (`resched=False`).

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Cały moduł — stała `PRESETS`, dialog Qt, logika tworzenia talii, `setup_menu(parent_menu=None)`; używa `common.ADDON_NAME` |

## Presety (stała `PRESETS`)

Lista krotek `(etykieta, search, limit, order)` — wszystkie z `order=1` (losowo):

| Etykieta | Search | Limit |
|---|---|---|
| Uczone w ostatnich 7 dniach | `rated:7` | 99999 |
| Uczone w ostatnich 30 dniach | `rated:30` | 99999 |
| Wszystkie uczone karty (bez limitu) | `-is:new` | 999999 |
| Trudne karty (pomyłki z 30 dni) | `rated:30:1` | 99999 |
| Losowe karty (uczone lub nie) | `deck:*` | 100 |

## Przepływ danych

```
Narzędzia → Anki Toolkit → Utwórz talię filtrowaną (preset)...
  → FilterSettingsDialog.exec()
      → użytkownik wybiera preset w QComboBox
  → create_filtered_deck(preset_index)
      → label, search, limit, order = PRESETS[preset_index]
      → _get_config() — czyta deck_name (bazę nazwy) z configu (używa ADDON_NAME)
      → deck_name = f"{base} — {label}"
      → reużycie istniejącej talii dyn o tej nazwie LUB col.decks.new_filtered(name)
        (sufiks (1), (2)... tylko gdy nazwę zajmuje zwykła talia)
      → konfiguruje search, limit, order, reschedule=False, separate=True
      → col.sched.rebuild_filtered_deck(id)    # wypełnia kartami
      → mw.col.decks.select(id) + mw.reset()  # przełącza widok
      → tooltip z liczbą kart
```

## Konfiguracja (sekcja `filtered_deck` w config.json)

```json
"filtered_deck": {
    "deck_name": "Angielski - Powtórka z wyprzedzeniem"
}
```

| Pole | Opis |
|---|---|
| `deck_name` | Nazwa bazowa talii — preset dokleja `— {etykieta}` |

`search_deck` z wcześniejszych wersji jest ignorowany (presety obejmują całą kolekcję). Edytowalne przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia** (sekcja "Talia filtrowana").

## Obsługa wersji Anki

Kod obsługuje dwa formaty deck config z bounds checking:
- **dict** (stary styl) — bezpośredni dostęp do `deck['terms'][0]` z walidacją długości
- **protobuf** (Anki 2.1.50+) — `deck.config.search_terms[0]` z walidacją niepustej listy; błędy `AttributeError` są raportowane użytkownikowi zamiast cicho ignorowane

## Zależności

- Anki API: `mw.col.decks`, `mw.col.sched.rebuild_filtered_deck`, `mw.addonManager.getConfig`
- Własne: `common.ADDON_NAME`
- PyQt6: `QDialog`, `QVBoxLayout`, `QFormLayout`, `QLabel`, `QComboBox`, `QDialogButtonBox`
- Brak pip packages
