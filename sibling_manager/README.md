# Sibling Manager

Moduł dynamicznego zawieszania kart-siblingów (siblings) w Anki.

Inspiracja: [SibPush — Delay New Sibs](https://github.com/DerDemystifier/SibPush_Delay-New-Sibs)

## Zasada działania

W przeciwieństwie do SibPush, który z góry zawiesza wszystkie nowe siblingi poza pierwszym (wg kolejności szablonów), ten moduł jest **reaktywny** — działa dopiero po odpowiedzi na kartę.

1. Anki pokazuje kartę (dowolną z siblingów) → odpowiadasz
2. Jeśli interval < próg (domyślnie 30 dni) → **zawiesza wszystkie inne NEW siblingi**
3. Gdy aktywna karta dojrzeje (interval ≥ próg) → **uwolnić wszystkie zawieszone siblingi** na raz
4. Anki pokazuje kolejną (losowo) → odpowiadasz → reszta znów zawieszona → cykl się powtarza

Większa losowość niż w SibPush: to Anki decyduje którą kartę pokazać następną, a nie z góry ustalona kolejność szablonów.

## Zapomnienie karty

Jeśli dojrzała karta zostanie zapomniona (interval spadnie poniżej progu), hook przy kolejnej odpowiedzi znów zawiesi wszystkie NEW siblingi. Karty które są już w nauce/review (nie `CARD_TYPE_NEW`) nie są dotykane — moduł zarządza tylko kartami nowymi.

## Uczenie na telefonie + synchronizacja

Hook `reviewer_did_answer_card` odpala się **tylko na desktopie** — recenzje zrobione na AnkiMobile/AnkiWeb go nie trigerrują.

Po synchronizacji desktopa automatycznie uruchamia się **batch scan** (`sync_did_finish` hook, 500 ms po syncu):
- Skanuje wszystkie notatki z NEW kartami (lub z tagiem `tk-sib-suspended`)
- Dla każdej notatki sprawdza stan wszystkich non-NEW kart:
  - Jeśli jakakolwiek non-NEW karta jest immature (interval < próg) → zawiesza NEW siblingi
  - Jeśli wszystkie non-NEW karty są mature → uwalnia zawieszone NEW siblingi
- Działa w tle (CollectionOp) — Anki nie zamarza, jeden krok undo

**Ręczny catch-up:** Narzędzia → Anki Toolkit → „Przetwórz kolekcję (sync catch-up)..." — uruchamia ten sam scan ręcznie (przydatne gdy auto-scan nie zadziałał lub sync był wyłączony).

## Konfiguracja

W **Ustawienia → Narzędzia → Sibling Manager**:

| Pole | Default | Opis |
|---|---|---|
| Próg dojrzałości | `30` dni | Po ilu dniach interval karta uznana za dojrzałą → uwolnienie siblingów |
| Tag zawieszonych | `tk-sib-suspended` | Tag dodawany do notatki gdy ma zawieszone siblingi |
| Tag ignorowanych | `tk-sib-ignored` | Notatki z tym tagiem są pomijane przez moduł |

Albo w `config.json`:

```json
"sibling_manager": {
    "interval": 30,
    "tag": "tk-sib-suspended",
    "ignore_tag": "tk-sib-ignored"
}
```

## Menu

- **Narzędzia → Anki Toolkit → Uwolnij karty zawieszone przez Sibling Manager...** — reset wszystkich zawieszeń (jeden krok undo, usuwa też tagi z notatek)
- **Narzędzia → Anki Toolkit → Przetwórz kolekcję (sync catch-up)...** — ręczny batch scan (ten sam co po syncu)

## Hooki

| Hook | Kiedy | Co robi |
|---|---|---|
| `reviewer_did_answer_card` | Po odpowiedzi na karcie (desktop) | `process_note` — reactive suspend/unsuspend |
| `sync_did_finish` | Po synchronizacji | `_run_sync_scan` — batch catch-up po recenzjach z telefonu |

## Współistnienie z SibPush

Jeśli używałeś wcześniej SibPush, **wyłącz go** przed włączeniem tego modułu — oba zarządzają zawieszaniem i mogłyby konfliktować. SibPush pre-suspenduje po kolei, ten moduł suspenduje reaktywnie po odpowiedzi.
