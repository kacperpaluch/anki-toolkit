# Filtered Deck — talia filtrowana

Tworzy talię filtrowaną w Anki z konfigurowalnymi parametrami przez dialog.

## Jak używać

**Narzędzia → Anki Toolkit → Utwórz talię filtrowaną: ...**

Pojawia się dialog z ustawieniami. Po kliknięciu OK talia jest tworzona i automatycznie otwierana.

## Konfiguracja

**Narzędzia → Anki Toolkit → Ustawienia... → Narzędzia → Talia filtrowana**

| Pole | Domyślnie | Opis |
|---|---|---|
| `deck_name` | `Angielski - Powtórka z wyprzedzeniem` | Nazwa tworzonej talii filtrowanej |
| `search_deck` | `angielski` | Nazwa talii do wyszukiwania (`deck:` w query) |

```json
"filtered_deck": {
    "deck_name": "Angielski - Powtórka z wyprzedzeniem",
    "search_deck": "angielski"
}
```

## Parametry dialogu

| Parametr | Domyślnie | Opis |
|---|---|---|
| **Dni do przodu** | `9999` | Zakres `prop:due<=X` — uwzględnia karty z terminem do X dni w przód. `9999` = wszystkie zaległe i przyszłe |
| **Limit kart** | `99999` | Maksymalna liczba kart w talii |
| **Kolejność** | Losowo | Porządek kart w talii |

### Dostępne kolejności

| Nazwa | Wartość wewnętrzna |
|---|---|
| Najdawniej oglądane | 0 |
| Losowo | 1 |
| Rosnące interwały | 2 |
| Malejące interwały | 3 |
| Najwięcej pomyłek | 4 |
| Kolejność dodania | 5 |
| Termin powtórki | 6 |

## Zachowanie

- Jeśli talia o tej nazwie już istnieje, tworzona jest z numerem: `Angielski - Powtórka z wyprzedzeniem (1)`, `(2)` itd.
- `reschedule = false` — oceny w talii filtrowanej nie zmieniają planowania FSRS/SM-2
- Po stworzeniu talia jest automatycznie otwierana
