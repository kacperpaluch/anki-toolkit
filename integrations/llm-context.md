# LLM Context — Integrations

Łączy Word Queue (n8n DataTable, panel, adres zapasowy i Cloudflare Access) z Web Bridge
(lokalny endpoint dla userscriptu). `word_queue.py` (HTTP n8n, konfiguracja,
przycisk 📚) i `panel.py` (Qt) obsługują kolejkę; `ai_senses.py` — „AI:
znaczenia” (numerowane dopasowanie definicji, okno wyboru, zapis notatek); `bridge.py`
endpoint; `settings.py` — panel „Kolejka słówek” we wspólnym oknie ustawień;
`__init__.py` tylko rejestruje hooki. `dictionaries-to-anki.user.js` jest jednym
źródłem przycisków dla przeglądarki i panelu. Nie rozdzielaj userscriptu na
dwie wersje.

Operacje HTTP n8n działają w tle, a kolekcja/edytor tylko na głównym wątku.
Bridge nasłuchuje wyłącznie na `127.0.0.1`; handler HTTP przekazuje zmianę do
głównego wątku i zachowuje protokół `{"fields": {...}}`. Panel odhacza wiersz
po `id`, a fallback bez panelu może odhaczyć go po słowie.

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
  do flagi w n8n (przycisk „Oznacz jako zrobione", hook po dodaniu notatki, zapis kart z AI,
  menu kontekstowe); sukces wymaga dokładnie jednego trafienia.
- Starsze GET-y nie zastępują nowej listy ani wyniku PATCH-a. Przebudowa listy
  zachowuje wybrane ID i unieważnia stare callbacki wypełniania edytora.
- Automatyczne odhaczenie wymaga powiązanej notatki, ID i zgodnego hasła;
  zmienioną formę hasła użytkownik zatwierdza przez „Oznacz jako zrobione”.
- Zapamiętany host musi należeć do adresów przekazanej konfiguracji.
- Nagłówki `CF-Access-Client-*` dokleja wyłącznie `_headers(cfg, url)` i tylko dla
  `https://` z kompletem id+secret — sekret nie może iść otwartym tekstem do
  hosta w LAN. Wszystkie odpowiedzi n8n przechodzą przez `_json()`, które stronę
  HTML (logowanie Access po przekierowaniu) zamienia na czytelny błąd tokenu.
- Zakładki biorą się z `link_templates` (etykieta → szablon adresu z `{q}`/`{slug}`),
  a nie z kolumn n8n. `link_columns` to tylko nadpisanie gotowym URL-em z wiersza;
  etykieta bez szablonu nie dostaje zakładki. Nowy słownik = jeden wpis w configu,
  bez zmian w DataTable.
