# LLM Context — Integrations

Łączy Word Queue (n8n DataTable, panel, adres zapasowy i Cloudflare Access) z Web Bridge
(lokalny endpoint dla userscriptu). `word_queue.py` (HTTP n8n, konfiguracja,
`find_word_notes`, pozycja menu „Toolkit ▾” przełączająca panel 📚) i `panel.py` (Qt)
obsługują kolejkę; `bridge.py` — endpoint; `queue_state.py` — dług odhaczeń;
`settings.py` — panel „Kolejka słówek” (pola notatki, port); `__init__.py` tylko
rejestruje hooki. `dictionaries-to-anki.user.js` jest jednym źródłem przycisków
dla przeglądarki i panelu. Nie rozdzielaj userscriptu na dwie wersje.

„Utwórz karty z AI” (`ai_senses.py`, okno wyboru znaczeń, drafty, ptaszki wyboru
na liście, `window.ankiDictionaryEntries`) usunięto; kod jest w tagu `archive/ai-senses`.
Klucz `ai_fields` został, bo mapuje role mostka na pola.

Operacje HTTP n8n działają w tle, a kolekcja/edytor tylko na głównym wątku.
Bridge nasłuchuje wyłącznie na `127.0.0.1`; handler HTTP przekazuje zmianę do
głównego wątku i zachowuje protokół `{"fields": {...}}`. Panel odhacza wiersz
po `id`, a fallback bez panelu może odhaczyć go po słowie.

## Mostek

- Bridge przechwytuje sesję edytora przez `editor_did_load_note`. Zmiana wymaga
  `saveNow`, żywego celu i niewygasłego żądania; timeout obejmuje także callback zapisu.
- Port bierze się z `web_bridge.port` (domyślnie 8767) i musi zgadzać się ze stałą
  `ENDPOINT` w userscripcie z przeglądarki. Kopia wstrzykiwana do panelu dostaje
  bieżący port w `_dict_profile()` (podmiana stałej w źródle), więc plik zostaje jeden.
  Nie wracaj na 8765/8766 — tam siedzi AnkiConnect i jego forki, a zajęty port
  kończy się cichym brakiem mostka. Dlatego nieudany bind woła `showWarning`.
- Userscript wysyła role (`headword`, `meaning`, `definition`, `example`);
  `bridge._resolve` zamienia je na pola z `word_queue` (`word_field`, `ai_fields`)
  na głównym wątku. Nazwy pól nie wracają do userscriptu — jedno źródło to konfiguracja.
- Wartości są tekstem i są escapowane przed wpisaniem do pola; surowy HTML tylko
  z `"html": true`. Separator zawsze jest HTML-em.
- `_origin_allowed` wpuszcza własny origin po porcie z `_bound_port`, nie po
  samym hoście. Nie rozluźniaj tego do `hostname == "127.0.0.1"`.

## Lista i n8n

- Stan „zrobione" z n8n to `_marked` i szary kolor pozycji. Lista nie ma checkboxów
  i ma pojedyncze zaznaczenie.
- Panel blokuje równoległe PATCH-e tego samego ID. `_set_row` to JEDYNE wejście
  do flagi w n8n (przycisk „Oznacz jako zrobione", hook po dodaniu notatki, menu
  kontekstowe, `_settle_owed`); sukces wymaga dokładnie jednego trafienia.
- Starsze GET-y nie zastępują nowej listy ani wyniku PATCH-a. Przebudowa listy
  zachowuje wybrane ID i unieważnia stare callbacki wypełniania edytora.
- Automatyczne odhaczenie wymaga powiązanej notatki, ID i zgodnego hasła;
  zmienioną formę hasła użytkownik zatwierdza przez „Oznacz jako zrobione”.
- `_on_item_changed` odkłada `_apply_selection` o obrót pętli: odmowa zastąpienia
  hasła cofa bieżącą pozycję, czego nie robi się z wnętrza sygnału.
- Zapamiętany host musi należeć do adresów przekazanej konfiguracji.
- Nagłówki `CF-Access-Client-*` dokleja wyłącznie `_headers(cfg, url)` i tylko dla
  `https://` z kompletem id+secret — sekret nie może iść otwartym tekstem do
  hosta w LAN. Wszystkie odpowiedzi n8n przechodzą przez `_json()`, które stronę
  HTML (logowanie Access po przekierowaniu) zamienia na czytelny błąd tokenu.
- `common.http` dokłada domyślny User-Agent także dla `post_json`;
  bez tego POST/PATCH do n8n mogą dostać Cloudflare 1010.
- Dopisane hasła idą do tabeli (`add_rows`) i dostają prawdziwe `id`. Duplikaty
  odsiewa panel po zawartości listy (ma całą tabelę) plus `_adding` (hasła w locie).
  Nieudany zapis oddaje hasła do pola wpisywania — nie ma trybu offline ani
  wierszy lokalnych (nie przywracaj ujemnych `id`).
- `_added` trzyma wiersze zapisane w n8n, dopóki nie zobaczy ich odświeżenie:
  GET rozpoczęty przed POST-em nie może ich usunąć z listy.
