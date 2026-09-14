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
- Port bierze się z `web_bridge.port` (domyślnie 8767) i musi zgadzać się ze stałą
  `ENDPOINT` w userscripcie. Nie wracaj na 8765/8766 — tam siedzi AnkiConnect
  i jego forki (np. „Agent Connect"), a zajęty port kończy się cichym brakiem
  mostka. Dlatego nieudany bind woła `showWarning`, nie tylko `logger`.
- Panel blokuje równoległe PATCH-e tego samego ID. Wspólna `_set_row` obsługuje
  checkbox i dodanie notatki; sukces wymaga dokładnie jednego trafienia.
- Starsze GET-y nie zastępują nowej listy ani wyniku PATCH-a. Przebudowa listy
  zachowuje wybrane ID i unieważnia stare callbacki wypełniania edytora.
- Automatyczne odhaczenie wymaga powiązanej notatki, ID i zgodnego hasła;
  zmienioną formę hasła użytkownik zatwierdza przez „Zrobione →”.
- Zapamiętany host musi należeć do adresów przekazanej konfiguracji.
- `ai_senses.py` bierze tekst już otwartych zakładek panelu, nie scrapuje stron
  ponownie. Cytaty modelu (`en`, `example`) są weryfikowane substringiem wobec
  wskazanego źródła EN, a polskie odpowiedniki wobec diki (tekst przycięty jak w prompcie) — nie usuwaj tej kontroli, to jedyna bariera przed zmyśloną
  definicją. Znaczenie bez definicji zostaje kartą EN-PL. Tagi są rozłączne:
  `ai_tag` wyłącznie dla `match == "exact"`, `ai_review_tag` dla całej reszty.
  Nie dokładaj `ai_tag` do wszystkich — filtr `tag:ai-review` ma być kompletną
  listą do weryfikacji, a nie podzbiorem.
- Dostawcę AI importujemy z dodatku Content przez `importlib` (folder z AnkiWeb
  bywa numerem). Integrations nie ma własnego klienta AI i nie powinno go dostać.
- Notatki z `ai_senses.add_notes` powstają poza oknem „Dodaj", więc hook
  `add_cards_did_add_note` nie leci — wiersz n8n odhacza panel wprost.

- AI przechwytuje generację zaznaczenia, ID wiersza, kolekcję i notatkę;
  nieaktualne callbacki nie pokazują propozycji ani nie zapisują kart.
- Zapis AI: przygotowanie całej paczki, jedno `col.add_notes` na głównym
  wątku; zwrócone OpChanges trafiają do `on_op_finished`. Pola tekstowe są
  escapowane jako HTML. `exact` to ocena modelu, nie walidacja semantyczna.

- SensePicker edytuje kopie propozycji; ręczna zmiana ustawia approx/none,
  wymaga niepustego PL. Linki HTTP(S) pochodzą z przechwyconego wiersza n8n,
  nigdy z odpowiedzi modelu. Ręczna treść nie przechodzi walidacji cytatów.

- `local_dict.py` jest bez aqt: konwerter StarDict→SQLite (CLI), lookup, rozbicie
  artykułu i render strony. Dzięki temu testuje się bez Anki i da się uruchomić
  jako skrypt. Nie wciągaj tam Qt — od okna jest `reader.py`.
- Baza: `defs` (definicja per offset bloku .dict) + `words` (hasła i aliasy .syn
  wskazujące na `defs`). Aliasów jest więcej niż haseł, więc definicji NIE
  duplikujemy per alias — inaczej baza puchnie z ~46 MB do ~276 MB.
- `parse()` jest dostrojony do słownika z .mobi (`<b>N.</b>`, `<b><i>pos</i></b>`,
  `<blockquote>`). Nierozpoznany artykuł ma wracać jako jeden blok, nie wyjątek.
- `text` (na kartę) i `html` (na ekran) to różne rzeczy: z `text` lecą
  kwalifikatory, przykłady po ➤ i odsyłacze. Nie zlewaj ich w jedno.
- `word` z query trafia na stronę tylko przez `html.escape` — ta strona potrafi
  pisać do notatki, więc odbite `<script>` byłoby realną dziurą.
- Czytnik nie może zależeć od kolejki n8n: okno z `reader.py` i przycisk 📖
  działają bez konfiguracji n8n. Zakładka w panelu to dodatek, nie wejście główne.
- Zakładka czytnika jest wyłączona ze zbierania tekstu dla AI (`_DictTabs.no_text`)
  — prompt dopasowuje diki do Oxforda, polski artykuł to tam szum.
- `_origin_allowed` wpuszcza własny origin po porcie z `_bound_port`, nie po
  samym hoście. Nie rozluźniaj tego do `hostname == "127.0.0.1"`.

