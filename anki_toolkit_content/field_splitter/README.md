# Field Splitter — rozdzielanie pól

Rozdziela zawartość pola źródłowego (np. `przyklad`) po separatorze i **kopiuje** części do kolejnych pól docelowych (`p1`, `p2`, `p3`…). Pole źródłowe nie jest modyfikowane — to kopia, nie przeniesienie.

## Kiedy używać

Gdy jedno pole zawiera wiele elementów rozdzielonych separatorem (np. przykłady z nagraniami `<br><br>`) i chcesz je rozbić na osobne pola, np. aby wyświetlać pojedynczy przykład na karcie bez kombinowania z CSS/JS.

## Jak używać

### Batch na zaznaczonych notatkach

**PPM w przeglądarce → Anki Toolkit → Rozdziel pole przyklad → p1, p2, p3...**

Etykieta pokazuje skonfigurowane pole źródłowe i pierwsze 3 pola docelowe. Batch działa w tle przez `CollectionOp` — jeden krok undo (**Edycja → Cofnij** cofa cały batch).

### Cała kolekcja

**Narzędzia → Anki Toolkit → Rozdziel pola w kolekcji...**

Wyświetla dialog z potwierdzeniem (liczba notatek do przetworzenia). Po zatwierdzeniu uruchamia batch na wszystkich notatkach — także jeden krok undo.

## Przykład

Pole `przyklad`:
```html
Many people were murdered in the Nazi death camp during World War II.[sound:tts_oe93owgdrkgo.mp3]<br><br>
The museum tells the story of prisoners who were sent to a death camp.[sound:tts_9gfu5ninen4f.mp3]<br><br>
Auschwitz was a death camp where the Nazis killed large numbers of civilians and prisoners.[sound:tts_kwzj4ughyfk9.mp3]
```

Po rozdzieleniu (separator `<br><br>`, pola `p1, p2, p3`):

| Pole | Wartość |
|---|---|
| `p1` | `Many people were murdered in the Nazi death camp during World War II.[sound:tts_oe93owgdrkgo.mp3]` |
| `p2` | `The museum tells the story of prisoners who were sent to a death camp.[sound:tts_9gfu5ninen4f.mp3]` |
| `p3` | `Auschwitz was a death camp where the Nazis killed large numbers of civilians and prisoners.[sound:tts_kwzj4ughyfk9.mp3]` |
| `przyklad` | *(niezmienione)* |

Tagi `[sound:...]` są zachowane — kopiowany jest cały segment łącznie z audio.

## Reguły

- Pierwsza część → `p1`, druga → `p2`, itd. (kolejność wg `target_fields`)
- **Więcej części niż pól docelowych**: nadmiarowe części są pomijane
- **Mniej części niż pól docelowych**: pozostałe pola nietknięte
- Pole źródłowe zawsze zachowane
- Pola docelowe nieistniejące w typie notatki są pomijane
- Tylko notatki posiadające pole źródłowe są przetwarzane

## Nadpisywanie

| Opcja | Zachowanie |
|---|---|
| **Nadpisuj istniejące pola** ON (domyślnie) | Zawsze nadpisuje pole docelowe nową treścią |
| **Nadpisuj istniejące pola** OFF | Wypełnia tylko puste pola docelowe; pola z treścią są pomijane |

Tryb OFF jest bezpieczny gdy chcesz uzupełnić brakujące pola bez ryzyka nadpisania ręcznych poprawek.

## Konfiguracja

**Narzędzia → Anki Toolkit → Ustawienia... → Workflowy → Rozdzielanie pól**

| Pole | Domyślnie | Opis |
|---|---|---|
| Pole źródłowe | `"przyklad"` | Pole z danymi do rozdzielenia (nie jest modyfikowane) |
| Separator | `"<br><br>"` | Tekst rozdzielający części (whitespace-tolerant) |
| Pola docelowe | `"p1, p2, p3, p4, p5"` | Pola oddzielone przecinkami |
| Nadpisuj istniejące pola | `true` | `true` = nadpisuj zawsze; `false` = wypełniaj tylko puste |

```json
"field_splitter": {
    "source_field": "przyklad",
    "separator": "<br><br>",
    "target_fields": "p1, p2, p3, p4, p5",
    "overwrite": true
}
```

Można wyłączyć cały moduł przez sekcję `modules` w `config.json`:
```json
"modules": {
    "field_splitter": false
}
```

## Separator — whitespace-tolerant

Whitespace w separatorze dopasowuje dowolny ciąg whitespace w treści. Dzięki temu `"<br> <br>"` jako separator zadziała także gdy w treści jest `"<br><br>"` (bez spacji) lub `"<br>  <br>"` (z dwiema spacjami). Mechanizm jest współdzielony z `common/text.py::split_separator_regex()`.