- „AI: znaczenia”: userscript (`window.ankiDictionaryEntries(word)`, ten sam plik co
  przyciski) zwraca pozycje wpisu o pasującym nagłówku. Rolę wyznacza KSZTAŁT, nie
  konfiguracja: `{pl}` bez `def` = znaczenie (diki, jednostka karty), `{def, pl?}` =
  definicja (Cambridge ma też PL). `split_entries` odsiewa powtórki po tekście + `pos` + `labels` osobno dla D/E;
  różne niepuste PL przy tym samym E pozostają oddzielne. Duplikat E uzupełnia
  brakujące PL i `pl_src`, zachowując pierwsze `src` definicji. Fallback bez D
  korzysta z `pl_src` tłumaczenia, które może różnić się od źródła definicji.
  `build_prompt` serializuje hasło, D/E i metadane jako JSON (bez interpolowania
  tekstu stron w linie instrukcji). Prompt opisuje zgodność sensu zamiast równej
  szczegółowości; PL, część mowy i kwalifikatory są dowodami, nie regułą zgadywania.
  Model zwraca TYLKO pełną mapę D → tekstowy identyfikator E albo null.
  `parse_mapping` zwraca None przy brakujących/dodatkowych/powtórzonych kluczach,
  złym typie lub numerze spoza listy. `_json_object` parsuje cały tekst (może zdjąć
  otoczkę ```json); nie wycina obiektu z komentarza i nie toleruje duplikatów kluczy.
  Tylko jawne null jest brakiem dopasowania; kompletna mapa samych null zwraca {}.
  Błędna mapa odrzuca całe hasło (`generate` → [], error), bez automatycznej próby
  naprawczej i bez tworzenia kart; paczka kontynuuje inne hasła. Nie przywracaj modelu piszącego tekst,
  walidacji cytatów ani trybu „cała strona” — treść karty ma być wyłącznie ze słownika.
  Bez znaczeń z diki kartami są pary Cambridge (bez modelu); bez definicji — samo PL
  (bez modelu). Znaczenia spoza diki są pomijane celowo.
  Brak reguły/CAPTCHA/zmieniony HTML = `[]`, czyli brak źródła. Kanarek:
  `tests/live_selectors.py` (sieć, kod wyjścia 1 = reguła nie pasuje).
  Porównanie nagłówka normalizuje spacje i łączniki ASCII/Unicode do spacji
  (`brother in law` = `brother-in-law`), bez zmiany URL ani treści karty.
  Nagłówek porównujemy bez `.stopword` (diki: give *something* up = give up).
  Wyjątek: pojedyncze słowo bez pasującego nagłówka (went → go) bierze PIERWSZY
  wpis strony; frazy nigdy (give up nie może spaść do give).
  Selektory sprawdzone na żywych stronach (09.2026): diki `:scope > .hw` (kontekst
  w nawiasie jest wewnątrz `.hw`), Cambridge `.dhw` + `.def-block` (`.def`,
  `.dtrans-se`), LDOCE `.PHRVBHWD`.
  Przycisk „→ hasło" na Cambridge: jeden na wpis (`.di-title.dhw, .hw.dhw`), bo
  strona frazy ma też goły `.hw.dhw` z samym czasownikiem („give" przy „give up").
  `_loaded`: None = w trakcie, False = błąd, True = zakończone poprawnie;
  sukces HTTP nie gwarantuje znalezienia hasła. Callbacki ekstrakcji mają generację
  i osobny limit 5 s: zawieszony renderer nie może zatrzymać paczki.
- Userscript 4.8 zwraca opcjonalne `pos`/`labels` obok `{pl}` lub `{def, pl?}`.
  Diki bierze POS z nagłówka poprzedzającego konkretną listę znaczeń (jedna entity
  może mieć rzeczownik i czasownik). Kwalifikatory są lokalne dla znaczenia;
  gramatyka nagłówka wpisu jest dodatkowym kontekstem w Cambridge/Oxford/LDoCE.
  Brak selektora zostawia metadata puste — nigdy nie zgadujemy z treści definicji.
  Metadane pomagają dopasowaniu, ale nie są nowymi polami karty ani rolami mostka.
  Stare wpisy `{pl}`/`{def, pl?}` i odzyskane drafty nadal działają. Zmiana promptu
  nie przelicza automatycznie istniejących draftów; odzyskiwanie nie pyta modelu.
  Regresje kontraktu: `tests/test_ai_senses.py`, `tests/test_queue_recovery.py`;
  DOM i lokalność metadanych: `tests/qt_integrations_smoke.py` (syntetyczne strony).
- `ai_tag` oznacza pochodzenie i trafia na wszystkie notatki z przycisku;
  `ai_review_tag` tylko przy `by_ai` (definicję przypisał model), chyba że
  użytkownik potwierdził `reviewed`. Każda edycja cofa potwierdzenie; zmiana
  definicji zdejmuje `by_ai`. Propozycje bez klucza `by_ai` (stare drafty) liczą
  się jak AI, gdy mają definicję (`_by_ai`).
- `add_notes` dopisuje każdej nowej notatce `ai-import::YYYY-MM-DD`.
  `date.today()` jest odczytane raz na głównym wątku przy przygotowaniu zapisu:
  lokalna data zapisu, nie generowania/draftu ani dzień Anki liczony od rollover.
  Tag obejmuje całą paczkę, również pary bez modelu i brak definicji. Nie zależy
  od `ai_tag`, `ai_review_tag` ani potwierdzenia; nie retaguje istniejących notatek.
  Nie ma nowego klucza configu ani stanu sesji; deduplikacja tagów pozostaje wspólna.
- AI wypełnia tylko `word_field`, `ai_fields.pl` i `ai_fields.definition`;
  `ai_fields.example` jest celem przycisków „+ przykład” (rola `example` w mostku).
- `validate_mapping` obsługuje ustawienia i zapis: wymagane EN/PL, różne pola,
  a przed transakcją sprawdzenie wszystkich skonfigurowanych pól w typie notatki.
- Dostawcę AI bierzemy z `..ai_generator.providers` (import leniwy w
  `_providers()`, bo testy logiki ładują `ai_senses.py` bez aqt). Integrations
  nie ma własnego klienta AI i nie powinno go dostać. `prepare_provider` należy
  do głównego wątku; w tle zostaje samo `generate`. Z sekcji `ai_generator`
  bierzemy klucze i listę dostawców, NIE modele per pole notatki — kolejka ma
  jeden własny wybór (`ai_provider`/`ai_model`/`ai_reasoning_effort`).
  `provider_label` pokazuje dostawcę i model w oknie wyboru.
- Panel ustawień pokazuje najpierw AI; pola/tagi/limit czasu, n8n, Cloudflare i Web Bridge są zwijane. Błąd mapowania otwiera sekcję pól. Panel kolejki rozdziela pasek źródeł od działań AI/oznaczania/pomijania.
- `ai_reasoning_effort`: opcjonalne nadpisanie effort dla CLI w kolejce. Puste/brak dziedziczy od dostawcy; `prepare_provider` zmienia tylko kopię konfiguracji. UI korzysta ze wspólnej listy `CLI_REASONING_EFFORTS` i resetuje nadpisanie po zmianie dostawcy. `SettingsDialog` podpina żywe ustawienia AI Generatora, aby etykieta dziedziczenia uwzględniała niezapisane zmiany poziomu.
- Notatki z `ai_senses.add_notes` powstają poza oknem „Dodaj", więc hook
  `add_cards_did_add_note` nie leci — wiersz n8n odhacza panel wprost.

- AI działa na PACZCE zaznaczonych wierszy: `SensePicker` i `add_notes` biorą
  listę haseł, nie jedno. Nie cofaj tego do jednego hasła — okno na hasło przy
  wklejonej liście to tyle klików, ile haseł.
- `_DictTabs._collect` oddaje pozycje ze stron przez `QTimer.singleShot(0, …)`, nigdy
  wprost. `runJavaScript` woła nas ze środka QtWebEngine, a paczka w tym callbacku
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
  escapowane jako HTML bez cudzysłowów (`quote=False`, jak edytor Anki), bo
  wyszukiwarka porównuje surowy HTML pola.

- SensePicker edytuje kopie propozycji i pokazuje wszystkie znaczenia, zaznaczając
  pierwsze `ai_max_senses`. Wymaga niepustego PL. Linki HTTP(S) pochodzą z adresów
  zakładek (wiersz n8n albo szablon) dla `pl_src` i `src`, nigdy z odpowiedzi modelu.
- Duplikat = samo słowo w `word_field` (`find_word_notes`), nigdy znaczenie.
  Szukamy też wariantu z encjami (`&amp;`, a dla starszych notatek `&#x27;`/`&quot;`).
  `_ai_senses` pomija słowa, które mają już karty, ZANIM zapyta model; błąd
  wyszukiwania przerywa paczkę. Nieodhaczone z nich odhacza dopiero po `askUser`
  (przez `_owe` + `_finish_rows`, jak po zapisie kart). `existing_senses` w podglądzie zostaje jako
  ostrzeżenie dla odzyskanych propozycji (karty mogły powstać w międzyczasie).
- Dopisane hasła idą do tabeli (`add_rows`) i dostają prawdziwe `id`. Duplikaty
  odsiewa panel po zawartości listy — ma całą tabelę, więc osobne zapytanie
  „czy już jest" byłoby zbędnym żądaniem przed każdą wklejką. Do porównania wchodzi też `_adding`
  (hasła w locie): przed odpowiedzią n8n nie ma ich na liście, a bez tego drugie
  wklejenie zapisałoby duplikat. Nieudany zapis oddaje hasła do pola „własne
  hasło” — panel zakłada działający n8n i nie ma trybu offline ani wierszy
  lokalnych (usunięte celowo; nie przywracaj ujemnych `id`).
- `_added` trzyma wiersze zapisane w n8n, dopóki nie zobaczy ich odświeżenie:
  GET rozpoczęty przed POST-em nie może ich usunąć z listy ani odblokować
  ponownego zapisu tego samego hasła.
- Userscript wysyła role (`headword`, `meaning`, `definition`, `example`);
  `bridge._resolve` zamienia je na pola z `word_queue` na głównym wątku. Nazwy
  pól nie wracają do userscriptu — jedno źródło to konfiguracja.
- Mostek i panel traktują wartości jako tekst i escapują je przed wpisaniem do
  pola; surowy HTML tylko z `"html": true`. Separator zawsze jest HTML-em.
- `_origin_allowed` wpuszcza własny origin po porcie z `_bound_port`, nie po
  samym hoście. Nie rozluźniaj tego do `hostname == "127.0.0.1"`.


## Odzyskiwanie

`queue_state.py` to mały plik JSON w `user_files/`, zapisywany atomowo.
Zakres = ścieżka kolekcji + adres główny + tabela + kolumny; nie zapisuje sekretów.
Panel używa go tylko na głównym wątku. Uszkodzony plik jest przemianowywany na
`.broken` i panel startuje z pustym stanem — nie może blokować okna „Dodaj".

- `add_rows`: wybór hosta przez GET, jeden POST bez retry/failover zapisu.
  Niepewny wynik sprawdzamy pełnym GET; brak pewności to błąd, a hasła wracają do pola.
  Przekroczenie `max_rows` to błąd, nie udane pobranie części tabeli.
- `drafts`: każdy ukończony wynik AI; stop kończy bieżące hasło, przycisk
  odzyskiwania otwiera propozycje bez modelu. Znikają po zapisie kart.
- `owed` (id wiersza → hasło): karty są, PATCH „zrobione" jeszcze nie przeszedł.
  Zapisywane PRZED `col.add_notes`, usuwane po udanym PATCH-u. Nieudany zapis
  długu przerywa dodawanie kart (propozycje zostają w `drafts`). Po każdym
  odświeżeniu `_settle_owed` sprawdza kolekcję (`find_word_notes`): są karty →
  ponów PATCH; brak kart (crash przed commitem) → zapomnij dług, zostaw draft.
- Undo NIE jest śledzone (świadomie, `ponytail:` w `queue_state.py`): cofnięcie
  paczki zostawia wiersz odhaczony w n8n — odznacza się go ręcznie.
- `_set_row` pozostaje jedynym wejściem do PATCH.

## Otwarty problem podglądu (2026-10-01)

- Środowisko zgłoszenia: Anki 26.09.3, Python 3.13.15, Qt 6.11.2,
  PyQt 6.11.0, macOS 27.0.1 ARM64. Diki pozostaje widoczne; Cambridge, Oxford
  i LDoCE pokazują się na chwilę, po czym widok jest pusty — według użytkownika
  dla wszystkich haseł. Przyczyna nie jest potwierdzona; nie uznawaj za naprawione.
- To osobny objaw od ekstrakcji `brother in law`: nierówne separatory nagłówka
  naprawiono w userscripcie 4.8. Na żywych stronach po poprawce odczytano
  1 znaczenie diki oraz 3/1/3 pozycje Cambridge/Oxford/LDoCE.
- Osobny proces QtWebEngine offscreen z `--disable-gpu` zachowywał DOM
  przez 25 s; przełączanie zakładek i zrzut widoku Cambridge pokazały stronę.
  Nie odtwarza to ustawień/renderowania uruchomionego Anki i nie dowodzi
  winy GPU. Sterownik Software zaproponowano jako test; brak wyniku od użytkownika.
- Dalsza diagnostyka: rzeczywiste URL-e po przekierowaniach, `loadFinished`,
  `renderProcessTerminated`, zawartość DOM w chwili pustego widoku i porównanie
  sterowników wideo. Nie zmieniono `panel.py` ani globalnych ustawień renderowania.
- Zgłoszony później wyjątek `SidebarTreeView has been deleted` pochodzi
  z Advanced Browser (`1334324384`), nie z tego modułu. Użytkownik polecił
  go pominąć i nie modyfikować innych dodatków; nic w nich nie zmieniono.
