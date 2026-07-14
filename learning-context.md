# LLM Context — reguły kart i nauki

Przeczytaj ten plik przy zmianach w `sentence_unlocker`, `sibling_manager`,
`homograph_manager`, `deck_router` albo `filtered_deck`.

## Odpowiedzialności

| Moduł | Reguła |
|---|---|
| `sentence_unlocker` | Stopniowo wpisuje markery tworzące karty kolejnych zdań |
| `sibling_manager` | Zawiesza nowe siblingi, dopóki aktywna karta nie dojrzeje |
| `homograph_manager` | Rozdziela osobne notatki z tym samym słowem — jedno znaczenie naraz |
| `deck_router` | Przenosi karty do talii według tagu i opcjonalnie szablonu |
| `filtered_deck` | Tworzy tymczasowe talie powtórkowe z presetów |

Moduły pozostają technicznie niezależne, ale są prezentowane razem w ustawieniach
**Reguły kart**.

## Sentence Unlocker

`sentence_unlocker/logic.py:process_note` jest czystym rdzeniem. Karty główne
muszą osiągnąć `threshold`, aby odblokować pierwsze zdanie. Następne zdanie jest
odblokowywane dopiero po dojrzeniu karty poprzedniego zdania.

Najważniejsze niezmienniki:

- Na jedno wywołanie odblokuj najwyżej jeden kolejny etap.
- Puste pola zdań są pomijane.
- Marker jest jednokierunkowy i nigdy nie jest automatycznie usuwany.
- Usunięcie markera mogłoby skasować wygenerowaną kartę i jej historię.
- `done_tag` oznacza notatkę całkowicie przetworzoną albo pozbawioną zdań.
- `ignore_tag` wyłącza regułę dla notatki.

Entry points w `sentence_unlocker/__init__.py`:

- odpowiedź reviewera,
- skan po synchronizacji,
- ręczny skan z menu.

## Sibling Manager

`sibling_manager/logic.py:process_note` obsługuje reakcję na odpowiedź, a
`process_note_sync` nadrabia zmiany wykonane poza desktopem.

Najważniejsze niezmienniki:

- Niedojrzała karta zawiesza tylko nowe siblingi.
- Moduł dotyka wyłącznie kart oznaczonych własnym tagiem.
- Dojrzała karta uwalnia wcześniej zawieszone siblingi.
- Kart w nauce i review nie należy zawieszać jako nowych siblingów.
- `ignore_tag` wyłącza regułę dla całej notatki.

Sentence Unlocker i Sibling Manager mogą działać jednocześnie: pierwszy decyduje,
czy karta istnieje, drugi czy nowo utworzony sibling jest chwilowo zawieszony.
Przy zmianie jednego mechanizmu sprawdź scenariusz współistnienia z drugim.

## Homograph Manager

`homograph_manager/logic.py:process_reactive` reaguje na odpowiedź, a
`process_group_sync` odtwarza niezmiennik po synchronizacji. Grupa to osobne
notatki o tej samej wartości pola kluczowego (domyślnie `ang`) — nie siblingi
jednej notatki. Szczegóły: `homograph_manager/llm-context.md`.

Najważniejsze niezmienniki:

- W grupie co najwyżej jedno niedojrzałe znaczenie ma odwieszone NEW karty.
- Po dojrzeniu aktywnego znaczenia uwalnia się dokładnie jedno następne (najniższy
  nid), nigdy wszystkie naraz — inaczej kilka frontów naraz znów interferuje.
- Moduł dotyka wyłącznie NEW kart **innych** notatek z grupy, nigdy notatki, na
  którą odpowiedziano — to rozłącza go od Sibling Managera.
- Własny tag (`tk-homograph-suspended`), rozłączny z tagiem Sibling Managera;
  `ignore_tag` wyłącza regułę dla notatki.

Sibling Manager rozkłada dwie strony jednego znaczenia; Homograph Manager rozkłada
znaczenia. Sync scan homografów startuje 600 ms po syncu (po Sibling Managerze,
500 ms), by działać na ustabilizowanym stanie.

## Deck Router

`deck_router/logic.py:match_deck` jest czystą funkcją: pierwsza pasująca reguła
wygrywa. Reguła wymaga tagu i talii; szablon jest opcjonalnym zawężeniem.

Routing uruchamia się:

- po dodaniu notatki,
- po batchu lub workflow AI,
- ręcznie dla istniejących kart.

Dla cloze i zwykłych kart korzystaj z API szablonu karty, nie zakładaj, że
`card.ord` zawsze indeksuje listę szablonów w ten sam sposób.

## Filtered Deck

Moduł tworzy lub przebudowuje talię filtrowaną z wybranego presetu. Jest to
narzędzie operacyjne, a nie trwała reguła kolekcji. Zmiany API talii filtrowanych
między wersjami Anki powinny być izolowane w tym module.

## Mutacje kolekcji

- Hook reviewera działa w głównym wątku.
- Skan całej kolekcji powinien być opakowany w `CollectionOp`.
- Po zmianie kart/notatek zwróć odpowiednie `OpChanges`.
- Operacje muszą być idempotentne: ponowny skan po synchronizacji nie może
  tworzyć dodatkowych zmian bez potrzeby.

## Testy

- `tests/test_sentence_unlocker.py` — łańcuch odblokowywania.
- `tests/test_homograph_manager.py` — grupowanie po słowie, uwalnianie po jednym.
- `tests/test_pure_logic.py` — dopasowanie Deck Routera i wybrane reguły.
- Przy zmianie Sibling/Homograph Managera dodaj test czystej logiki zamiast testować Qt.
