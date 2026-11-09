# Rozdzielanie pól (`field_splitter/`)

Dzieli pole źródłowe (np. `przyklad`) separatorem i **kopiuje** kolejne części
do pól docelowych (`p1`, `p2`, `p3`…). Pole źródłowe zostaje bez zmian.
Ustawienia są w **Ustawienia → Rozdzielanie pól**.

## Gdzie to jest

- **Przeglądarka → prawy klik → Anki Toolkit → Rozdziel pole …** dla zaznaczonych notatek.
- **Narzędzia → Anki Toolkit → Operacje na kolekcji → Rozdziel pola w kolekcji…** dla całej kolekcji.
- Krok **Rozdziel** w sekwencjach.

Każde uruchomienie to jeden krok cofania (**Edycja → Cofnij**).

## Przykład

Pole `przyklad` z trzema zdaniami rozdzielonymi `<br><br>` daje `p1`, `p2`
i `p3` — po jednym zdaniu z jego `[sound:…]`.

## Reguły

- Kolejne części trafiają do kolejnych pól z listy; nadmiarowe części są pomijane,
  a nadmiarowe pola zostają nietknięte.
- Pola docelowe, których nie ma w typie notatki, są pomijane. Pole źródłowe wpisane
  na listę celów też jest pomijane.
- Spacje w separatorze pasują do dowolnych odstępów (`<br> <br>` = `<br><br>`),
  kilka separatorów pod rząd liczy się jak jeden, a puste części są pomijane.
- **Nadpisuj istniejące pola** włączone: pola docelowe zawsze dostają nową treść.
  Wyłączone: wypełniane są tylko puste pola.

## Konfiguracja (`field_splitter`)

```json
"field_splitter": {
    "source_field": "przyklad",
    "separator": "<br><br>",
    "target_fields": "p1, p2, p3, p4, p5",
    "overwrite": true
}
```

Reguła separatora jest ta sama co w `common/text.py::split_separator_regex()`;
`splitting.py` ma jej kopię, żeby logikę dało się testować bez Anki.
