# Anki Toolkit: HTML Cleanup

Samodzielny dodatek czyszczący HTML w polach notatek według reguł, które
definiujesz sam.

## Użycie

- Notatki dodawane przez okno **Dodaj** są czyszczone automatycznie przed
  zapisaniem.
- **Narzędzia → Anki Toolkit: HTML Cleanup** zawiera ustawienia i ręczne
  czyszczenie całej kolekcji.
- Opcjonalny automatyczny skan przy otwieraniu profilu można włączyć w UI.

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
Niezmieniony stary zestaw domyślny jest aktualizowany przy odczycie; własne reguły
pozostają bez zmian. Pusta lista wyłącza czyszczenie — nie przywraca domyślnych reguł.

Czyszczenie w Dodaj odbywa się przed zapisem, w ramach tego samego kroku undo.
Reguły mają limit 20 przebiegów i 1 000 000 znaków pola. Przekroczenie limitu
przerywa operację bez zapisania częściowych zmian; ogranicza to rozrost tekstu,
ale nie zastępuje ostrożności przy tworzeniu kosztownych wyrażeń regularnych.

Konfiguracja nie wymaga edycji plików. Nie uruchamiaj równocześnie starego
modułu `nbsp_remover` w scalonym Anki Toolkit: oba dodatki czyszczą notatki
dodawane przez to samo okno Anki.
