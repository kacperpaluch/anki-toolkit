# LLM Context — nbsp_remover

## Co robi

Usuwa `&nbsp;` i czyści tagi `<div>` z pól kart. Działa na dwa sposoby:
1. **Automatycznie** — przy każdym dodaniu karty (hook `add_cards_did_add_note`)
2. **Ręcznie** — jednorazowe czyszczenie całej kolekcji przez **Narzędzia → Anki Toolkit → Wyczyść HTML w kolekcji...**

## Pliki

| Plik | Rola |
|---|---|
| `__init__.py` | `setup_menu(parent_menu=None)` — dodaje jedną akcję do menu Anki Toolkit, inicjuje hook dodawania kart, obsługuje auto-run przy starcie; używa `_get_config()` z utils |
| `addcards.py` | Hook na dodawanie kart — czyści pola w locie przy każdym `Add` przez `clean_field()`, wywołuje `mw.col.update_note(note)` |
| `cleaning.py` | Czysta logika czyszczenia: `clean_field()` oraz regexy `NBSP`, `DIV_TAG_RE`, `DIV_WRAP_RE`, `TRAILING_BR_RE`; testowalne bez Anki |
| `collection.py` | Masowe czyszczenie kolekcji przez `find_and_replace` Anki; callbacki `.failure()` zapewniają kontynuację łańcucha przy błędzie |
| `utils.py` | `_get_config()`, `_get_skip_field()`, `_show_tooltip()`, `purge_tooltip`, `editing_tooltip`; importuje regexy z `cleaning.py` dla kompatybilności |

## Konfiguracja

Sekcja `nbsp_remover` w głównym `config.json` toolkitu:

```json
"nbsp_remover": {
    "show_tooltip": true,
    "auto_run_startup": false,
    "skip_field": "ang"
}
```

| Pole | Opis |
|---|---|
| `show_tooltip` | Wyświetlaj powiadomienie po wyczyszczeniu |
| `auto_run_startup` | Automatycznie uruchamiaj purge przy starcie Anki |
| `skip_field` | Pole z którego tagi `<div>` są usuwane całkowicie (zamiast zamiany na `<br>`) |

Ustawienia edytowane przez **Narzędzia → Anki Toolkit → Ustawienia... → zakładka Narzędzia** (sekcja "Czyszczenie HTML").

Odczyt configu w module:
```python
from .utils import _get_config

cfg = _get_config()  # zwraca dict z klucza "nbsp_remover"
```

## Przepływ — tryb auto (addcards.py)

```
Użytkownik klika Add w oknie dodawania kart
  → on_add(note)
      → _get_skip_field() z configu
      → dla każdego pola:
          → clean_field(name, value, skip_field)
              → zamień &nbsp; → " " (literal)
              → jeśli pole == skip_field: usuń tagi <div> i </div> całkowicie
              → pozostałe pola: <div>tekst</div> → tekst<br>, usuń trailing <br>
              → zwróć (cleaned, nbsp_count, div_count, div_br_count)
      → jeśli cokolwiek zmieniono:
          mw.col.update_note(note)   ← jawny zapis do bazy
          addcards = _addcards_ref() ← słaba referencja do okna AddCards
          editing_tooltip()          ← tylko jeśli show_tooltip=true
```

## Wzorzec weakref dla AddCards

`addcards.py` przechowuje referencję do okna `AddCards` przez `weakref.ref`, nie bezpośrednio. Dzięki temu jeśli okno AddCards zostanie zamknięte i zwolnione przez GC, `_addcards_ref()` zwraca `None` zamiast trzymać martwy obiekt. `editing_tooltip` obsługuje `None` jako brak okna.

## Przepływ — tryb purge (collection.py)

```
Narzędzia → Anki Toolkit → Wyczyść HTML w kolekcji...
  → clean_collection()
      → _get_skip_field() z configu
      → find_and_replace(&nbsp; → " ", wszystkie pola)                          # op1
      → find_and_replace(</?div[^>]*> → "", pole skip_field, regex)            # op2 (łączone <div> i </div>)
      → dla każdego pola poza skip_field (równolegle):
          find_and_replace(<div[^>]*>.*?</div> → $1<br>, regex)                # div_br_ops
      → dla każdego pola poza skip_field (równolegle, po zakończeniu div_br):
          find_and_replace(<br>\s*$ → "", regex)                               # cleanup_ops
      → purge_tooltip() z podsumowaniem po zakończeniu wszystkich op
```

Operacje są łączone przez callbacki `.success()` i `.failure()` — sekwencyjny łańcuch: op1→op2→(równolegle div_br_ops)→(równolegle cleanup_ops)→tooltip. `.failure()` zapewnia, że łańcuch nie urywa się przy błędzie.
`operations_remaining` jest jawnie resetowane przed każdą fazą równoległą.

## Zasady czyszczenia

| Pole | Reguła dla `<div>` |
|---|---|
| `skip_field` (domyślnie `ang`) | Usuń tagi `<div[^>]*>` i `</div>` całkowicie (zostawia treść) |
| Pozostałe | `<div[^>]*>tekst</div>` → `tekst<br>`, usuń trailing `<br>` |

Powód: pole `ang` zawiera pojedyncze słowo/wyrażenie — `<div>` psuje wygląd. Pozostałe pola mogą mieć wieloliniową treść gdzie `<br>` jest poprawnym separatorem.

Rejestry regex współdzielone przez `addcards.py` i `collection.py` (zdefiniowane w `cleaning.py`; re-eksportowane przez `utils.py` dla kompatybilności):
- `NBSP` = `"&nbsp;"` (literal)
- `DIV_TAG_RE` = `r"</?div[^>]*>"` — łapie `<div>`, `<div class="...">`, `</div>`
- `DIV_WRAP_RE` = `r"<div[^>]*>(.*?)</div>"` — łapie div z zawartością
- `TRAILING_BR_RE` = `r"<br>\s*$"` — trailing `<br>` z opcjonalnymi spacjami

## Zależności

- Stdlib: `re`
- Anki API: `aqt.operations.note.find_and_replace`, `aqt.addcards.AddCards`, `mw.col.update_note`, hooki `add_cards_did_init`, `add_cards_did_add_note`
- Własne: `common.ADDON_NAME`, `nbsp_remover.cleaning.clean_field`
- Brak pip packages
