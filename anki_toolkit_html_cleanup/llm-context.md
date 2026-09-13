# LLM Context — Anki Toolkit: HTML Cleanup

## Zakres

Dodatek stosuje listę reguł „znajdź → zamień" do pól notatek. Reguły definiuje
użytkownik w tabeli w ustawieniach. Działa przy dodawaniu notatki oraz na
żądanie w całej kolekcji.

## Pliki

| Plik | Rola |
|---|---|
| `cleaning.py` | silnik reguł i zestaw domyślny, bez zależności od Anki |
| `__init__.py` | hooki Add Cards, `CollectionOp`, menu i konfiguracja |
| `settings.py` | dialog ustawień z tabelą reguł |

## Niezmienniki

- `clean_field()` jest jedynym silnikiem reguł dla Add Cards i skanu kolekcji.
- Reguły domyślne zastępują oba końce bloków `<div>` przez `<br>`, następnie
  scalają sąsiadujące separatory i obcinają je na brzegach pola.
- `default_rules(skip_field)` służy zarówno za zestaw domyślny, jak i za migrację
  configów sprzed edytowalnych reguł. `get_config()` uzupełnia brakujący klucz,
  zachowuje pustą listę i aktualizuje wyłącznie dokładny stary zestaw domyślny.
- `clean_field()` zwraca liczniki kluczowane indeksem reguły; tooltip mapuje je
  na `name`, więc indeksy muszą pochodzić z tej samej listy, która czyściła.
- Niepoprawny regex jest pomijany w locie; dialog odrzuca go przy zapisie
  (`re.compile`) — to jedyne miejsce walidacji.
- `MAX_PASSES` i `MAX_FIELD_CHARS` ograniczają rozrost tekstu; zamiennik jest
  budowany przyrostowo z kontrolą rozmiaru. Nie ograniczają czasu działania `re`.
- `_clean_note` zbiera zmiany przed mutacją, więc błąd rozrostu nie zmienia
  części notatki. Hook `add_cards_will_add_note` zwraca błąd bez zapisu do kolekcji.
- Skan kolekcji musi używać `CollectionOp`, aby tworzyć poprawny krok undo.
- Hook Add Cards działa na głównym wątku; nie przenoś zapisu notatki do workera.
- `save_config()` zachowuje nieznane klucze konfiguracji profilu.

Interfejs i opis użytkowy są w `README.md`. Dodatek nie zależy od innych
pakietów Anki Toolkit.
