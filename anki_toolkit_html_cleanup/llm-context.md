# LLM Context — Anki Toolkit: HTML Cleanup

## Zakres

Dodatek normalizuje `&nbsp;` i tagi `<div>` w polach notatek. Działa przy
dodawaniu notatki oraz na żądanie w całej kolekcji.

## Pliki

| Plik | Rola |
|---|---|
| `cleaning.py` | czyste, testowalne reguły normalizacji |
| `__init__.py` | hooki Add Cards, `CollectionOp`, menu i konfiguracja |
| `settings.py` | dialog ustawień w Narzędziach |

## Niezmienniki

- `clean_field()` jest jedynym źródłem reguł czyszczenia dla Add Cards i skanu
  całej kolekcji.
- W `skip_field` tagi `<div>` usuwa się bezpośrednio; w innych polach bloki
  `<div>` przechodzą na `<br>`, aby zachować podział linii.
- Skan kolekcji musi używać `CollectionOp`, aby tworzyć poprawny krok undo.
- Hook Add Cards działa na głównym wątku; nie przenoś zapisu notatki do workera.
- `save_config()` zachowuje nieznane klucze konfiguracji profilu.

Interfejs i opis użytkowy są w `README.md`. Dodatek nie zależy od innych
pakietów Anki Toolkit.
