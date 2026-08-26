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
- Reguły stosowane są w kolejności listy — `Bloki <div> → <br>` musi wyprzedzać
  `Obetnij końcowy <br>`, inaczej zostaje wiszący `<br>`.
- `default_rules(skip_field)` służy zarówno za zestaw domyślny, jak i za migrację
  configów sprzed edytowalnych reguł (`get_config()` uzupełnia brakujące `rules`).
- `clean_field()` zwraca liczniki kluczowane indeksem reguły; tooltip mapuje je
  na `name`, więc indeksy muszą pochodzić z tej samej listy, która czyściła.
- Niepoprawny regex jest pomijany w locie; dialog odrzuca go przy zapisie
  (`re.compile`) — to jedyne miejsce walidacji.
- `MAX_PASSES` ogranicza `repeat`; koszt jest wykładniczy, nie podnoś bez limitu
  rozmiaru.
- Skan kolekcji musi używać `CollectionOp`, aby tworzyć poprawny krok undo.
- Hook Add Cards działa na głównym wątku; nie przenoś zapisu notatki do workera.
- `save_config()` zachowuje nieznane klucze konfiguracji profilu.

Interfejs i opis użytkowy są w `README.md`. Dodatek nie zależy od innych
pakietów Anki Toolkit.
