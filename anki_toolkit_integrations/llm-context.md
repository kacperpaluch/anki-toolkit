# LLM Context — Anki Toolkit: Integrations

Łączy Word Queue (n8n DataTable, panel i fallback Tailscale) z Web Bridge
(lokalny endpoint dla userscriptu). `word_queue.py` i `panel.py` obsługują
kolejkę; `bridge.py` endpoint, a `dictionaries-to-anki.user.js` jest jednym
źródłem przycisków dla przeglądarki i panelu. Nie rozdzielaj userscriptu na
dwie wersje.

Operacje HTTP n8n działają w tle, a kolekcja/edytor tylko na głównym wątku.
Bridge nasłuchuje wyłącznie na `127.0.0.1`; handler HTTP przekazuje zmianę do
głównego wątku i zachowuje protokół `{"fields": {...}}`. Panel odhacza wiersz
po `id`, a fallback bez panelu może odhaczyć go po słowie. Nie ma automatycznej
migracji konfiguracji: prywatne ustawienia przenosi się jednorazowo poza kodem.

- Bridge przechwytuje sesję edytora przez `editor_did_load_note`. Zmiana wymaga
  `saveNow`, żywego celu i niewygasłego żądania; timeout obejmuje także callback zapisu.
- Panel blokuje równoległe PATCH-e tego samego ID. Wspólna `_set_row` obsługuje
  checkbox i dodanie notatki; sukces wymaga dokładnie jednego trafienia.
- Starsze GET-y nie zastępują nowej listy ani wyniku PATCH-a. Przebudowa listy
  zachowuje wybrane ID i unieważnia stare callbacki wypełniania edytora.
- Automatyczne odhaczenie wymaga powiązanej notatki, ID i zgodnego hasła;
  zmienioną formę hasła użytkownik zatwierdza przez „Zrobione →”.
- Zapamiętany host musi należeć do adresów przekazanej konfiguracji.
- `ai_senses.py` bierze tekst już otwartych zakładek panelu, nie scrapuje stron
  ponownie. Cytaty modelu (`en`, `example`) są weryfikowane substringiem wobec
  tekstu strony — nie usuwaj tej kontroli, to jedyna bariera przed zmyśloną
  definicją. Znaczenie bez definicji zostaje kartą EN-PL; `ai_tag` idzie na każdą
  kartę z AI, `ai_review_tag` tylko na niepewne dopasowania.
- Dostawcę AI importujemy z dodatku Content przez `importlib` (folder z AnkiWeb
  bywa numerem). Integrations nie ma własnego klienta AI i nie powinno go dostać.
- Notatki z `ai_senses.add_notes` powstają poza oknem „Dodaj", więc hook
  `add_cards_did_add_note` nie leci — wiersz n8n odhacza panel wprost.
