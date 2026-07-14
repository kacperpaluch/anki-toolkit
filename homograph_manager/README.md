# Homograph Manager

Rozdziela w nauce **osobne notatki z tym samym słowem** o różnych znaczeniach (homografy), np. cztery karty `assault`: *napaść*, *atak wojskowy*, *atak-krytyka*, *napadać*.

## Problem

Sibling Manager grupuje karty **jednej notatki** (ang-pol ↔ pol-ang). Wbudowany „bury siblings" Anki też. Żaden nie łączy **różnych notatek** o tym samym słowie — dlatego dwa znaczenia „assault" pojawiają się obok siebie i interferują.

## Zasada działania

Grupa = wszystkie notatki, których pole `ang` (po trim + lowercase) jest identyczne. W obrębie grupy w danym momencie **aktywne jest tylko jedno znaczenie** — NEW karty pozostałych są zawieszone.

1. Odpowiadasz na kartę jednego znaczenia → NEW karty **innych** znaczeń zostają zawieszone.
2. Gdy aktywne znaczenie dojrzeje (jakakolwiek jego karta ma interval ≥ próg) → uwalnia się **dokładnie jedno** następne znaczenie (nie wszystkie naraz — inaczej znów interferencja).
3. Uczysz się go → reszta dalej zawieszona → cykl się powtarza, aż wszystkie znaczenia przejdą.

Moduł dotyka **wyłącznie NEW kart innych notatek** z grupy — nigdy kart notatki, na którą właśnie odpowiedziałeś. Dzięki temu współistnieje z Sibling Managerem: ten drugi rozkłada dwie strony jednego znaczenia, ten rozkłada znaczenia.

## Uczenie na telefonie + synchronizacja

Reviewer hook odpala się tylko na desktopie. Po synchronizacji (`sync_did_finish`, 600 ms po syncu — po Sibling Managerze) batch scan **odtwarza niezmiennik** dla każdej grupy: aktywne zostaje jedno znaczenie (to w trakcie nauki, a jak żadne — o najniższym nid), reszta zawieszona.

**Ręczny catch-up:** Narzędzia → Anki Toolkit → „Homograph Manager: przeskanuj całą kolekcję...".

## Konfiguracja

W **Ustawienia → Reguły kart → Odblokowywanie** albo w `config.json`:

```json
"homograph_manager": {
    "interval": 30,
    "field": "ang",
    "tag": "tk-homograph-suspended",
    "ignore_tag": "tk-homograph-ignored",
    "show_tooltip": true
}
```

| Pole | Default | Opis |
|---|---|---|
| `interval` | `30` dni | Po ilu dniach interval znaczenie uznane za dojrzałe → uwolnienie następnego |
| `field` | `ang` | Pole, po którego wartości grupowane są homografy |
| `tag` | `tk-homograph-suspended` | Tag notatek z zawieszonymi homografami |
| `ignore_tag` | `tk-homograph-ignored` | Notatki z tym tagiem są pomijane |
| `show_tooltip` | `true` | Tooltip po batch scan po synchronizacji |

## Menu

- **Uwolnij karty zawieszone przez Homograph Manager...** — reset wszystkich zawieszeń (usuwa też tagi).
- **Homograph Manager: przeskanuj całą kolekcję...** — ręczny batch scan.

## Hooki

| Hook | Kiedy | Co robi |
|---|---|---|
| `reviewer_did_answer_card` | Po odpowiedzi (desktop) | `process_reactive` — zawieś/uwolnij homografy |
| `sync_did_finish` | Po synchronizacji | `_run_sync_scan` — batch odtworzenie niezmiennika |
