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

Kolejność ma znaczenie — `▲`/`▼` ją zmieniają. Domyślne cztery reguły
(`&nbsp;` → spacja, bloki `<div>` → `<br>`, usunięcie `<div>` w polu `ang`,
obcięcie końcowego `<br>`) przywraca przycisk **Przywróć domyślne**.

Konfiguracja nie wymaga edycji plików. Nie uruchamiaj równocześnie starego
modułu `nbsp_remover` w scalonym Anki Toolkit: oba dodatki czyszczą notatki
dodawane przez to samo okno Anki.
