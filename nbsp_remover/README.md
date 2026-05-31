# Nbsp Remover — czyszczenie &nbsp; i tagów div

Automatycznie usuwa `&nbsp;` i czyści tagi `<div>` z pól kart. Eliminuje artefakty HTML wklejane z zewnętrznych źródeł (strony internetowe, PDF, inne aplikacje).

## Jak działa

### Tryb automatyczny (przy dodawaniu kart)

Każda karta dodawana przez okno **Add** jest automatycznie czyszczona przed zapisem. Jeśli cokolwiek zostało zmienione, pojawia się tooltip z podsumowaniem.

### Tryb ręczny (czyszczenie całej kolekcji)

**Narzędzia → Anki Toolkit → Purge collection from &nbsp;**

Czyści wszystkie notatki w kolekcji. Operacja jest nieodwracalna — wykonaj backup przed użyciem na dużej kolekcji.

## Reguły czyszczenia

| Element | Pole pomijane (domyślnie `ang`) | Pozostałe pola |
|---|---|---|
| `&nbsp;` | Zamień na spację | Zamień na spację |
| `<div>` i `</div>` | Usuń całkowicie | — |
| `<div>tekst</div>` | — | Zamień na `tekst<br>` |
| Trailing `<br>` | — | Usuń z końca pola |

**Dlaczego inne reguły dla pola pomijanego?**
Pole pomijane (domyślnie `ang`) zawiera pojedyncze słowo lub krótkie wyrażenie — `<div>` psuje wygląd i jest zbędny. Pozostałe pola mogą zawierać wieloliniowe definicje, gdzie `<br>` jest poprawnym separatorem linii.

## Przykład

Wklejony tekst z przeglądarki:
```html
<div>look&nbsp;forward&nbsp;to</div>
```

Po czyszczeniu (pole `ang`):
```
look forward to
```

Wklejony tekst (inne pole):
```html
<div>to wait for something</div><div>with excitement</div>
```

Po czyszczeniu:
```
to wait for something<br>with excitement
```

## Konfiguracja

**Narzędzia → Anki Toolkit → Ustawienia... → zakładka nbsp Remover**

| Opcja | Domyślnie | Opis |
|---|---|---|
| Pokazuj tooltip | `true` | Wyświetlaj powiadomienie po wyczyszczeniu |
| Czyść przy starcie | `false` | Automatycznie uruchamiaj purge przy starcie Anki |
| Pole pomijane | `"ang"` | Pole z którego tagi `<div>` są usuwane całkowicie (zamiast zamiany na `<br>`) |

```json
"nbsp_remover": {
    "show_tooltip": true,
    "auto_run_startup": false,
    "skip_field": "ang"
}
```

Można wyłączyć cały moduł przez sekcję `modules` w `config.json`:
```json
"modules": {
    "nbsp_remover": false
}
```
