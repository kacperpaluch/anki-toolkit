# Sentence Unlocker — stopniowe odblokowywanie zdań

Automatycznie wpisuje znacznik do pól `p1-tak`/`p2-tak`/`p3-tak`, gdy karty odpowiednio dojrzeją — dzięki czemu karty ćwiczeń „Uzupełnij" (`p1-nauka`/`p2-nauka`/`p3-nauka`) generują się dopiero wtedy, kiedy słowo jest już opanowane.

## Idea

Model `angielski` ma szablony zdań z warunkiem `{{#p1-tak}}{{#p1-nauka}}…` — karta powstaje tylko, gdy `pX-tak` jest niepuste. Ten moduł steruje tym znacznikiem, **stopniowo**:

1. karty **główne** `ang-pol` i `pol-ang` dojrzeją (interval ≥ próg) → odblokuj zdanie 1 (`p1-tak` = `tak`)
2. karta zdania 1 (`p1-nauka`) dojrzeje → odblokuj zdanie 2
3. karta zdania 2 dojrzeje → odblokuj zdanie 3

Nie dokładasz trudniejszych ćwiczeń produkcyjnych, dopóki wcześniejszy materiał nie siedzi. To „odwrotność" Sibling Managera: tam nowe siblingi są **zawieszane** do dojrzenia aktywnej karty, tu nowe karty są **tworzone** po dojrzeniu poprzednich.

## Jednokierunkowość ⚠️

Znacznik **nigdy nie jest usuwany**. Wyczyszczenie `pX-tak` skasowałoby już wygenerowaną kartę razem z jej historią powtórek. Raz odblokowane zostaje odblokowane, nawet jeśli karta później „wypadnie" poniżej progu.

## Jak działa

| Wyzwalacz | Kiedy |
|---|---|
| Hook `reviewer_did_answer_card` | Po każdej odpowiedzi na desktopie — odblokowuje kolejne zdanie, jeśli warunek spełniony |
| Hook `sync_did_finish` | Po synchronizacji z telefonu/AnkiWeb — batch catch-up (500 ms po sync) |
| **Narzędzia → Anki Toolkit → Sentence Unlocker: przeskanuj kolekcję...** | Ręczny batch (np. przy pierwszym uruchomieniu) |

Batch przetwarza notatki modelu docelowego bez tagu „ukończonych" i „ignorowanych" (`note:… -tag:done -tag:ignore`). Notatka bez żadnego zdania jest od razu tagowana jako ukończona, żeby skanowanie ją pomijało.

**Nie uruchamia się przy starcie Anki** i nie musi — hook reviewer'a odblokowuje kolejne zdanie dokładnie w momencie, gdy odpowiadasz na kartę i osiąga ona próg (interwał zmienia się tylko przy odpowiedzi), a reviewy z telefonu łapie hook po synchronizacji. Ręczny skan to catch-up „na teraz".

**Talie i subtalie nie mają znaczenia.** Moduł patrzy na model notatki i nazwy **szablonów kart**, nie na talię. Jeśli rozdzielasz karty do subtalii (`ang::ang-pol`, `ang::pol-ang`), config zostaje bez zmian — `main_templates` to `ang-pol`/`pol-ang` (nazwy szablonów).

**Komunikaty:** ręczny skan **zawsze** pokazuje tooltip z wynikiem — również „brak zdań do odblokowania", gdy żadna karta nie osiągnęła progu (dlatego cisza = nic nie było jeszcze dojrzałe). Automatyczny skan po syncu pokazuje tooltip tylko gdy coś odblokował. Po każdej odpowiedzi log trafia do bufora (**Ustawienia → Diagnostyka → Logi**), bez tooltipa (żeby nie spamować).

## Konfiguracja

**Narzędzia → Anki Toolkit → Ustawienia... → Narzędzia → Sentence Unlocker** — wszystko edytowalne z UI:

| Pole | Domyślnie | Opis |
|---|---|---|
| `model` | `angielski` | Typ notatki, którego dotyczy moduł (inne modele są pomijane) |
| `threshold` | `21` | Próg dojrzałości karty w dniach (`ivl ≥ threshold`) |
| `marker` | `tak` | Wartość wpisywana do pola `-tak` |
| `main_templates` | `ang-pol, pol-ang` | **Nazwy szablonów kart** (typów kart w notatce, **nie talii**), których dojrzałość odblokowuje pierwsze zdanie |
| `chain` | `p1-nauka:p1-tak, p2-nauka:p2-tak, p3-nauka:p3-tak` | Zdania w kolejności odblokowywania (pary `pole-nauka:pole-tak`) |
| `ignore_tag` | `tk-unlock-ignored` | Tag wyłączający moduł dla danej notatki |
| `done_tag` | `tk-unlock-done` | Tag notatek w pełni odblokowanych (pomijane w batchu) |
| `show_tooltip` | `true` | Tooltip z podsumowaniem po skanowaniu |

W UI `main_templates` podaje się przecinkami, a `chain` jako pary `pole-nauka:pole-tak` rozdzielone przecinkami (kolejność = kolejność odblokowywania).

```json
"sentence_unlocker": {
    "model": "angielski",
    "threshold": 21,
    "marker": "tak",
    "main_templates": ["ang-pol", "pol-ang"],
    "chain": [
        {"nauka_field": "p1-nauka", "tak_field": "p1-tak"},
        {"nauka_field": "p2-nauka", "tak_field": "p2-tak"},
        {"nauka_field": "p3-nauka", "tak_field": "p3-tak"}
    ],
    "ignore_tag": "tk-unlock-ignored",
    "done_tag": "tk-unlock-done",
    "show_tooltip": true
}
```

> Nazwa pola w `nauka_field` jest jednocześnie nazwą szablonu karty tego zdania — moduł po niej sprawdza dojrzałość karty. W modelu `angielski` pokrywają się (`p1-nauka` itd.).

## Włączanie / wyłączanie

**Ustawienia → Moduły → Sentence Unlocker** (`config.json` → `modules.sentence_unlocker`). Zmiana wymaga restartu Anki.
