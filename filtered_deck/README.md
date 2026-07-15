# Filtered Deck — talia filtrowana

Tworzy talię filtrowaną w Anki z jednego z predefiniowanych presetów. Karty pobierane są z **dowolnego decka** (cała kolekcja), a oceny **nie zmieniają harmonogramu** powtórek.

## Jak używać

**Narzędzia → Anki Toolkit → Utwórz talię filtrowaną (preset)...**

Pojawia się dialog z listą presetów. Po wybraniu i kliknięciu OK talia jest tworzona i automatycznie otwierana.

## Presety

| Preset | Search Anki | Domyślny limit | Kolejność |
|---|---|---|---|
| Uczone w ostatnich 7 dniach | `rated:7` | 99999 | Losowo |
| Uczone w ostatnich 30 dniach | `rated:30` | 99999 | Losowo |
| Wszystkie uczone karty (bez limitu) | `-is:new` | Bez limitu | Losowo |
| Trudne karty (pomyłki z 30 dni) | `rated:30:1` | 99999 | Losowo |
| Losowe karty (uczone lub nie) | `deck:*` | 100 | Losowo |

Pole **Limit kart** podpowiada domyślny limit wybranego presetu, ale można go nadpisać. Ustawienie **0** (wyświetla się jako „Bez limitu") pobiera wszystkie pasujące karty.

Każdy preset tworzy osobną talię o nazwie `{deck_name} — {nazwa presetu}`.

## Konfiguracja

**Narzędzia → Anki Toolkit → Ustawienia... → Reguły kart → Presety powtórek**

| Pole | Domyślnie | Opis |
|---|---|---|
| `deck_name` | `Angielski - Powtórka z wyprzedzeniem` | Nazwa bazowa — preset dokleja do niej swoją etykietę |

```json
"filtered_deck": {
    "deck_name": "Angielski - Powtórka z wyprzedzeniem"
}
```

> `search_deck` z wcześniejszych wersji nie jest już używany — presety obejmują całą kolekcję.

## Zachowanie

- Jeśli talia filtrowana danego presetu już istnieje, jest **aktualizowana i przebudowywana** zamiast tworzenia kopii z sufiksem
- Jeśli nazwa jest zajęta przez zwykłą (nie-filtrowaną) talię, tworzona jest z numerem: `(1)`, `(2)` itd.
- `reschedule = false` — oceny w talii filtrowanej nie zmieniają planowania FSRS/SM-2
- Po stworzeniu talia jest automatycznie otwierana
