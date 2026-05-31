# LLM Context — filtered_deck

## Co robi

Tworzy talię filtrowaną w Anki z konfigurowalnymi parametrami przez dialog Qt. Dostępne przez **Narzędzia → Anki Toolkit → Stwórz talię ... (Wybierz opcje)...**. Nazwa talii i deck docelowy są konfigurowalne w ustawieniach wtyczki.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Cały moduł — dialog Qt, logika tworzenia talii, `setup_menu(parent_menu=None)`; używa `common.ADDON_NAME` |

## Przepływ danych

```
Narzędzia → Anki Toolkit → Stwórz talię ...
  → FilterSettingsDialog.exec()
      → użytkownik wybiera: dni, limit, kolejność
  → create_filtered_deck(days, limit, order)
      → _get_config() — czyta deck_name i search_deck z configu (używa ADDON_NAME)
      → col.decks.new_filtered(name)          # tworzy nową talię filtrowaną
      → konfiguruje search_query, limit, order, reschedule=False
      → col.sched.rebuild_filtered_deck(id)    # wypełnia kartami
      → mw.col.decks.select(id) + mw.reset()  # przełącza widok
      → tooltip z liczbą kart
```

## Konfiguracja (sekcja `filtered_deck` w config.json)

```json
"filtered_deck": {
    "deck_name": "Angielski - Powtórka z wyprzedzeniem",
    "search_deck": "angielski"
}
```

| Pole | Opis |
|---|---|
| `deck_name` | Nazwa tworzonej talii filtrowanej |
| `search_deck` | Nazwa talii do wyszukiwania (`deck:` w query) |

Edytowalne przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia** (sekcja "Talia filtrowana").

## Parametry dialogu

| Parametr | Domyślnie | Opis |
|---|---|---|
| Dni do przodu | 9999 | `prop:due<=X` — zakres terminów powtórek |
| Limit kart | 99999 | Max liczba kart w talii |
| Kolejność | Losowo (1) | Sort order Anki (0–6) |

Wartości sort order: 0=Oldest seen, 1=Random, 2=Increasing intervals, 3=Decreasing intervals, 4=Most lapses, 5=Order added, 6=Due date.

## Obsługa wersji Anki

Kod obsługuje dwa formaty deck config z bounds checking:
- **dict** (stary styl) — bezpośredni dostęp do `deck['terms'][0]` z walidacją długości
- **protobuf** (Anki 2.1.50+) — `deck.config.search_terms[0]` z walidacją niepustej listy; błędy `AttributeError` są raportowane użytkownikowi zamiast cicho ignorowane

## Zależności

- Anki API: `mw.col.decks`, `mw.col.sched.rebuild_filtered_deck`, `mw.addonManager.getConfig`
- Własne: `common.ADDON_NAME`
- PyQt6: `QDialog`, `QSpinBox`, `QComboBox`, `QDialogButtonBox`
- Brak pip packages
