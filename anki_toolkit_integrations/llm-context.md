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
- Ptaszek = `_picked`, czyli wybór do AI, wyłącznie w pamięci panelu. Stan
  „zrobione" z n8n to `_marked` i kolor pozycji — dwie różne rzeczy na jednej
  liście, nie sklejaj ich z powrotem. Oba stany rysuje `_style_item` czytając
  `self`, a nie argumenty — inaczej rozjeżdżają się między ścieżkami wywołań.
  Wybór niesie TEKST pozycji („☑ hasło"), nie tylko wskaźnik checkboxa: ten
  rysuje motyw Anki i bywa niewidoczny. Dlatego `_make_item` tworzy pozycję bez
  etykiety — jedynym miejscem, które ją ustawia, jest `_style_item`. Ptaszki przeżywają przebudowę listy
  (po to są), ale `_rebuild` przycina je do istniejących wierszy, a zapis kart
  je zdejmuje, żeby hasło nie poszło do modelu drugi raz.
- Panel blokuje równoległe PATCH-e tego samego ID. `_set_row` to JEDYNE wejście
  do flagi w n8n (przycisk „Zrobione →", hook po dodaniu notatki, zapis kart z AI,
  menu kontekstowe); sukces wymaga dokładnie jednego trafienia.
- Starsze GET-y nie zastępują nowej listy ani wyniku PATCH-a. Przebudowa listy
  zachowuje wybrane ID i unieważnia stare callbacki wypełniania edytora.
- Automatyczne odhaczenie wymaga powiązanej notatki, ID i zgodnego hasła;
  zmienioną formę hasła użytkownik zatwierdza przez „Zrobione →”.
- Zapamiętany host musi należeć do adresów przekazanej konfiguracji.
- Zakładki biorą się z `link_templates` (etykieta → szablon adresu z `{q}`/`{slug}`),
  a nie z kolumn n8n. `link_columns` to tylko nadpisanie gotowym URL-em z wiersza;
  etykieta bez szablonu nie dostaje zakładki. Nowy słownik = jeden wpis w configu,
  bez zmian w DataTable.
- Role zakładek są w konfiguracji, nie w kodzie: `ai_pl_sources` i `ai_en_sources`.
  Cambridge EN-PL jest na obu listach — nie zakładaj, że źródło PL i EN to
  rozłączne zbiory, i nie wracaj do zaszytego `"diki"`. Etykiety muszą się zgadzać
  z `link_templates`; `generate` sprawdza to z góry, bo inaczej pusty worek PL
  odrzuca wszystkie znaczenia bez wskazania przyczyny.
- `ai_senses.py` bierze tekst już otwartych zakładek panelu, nie scrapuje stron
  ponownie. Cytaty modelu (`en`, `example`) są weryfikowane substringiem wobec
  wskazanego źródła z `ai_en_sources`, a polskie odpowiedniki wobec sumy tekstów
  z `ai_pl_sources` (tekst przycięty jak w prompcie) — nie usuwaj tej kontroli,
  to jedyna bariera przed zmyśloną definicją. Znaczenie bez definicji zostaje kartą EN-PL. Tagi są rozłączne:
  `ai_tag` wyłącznie dla `match == "exact"`, `ai_review_tag` dla całej reszty.
  Nie dokładaj `ai_tag` do wszystkich — filtr `tag:ai-review` ma być kompletną
  listą do weryfikacji, a nie podzbiorem.
- Dostawcę AI importujemy z dodatku Content przez `importlib` (folder z AnkiWeb
  bywa numerem). Integrations nie ma własnego klienta AI i nie powinno go dostać.
  Kandydata wybiera `_has_providers` po PLIKU `ai_generator/providers.py`, nigdy
  przez próbny import: `import_module("<dodatek>.ai_generator.providers")`
  wykonuje `__init__.py` przeglądanego dodatku, a to uruchamiało obcy kod
  startowy (AnkiConnect startował serwer i otwierał QMessageBox z wątku
  roboczego — natywne przerwanie Anki). `prepare_provider` należy do głównego
  wątku; w tle zostaje samo `generate`. Z Contentu bierzemy klucze i listę
  dostawców, NIE jego modele per pole notatki — Integrations ma jeden własny
  wybór (`ai_provider`/`ai_model`), a `provider_label` pokazuje go w oknie wyboru.
- Notatki z `ai_senses.add_notes` powstają poza oknem „Dodaj", więc hook
  `add_cards_did_add_note` nie leci — wiersz n8n odhacza panel wprost.

- AI działa na PACZCE zaznaczonych wierszy: `SensePicker` i `add_notes` biorą
  listę haseł, nie jedno. Nie cofaj tego do jednego hasła — okno na hasło przy
  wklejonej liście to tyle klików, ile haseł.
- `_DictTabs._collect` oddaje tekst stron przez `QTimer.singleShot(0, …)`, nigdy
  wprost. `toPlainText` woła nas ze środka QtWebEngine, a paczka w tym callbacku
  ładuje kolejne hasło i potrafi otworzyć modalne okno — to natywny crash Anki,
  nie wyjątek Pythona. Nie „upraszczaj" tego z powrotem do bezpośredniego wywołania.
- Paczka jest SEKWENCYJNA: jedno hasło naraz, następne rusza po wyniku
  poprzedniego. Nie wprowadzaj z powrotem nakładania kroków — zakładki i tak są
  jedne, więc zysk jest żaden, a liczników stanu do skoordynowania od razu kilka.
  `_busy` wstrzymuje wszystko, co przebudowuje listę (odświeżanie, kolejność,
  dopisywanie haseł); wynik wiąże się z wierszem po `row_id`, nie po zaznaczeniu.
  Przerwana paczka woła `_unfreeze` — inaczej panel zostaje wyłączony na zawsze.
- Cel zapisu sprawdzamy PO zamknięciu okna wyboru, nie przed: dialog bywa otwarty
  długo, a tożsamość kolekcji i żywe okno „Dodaj” to warunek, żeby zapis poszedł
  tam, gdzie użytkownik go widział.
- Błąd jednego hasła nie przerywa paczki: wypada z wyników i ląduje w dymku.
- Zapis AI: przygotowanie całej paczki, jedno `col.add_notes` na głównym
  wątku; zwrócone OpChanges trafiają do `on_op_finished`. Pola tekstowe są
  escapowane jako HTML. `exact` to ocena modelu, nie walidacja semantyczna.

- SensePicker edytuje kopie propozycji; ręczna zmiana ustawia approx/none,
  wymaga niepustego PL. Linki HTTP(S) pochodzą z adresów zakładek (wiersz n8n
  albo szablon), nigdy z odpowiedzi modelu. Ręczna treść nie przechodzi walidacji
  cytatów. `existing_senses` tylko OSTRZEGA o istniejących kartach z tym hasłem —
  kilka znaczeń jednego hasła jest zamierzone, więc nie rób z tego blokady.
- Dopisane hasła idą do tabeli (`add_rows`) i dostają prawdziwe `id`. Duplikaty
  odsiewa panel po zawartości listy — ma całą tabelę, więc osobne zapytanie
  „czy już jest" byłoby zbędnym żądaniem. Do porównania wchodzi też `_adding`
  (hasła w locie): przed odpowiedzią n8n nie ma ich na liście, a bez tego drugie
  wklejenie zapisałoby duplikat. Zapasowe ujemne `id` wydaje licznik
  `_next_local_id`, nigdy `min(_local_rows)` — inaczej równoległe zapisy dostają
  ten sam numer. Nieudany zapis degraduje się do wiersza lokalnego, nie do
  wyjątku: hasło ma dać się przerobić także offline.
- Wiersz lokalny (fallback) to zwykły wiersz listy z UJEMNYM `id` (`_local_rows`).
  Cała reszta panelu nie musi o nim wiedzieć — jedyny guard siedzi w `_set_row`
  i zamiast PATCH-a domyka tę samą ścieżkę `finished` gotowym wynikiem. Nie
  dokładaj drugiego trybu pracy panelu ani pola „to jest lokalne": znak `id`
  wystarcza, a `refill` musi te wiersze i ich ptaszki przenieść sam, bo n8n
  ich nie odtworzy.

- `_origin_allowed` wpuszcza własny origin po porcie z `_bound_port`, nie po
  samym hoście. Nie rozluźniaj tego do `hostname == "127.0.0.1"`.

