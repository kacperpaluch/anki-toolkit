# Czyszczenie HTML (`html_cleanup/`)

Czyści HTML w polach notatek według reguł, które definiujesz sam.

## Użycie

- Notatki dodawane przez okno **Dodaj** są czyszczone automatycznie przed
  zapisaniem.
- Reguły edytujesz w **Narzędzia → Anki Toolkit → Ustawienia… → Czyszczenie
  HTML**, a całą kolekcję czyścisz przez **Narzędzia → Anki Toolkit → Wyczyść
  HTML w kolekcji…**.
- Opcja **Czyść całą kolekcję przy otwarciu profilu** uruchamia ten sam skan
  automatycznie; **Pokazuj podsumowanie po czyszczeniu** steruje dymkiem.
- Czyszczenie całej kolekcji to jeden krok **Edycja → Cofnij**.

## Reguły

Każda reguła to jedno „znajdź → zamień", stosowane kolejno od góry listy.
W ustawieniach edytujesz je w tabeli:

| Kolumna | Znaczenie |
|---|---|
| Nazwa | zaznaczenie włącza regułę; nazwa trafia do podsumowania |
| Znajdź / Zamień na | wzorzec i zamiennik |
| Regex | wzorzec jako wyrażenie regularne (DOTALL, bez wielkości liter); w zamienniku działa `\1` |
| Powtarzaj | stosuj wielokrotnie, aż przestanie coś zmieniać — dla tagów zagnieżdżonych |
| Pola | puste = wszystkie, `ang` = tylko to pole, `!ang` = wszystkie oprócz; kilka po przecinku |

Kolejność ma znaczenie — `▲`/`▼` ją zmieniają. Domyślne pięć reguł
(`&nbsp;` → spacja, tagi `<div>` → `<br>`, usunięcie `<div>` w polu `ang`,
scalenie sąsiadujących `<br>` i obcięcie brzegowych `<br>`) przywraca przycisk
**Przywróć domyślne**. Zachowują one granice także przy zagnieżdżonych blokach.
Reguły domyślne pochodzą z szablonu `config.json`. Pusta lista wyłącza
czyszczenie — nie przywraca domyślnych reguł.

Czyszczenie w Dodaj odbywa się przed zapisem, w ramach tego samego kroku undo.
Reguły mają limit 20 przebiegów i 1 000 000 znaków pola. Przekroczenie limitu
przerywa operację bez zapisania częściowych zmian; ogranicza to rozrost tekstu,
ale nie zastępuje ostrożności przy tworzeniu kosztownych wyrażeń regularnych.