- `add_rows`: wybór hosta przez GET, jeden POST bez retry/failover zapisu.
  Niepewny wynik sprawdzamy pełnym GET; brak pewności to błąd. HTTP 403 to
  odrzucenie, bez ponowienia ani readbacku. Przekroczenie `max_rows` to błąd.
- Wyszukiwarka `_search` współdzieli `_apply_hiding` z filtrem `_status_filter`
  (Wszystkie / Niezrobione / Zrobione, domyślnie Niezrobione).
- Duplikat w kolekcji = samo słowo w `word_field` (`word_queue.find_word_notes`),
  także wariant z encjami (`&amp;`, `&#x27;`/`&quot;`).

## Dług odhaczeń (`queue_state.py`)

Mały plik JSON w `user_files/`, zapisywany atomowo, tylko na głównym wątku.
Zakres = ścieżka kolekcji + adres główny + tabela + kolumny; bez sekretów.
Uszkodzony plik jest przemianowywany na `.broken` i panel startuje z pustym
stanem — nie może blokować okna „Dodaj". Stare klucze (np. `drafts`) są ignorowane.

- `owed` (id wiersza → hasło): notatka jest, PATCH „zrobione" jeszcze nie przeszedł.
  `note_added` zapisuje dług przed PATCH-em, sukces go usuwa. Po każdym
  odświeżeniu `_settle_owed` sprawdza kolekcję: są karty → ponów PATCH; brak
  kart → zapomnij dług; wiersza nie ma w n8n → zapomnij bez PATCH-a.
- Undo NIE jest śledzone (świadomie, `ponytail:` w `queue_state.py`).

## Zakładki słowników

- Zakładki biorą się z `link_templates` (etykieta → szablon adresu z `{q}`/`{slug}`),
  a nie z kolumn n8n. `link_columns` to tylko nadpisanie gotowym URL-em z wiersza;
  etykieta bez szablonu nie dostaje zakładki.
- Wybór słowa ładuje tylko widoczną zakładkę; reszta czeka w `_pending` na
  `currentChanged`. Ładowanie wszystkich naraz służyło usuniętemu AI — nie przywracaj
  (4× więcej zapytań i pamięci, częstsza weryfikacja Cloudflare).
- Na diki „→ hasło" stoi przy KAŻDYM `.hws .hw` (wpis bywa listą nagłówków:
  nazwa łacińska, potem „także:"); na Cambridge jeden na wpis
  (`.di-title.dhw, .hw.dhw`). „→ oba" bierze nagłówek równy `?q=`, inaczej pierwszy.
  Pole hasła dostaje zawsze JEDEN nagłówek.
- Kanarek `tests/live_selectors.py` (sieć) prowadzi prawdziwe `_DictTabs` z `page_js`
  na żywych stronach i sprawdza wczytanie oraz przyciski. Uruchamiaj po aktualizacji
  Anki, na jego Qt.

### Znikający podgląd słowników (rozwiązane 2026-10-01)

- Przyczyna: QtWebEngine 6.11.2 nie rejestruje kodeków ICU. Każde kodowanie poza
  UTF-8/16, windows-1252, GBK/gb18030, japońskimi, EUC-KR i ISO-8859-8-I kończy się
  `CHECK` w `NewTextCodec` i SIGTRAP renderera. Odtworzenie:
  `new TextDecoder('windows-1250').decode(new Uint8Array([65]))`. Qt 6.8/6.9 działa.
- Wyzwalaczem są skrypty reklam na Cambridge, Oxfordzie i LDoCE. Diki nie padło.
- Naprawa: `page_js` — skrypty strony (MainWorld) są włączone tylko na zakładkach
  z tej listy (domyślnie diki). Userscript działa w ApplicationWorld (`_WORLD`),
  więc przyciski i mostek działają też przy wyłączonym JS strony. Nie przenoś
  userscriptu z powrotem do MainWorld.
- Nie zastępuj tego blokadą żądań reklam: Ad-Shield (`html-load.com`) po zablokowaniu
  skryptów czyści stronę i przekierowuje na `report.error-report.com`. Sprawdzone, odrzucone.
- `_renderer_died` loguje awarię, pokazuje komunikat zamiast szarego widoku
  i odkłada URL do `_pending` (ponowne wejście w zakładkę wczytuje stronę).
- Weryfikacja Cloudflare (Cambridge) bez JS stoi w miejscu. `_after_load` sprawdza
  stronę w `_WORLD` (`_CHALLENGE_JS`: `_cf_chl_opt` / `challenge-platform`) i tylko
  dla zakładek spoza `page_js` włącza JS na czas weryfikacji (`_challenged`), po
  niej wyłącza go i przeładowuje stronę. Jedna próba na adres bez query (`_passed`),
  kasowana po czystym wczytaniu — bez pętli, gdy ciasteczko nie wystarcza. Nowe
  hasło (`_start_load`) i padnięty renderer zawsze wracają do JS wyłączonego.
- Gdy Anki dostanie poprawione Qt, wystarczy dopisać etykiety do `page_js`.
- Wyjątek `SidebarTreeView has been deleted` pochodzi z Advanced Browser
  (`1334324384`), nie z tego modułu; użytkownik polecił go pominąć.
