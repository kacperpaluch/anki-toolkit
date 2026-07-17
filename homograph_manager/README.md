# Homograph Manager

Rozdziela w nauce **osobne notatki z tym samym słowem** o różnych znaczeniach (homografy), np. cztery karty `assault`: *napaść*, *atak wojskowy*, *atak-krytyka*, *napadać*.

## Problem

Wbudowany „bury siblings" Anki grupuje tylko karty **jednej notatki** (ang-pol ↔ pol-ang). Nic nie łączy **różnych notatek** o tym samym słowie — dlatego dwa znaczenia „assault" pojawiają się obok siebie i interferują.

## Zasada działania

Grupa = wszystkie notatki, których pole `ang` (po trim + lowercase) jest identyczne. Moduł bramkuje **wprowadzanie nowych znaczeń** — nie zawiesza znaczeń, których już się uczysz.

1. Znaczenie **już w nauce/review** (jakakolwiek jego karta nie jest NEW, a interval < próg) jest **zwolnione z bramkowania** — nigdy nie zawieszane. Jeśli uczysz się kilku znaczeń naraz (np. dodanych zanim moduł istniał), wszystkie zostają aktywne.
2. Odpowiadasz na kartę jednego znaczenia → NEW karty **całkowicie nowych** (jeszcze nierozpoczętych) znaczeń zostają zawieszone.
3. Gdy żadne znaczenie nie jest już w nauce, uwalnia się **dokładnie jedno** następne nowe znaczenie (najniższy nid, nie wszystkie naraz — inaczej znów interferencja).
4. Gdy aktywne znaczenie dojrzeje (interval ≥ próg) → jego tag znika, a kolejne nowe znaczenie może wejść.

Moduł dotyka **wyłącznie NEW kart** — karty w nauce/review nigdy nie są zawieszane. Karty zawieszone ręcznie (bez tagu modułu) też są zostawiane w spokoju.

## Uczenie na telefonie + synchronizacja

Reviewer hook odpala się tylko na desktopie. Po synchronizacji (`sync_did_finish`) batch scan **odtwarza niezmiennik** dla każdej grupy: znaczenia w nauce zostają aktywne, spośród całkowicie nowych aktywne jest jedno (najniższy nid), reszta zawieszona. Skan jest samonaprawiający — jeśli jakieś znaczenie w nauce zostało błędnie zawieszone wcześniej, kolejny skan je uwalnia.

**Ręczny catch-up:** Narzędzia → Anki Toolkit → „Homograph Manager: przeskanuj całą kolekcję...".

## Konfiguracja

W **Ustawienia → Reguły kart → Odblokowywanie** albo w `config.json`:

```json
"homograph_manager": {
    "interval": 30,
    "field": "ang",
    "note_types": ["angielski"],
    "tag": "tk-homograph-suspended",
    "ignore_tag": "tk-homograph-ignored",
    "show_tooltip": true
}
```

| Pole | Default | Opis |
|---|---|---|
| `interval` | `30` dni | Po ilu dniach interval znaczenie uznane za dojrzałe → uwolnienie następnego |
| `field` | `ang` | Pole, po którego wartości grupowane są homografy |
| `note_types` | `["angielski"]` | Modele, w których moduł grupuje. Pusta lista = wszystkie typy notatek |
| `tag` | `tk-homograph-suspended` | Tag notatek z zawieszonymi homografami |
| `ignore_tag` | `tk-homograph-ignored` | Notatki z tym tagiem są pomijane |
| `show_tooltip` | `true` | Tooltip po batch scan po synchronizacji |

Ograniczenie `note_types` chroni np. talię zdań (Prestonly), gdzie to samo zdanie powtórzone w różnych lekcjach ma identyczne pole `ang` — bez filtra moduł uznałby je za grupę i zawiesił. Notatki spoza `note_types` są pomijane; jeśli wcześniej dostały tag/zawieszenie, najbliższy skan je uwalnia.

## Menu

- **Uwolnij karty zawieszone przez Homograph Manager...** — reset wszystkich zawieszeń (usuwa też tagi).
- **Homograph Manager: przeskanuj całą kolekcję...** — ręczny batch scan.

## Hooki

| Hook | Kiedy | Co robi |
|---|---|---|
| `reviewer_did_answer_card` | Po odpowiedzi (desktop) | `process_reactive` — zawieś/uwolnij homografy |
| `sync_did_finish` | Po synchronizacji | `_run_sync_scan` — batch odtworzenie niezmiennika |
