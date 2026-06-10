# LLM Context — filtered_deck

## Co robi

Tworzy talię filtrowaną w Anki z konfigurowalnymi parametrami przez formularz Qt. Dostępne przez **Narzędzia → Anki Toolkit → Utwórz talię filtrowaną: {deck}...**. Nazwa talii i deck docelowy są konfigurowalne w ustawieniach wtyczki.

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | Cały moduł — dialog Qt, logika tworzenia talii, `setup_menu(parent_menu=None)`; używa `common.ADDON_NAME` |

## Przepływ danych

```
Narzędzia → Anki Toolkit → Utwórz talię filtrowaną: {deck}...
  → FilterSettingsDialog.exec()
      → użytkownik wybiera w QFormLayout: Dni do przodu, Limit kart, Kolejność
  → create_filtered_deck(days, limit, order)
      → _get_config() — czyta deck_name i search_deck z configu (używa ADDON_NAME)
      → col.decks.new_filtered(name)          # tworzy nową talię filtrowaną
      → search_query = f'prop:due<={days} deck:"{search_deck}"'
        # nazwa talii w cudzysłowach — nazwy ze spacjami nie psują zapytania
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
| `search_deck` | Nazwa talii do wyszukiwania (`deck:"..."` w query — nazwy ze spacjami są obsługiwane) |

Edytowalne przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia** (sekcja "Talia filtrowana").

## Parametry dialogu

| Parametr | Domyślnie | Opis |
|---|---|---|
| Dni do przodu | 9999 | `prop:due<=X` — zakres terminów powtórek |
| Limit kart | 99999 | Max liczba kart w talii |
| Kolejność | Losowo (1) | Sort order Anki (0–6) |

Wartości sort order: 0=Najdawniej oglądane, 1=Losowo, 2=Rosnące interwały, 3=Malejące interwały, 4=Najwięcej pomyłek, 5=Kolejność dodania, 6=Termin powtórki.

## Obsługa wersji Anki

Kod obsługuje dwa formaty deck config z bounds checking:
- **dict** (stary styl) — bezpośredni dostęp do `deck['terms'][0]` z walidacją długości
- **protobuf** (Anki 2.1.50+) — `deck.config.search_terms[0]` z walidacją niepustej listy; błędy `AttributeError` są raportowane użytkownikowi zamiast cicho ignorowane

## Zależności

- Anki API: `mw.col.decks`, `mw.col.sched.rebuild_filtered_deck`, `mw.addonManager.getConfig`
- Własne: `common.ADDON_NAME`
- PyQt6: `QDialog`, `QVBoxLayout`, `QFormLayout`, `QLabel`, `QSpinBox`, `QComboBox`, `QDialogButtonBox`
- Brak pip packages
