# Filtered Deck — talia filtrowana

Tworzy talię filtrowaną w Anki z konfigurowalnymi parametrami przez dialog.

## Jak używać

**Narzędzia → Anki Toolkit → Stwórz talię ... (Wybierz opcje)...**

Pojawia się dialog z ustawieniami. Po kliknięciu OK talia jest tworzona i automatycznie otwierana.

## Konfiguracja

**Narzędzia → Anki Toolkit → Ustawienia... → zakładka Talia filtrowana**

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
| **Ile dni do przodu** | `9999` | Zakres `prop:due<=X` — uwzględnia karty z terminem do X dni w przód. `9999` = wszystkie zaległe i przyszłe |
| **Limit kart** | `99999` | Maksymalna liczba kart w talii |
| **Kolejność** | Losowo | Porządek kart w talii |

### Dostępne kolejności

| Nazwa | Wartość wewnętrzna |
|---|---|
| Najdawniej oglądane (Oldest seen) | 0 |
| Losowo (Random) | 1 |
| Rosnące interwały (Increasing intervals) | 2 |
| Malejące interwały (Decreasing intervals) | 3 |
| Najwięcej pomyłek (Most lapses) | 4 |
| Kolejność dodania (Order added) | 5 |
| Termin powtórki (Due date) | 6 |

## Zachowanie

- Jeśli talia o tej nazwie już istnieje, tworzona jest z numerem: `Angielski - Powtórka z wyprzedzeniem (1)`, `(2)` itd.
- `reschedule = false` — oceny w talii filtrowanej nie zmieniają planowania FSRS/SM-2
- Po stworzeniu talia jest automatycznie otwierana
