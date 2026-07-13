# Deck Router

Kieruje karty do talii na podstawie **tagu notatki** (opcjonalnie zawężone do konkretnego szablonu karty).

## Po co to

Natywny **Deck Override** w Anki działa tylko **per-szablon** karty — ustawiasz go w opcjach szablonu i wszystkie karty z tego szablonu lądują w jednej talii. Nie da się nim rozdzielić kart tego samego szablonu na różne talie w zależności od tego, *co* to za karta.

Deck Router dokłada brakujący wymiar: **per-tag**. Otagowujesz notatkę (np. `abc123`), a jej karty trafiają do innej talii niż reszta kolekcji — nadpisując natywny override tylko dla tych kart.

## Zasada działania

- Reguła = `{tag, (opcjonalnie) szablon, talia}`.
- Dla każdej karty sprawdzane są reguły po kolei — **pierwsza pasująca wygrywa**. Reguła pasuje, gdy jej tag jest na notatce **oraz** jej szablon zgadza się z szablonem karty (albo szablon jest pusty = wszystkie karty notatki).
- Pasująca karta jest przenoszona do talii z reguły (talia tworzona automatycznie, jeśli nie istnieje). Karta już będąca we właściwej talii jest pomijana.
- **Notatka bez pasującej reguły nie jest ruszana** — zostaje tam, gdzie umieścił ją natywny Deck Override / bieżąca talia. Pusta lista reguł = moduł nic nie robi.

Tag jest własnością **notatki**, więc wszystkie jej karty dzielą ten sam tag — reguła bez szablonu przenosi cały komplet kart do jednej talii. Reguła ze szablonem pozwala rozbić karty jednej notatki na różne talie.

## Kiedy się odpala

| Wyzwalacz | Kiedy |
|---|---|
| Okno **Dodaj** | Hook `add_cards_did_add_note` — przy ręcznym dodaniu notatki |
| **AI-workflow / batch w przeglądarce** | Po zapisaniu zmienionych notatek (`route_after_edit` wołane z `ai_generator`) |
| **Ręcznie** | Narzędzia → Anki Toolkit → „Deck Router: uporządkuj istniejące karty…” albo przycisk **„Uporządkuj istniejące karty…”** w zakładce ustawień — przechodzi po wszystkich notatkach z tagami z reguł |

## Konfiguracja

**Ustawienia → Reguły kart → Kierowanie do talii** — tabela reguł (Dodaj/Usuń wiersz):

| Kolumna | Opis |
|---|---|
| **Tag** | Tag, który musi być na notatce. Pole tekstowe. |
| **Szablon** | Lista rozwijana: `(wszystkie)` albo konkretny szablon z Twoich typów notatek. |
| **Talia docelowa** | Lista rozwijana z istniejących talii — **edytowalna**, możesz wpisać nową (zostanie utworzona). Zagnieżdżanie przez `::`. |

Listy szablonów i talii są pobierane z kolekcji, więc unikasz literówek.

Odpowiednik w `config.json`:

```json
"deck_router": {
    "rules": [
        {"tag": "abc123", "template": "pol-ang", "deck": "Angielski::Osobne::pol-ang"},
        {"tag": "abc123", "deck": "Angielski::Osobne"}
    ]
}
```

Reguły z pustym tagiem lub pustą talią są przy zapisie pomijane.

## Menu

- **Narzędzia → Anki Toolkit → Deck Router: uporządkuj istniejące karty…** — retroaktywne uporządkowanie: znajduje notatki z tagami z reguł i przenosi ich karty (w tle, jeden krok undo).
- Ta sama akcja jest dostępna przyciskiem **„Uporządkuj istniejące karty…”** w zakładce **Ustawienia → Reguły kart → Kierowanie do talii** — używa reguł aktualnie widocznych w tabeli (także jeszcze niezapisanych), więc można od razu przetestować nową regułę.

## Włączanie / wyłączanie

**Ustawienia → Moduły** (lub `config.json` → `modules.deck_router`). Zmiana wymaga restartu Anki.
