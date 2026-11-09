# Kolejka słówek (`integrations/`)

Panel 📚 przy oknie **Dodaj**: kolejka słówek z n8n DataTable, cztery słowniki
w zakładkach i lokalny Web Bridge, przez który przyciski na stronach słowników
wpisują dane do otwartej notatki.

Panel otwierasz z **Toolkit ▾ → 📚 Kolejka słówek (pokaż/ukryj)** w oknie **Dodaj** albo
przez **Narzędzia → Anki Toolkit → Kolejka słówek (n8n)…**. Pola notatki i port
ustawiasz w **Ustawienia… → Kolejka słówek**, a połączenie z n8n i Cloudflare
Access w **Ustawienia… → Konta i klucze**.

Przycisk **Utwórz karty z AI** został usunięty w 2026-11 (karty i tak są
weryfikowane ręcznie). Jego kod jest w tagu Git `archive/ai-senses`.

## Lista słówek

Panel pobiera **całą** tabelę. Szare pozycje to słowa zrobione (flaga w n8n).
Filtr **Wszystkie / Niezrobione / Zrobione** (domyślnie Niezrobione) chowa
pozycje, ale ich nie usuwa. **Szukaj w kolejce…** filtruje po fragmencie hasła
bez rozróżniania wielkości liter. Gdy tabela przekroczy `max_rows` (domyślnie 5000),
dostajesz błąd zamiast niepełnej listy.

Kliknięcie słowa wpisuje je do pola angielskiego i ładuje słowniki. Gdy notatka
ma już inne wypełnione pola, panel najpierw pyta o zgodę.

- **Oznacz jako zrobione** odhacza słowo w n8n i przechodzi do następnego (skrót **D**).
- **Pomiń** przechodzi dalej bez odhaczania (skrót **S**).
- Prawy klik na pozycji: *Oznacz jako zrobione* / *Cofnij odhaczenie*.

Skróty działają, gdy lista ma fokus. Ctrl+Enter zostaje skrótem „Dodaj”.

Po dodaniu notatki wiersz jest odhaczany sam, ale panel **zostaje na słowie**,
bo jedno hasło często daje kilka kart. Odhaczenie wymaga, żeby pole angielskie
nadal zawierało to hasło. Jeśli zmienisz formę (np. „sprawling” → „sprawl”),
użyj **Oznacz jako zrobione**. Gdy odhaczenie w n8n się nie uda, panel
zapamiętuje je w `user_files/` i ponawia po następnym **Odśwież**.

Bez otwartego panelu dodanie notatki też odhacza wiersz, ale tylko gdy treść
pola dokładnie pasuje do hasła w tabeli.

**Kolejność:** **Od początku**, **Najnowsze** (dzisiejsza wklejka na górze) albo
**Losowo**. Sortowanie idzie po `id` wiersza. Wybór przeżywa restart.

## Własne hasła

Wpisz hasło w polu **Dodaj słowo** i naciśnij Enter (kilka rozdziel przecinkiem)
albo użyj **Wklej listę…** (po jednym na linię). Hasła trafiają do tabeli n8n
jako zwykłe wiersze. Hasło, które już jest na liście, jest pomijane. Gdy n8n
nie przyjmie zapisu, hasła wracają do pola. Jeśli wynik zapisu jest niepewny
(np. zerwane połączenie), kliknij **Odśwież** przed ponowieniem.

## Adres n8n i Cloudflare Access

Podajesz adres główny (np. domenę za Cloudflare) i opcjonalnie zapasowy (np. IP
w sieci domowej). Panel najpierw próbuje hosta, który ostatnio odpowiedział.

Gdy n8n stoi za Cloudflare Access:

1. W Zero Trust utwórz *service token*.
2. W aplikacji Access dodaj regułę z akcją **Service Auth** (zwykłe „Allow” przekierowuje na logowanie).
3. Client ID i Secret wpisz w **Konta i klucze**. Są wysyłane tylko na adresy `https`.
4. Przy włączonym Bot Fight Mode dodaj wyjątek dla `/api/v1/data-tables/`.

Klucz API n8n nadal jest wymagany. Po zmianie ustawień zamknij okno „Dodaj”
i otwórz panel ponownie.

## Słowniki w zakładkach

| Zakładka | Rola | Adres |
|---|---|---|
| diki | PL | `diki.pl/slownik-angielskiego?q=…` |
| Cambridge EN-PL | PL + EN | `dictionary.cambridge.org/pl/dictionary/english-polish/…` |
| Oxford | EN | `oxfordlearnersdictionaries.com/definition/english/…` |
| LDoCE | EN | `ldoceonline.com/dictionary/…` |

Adresy powstają z samego hasła (`link_templates`), więc kolumny z URL-ami
w tabeli nie są potrzebne. `link_columns` to tylko nadpisanie: niepusty URL
z wiersza wygrywa. Wybór słowa ładuje od razu wszystkie zakładki
(Chromium bierze ~100 MB na zakładkę).

Na stronach działają przyciski userscriptu. Na diki **→ hasło** stoi przy każdym
nagłówku wpisu, a **→ oba** bierze nagłówek, którego szukałeś.

**Skrypty samej strony działają tylko na zakładkach z `page_js`** (domyślnie
`["diki"]`). QtWebEngine 6.11.2 (Anki 26.09) wywraca stronę na skryptach reklam
w starym kodowaniu znaków, więc Cambridge, Oxford i LDoCE znikały po chwili.
Bez skryptów strony nie działają odsłuch i rozwijane sekcje, ale przyciski
userscriptu działają. Zakładka, której proces padł, mówi o tym wprost
i wczytuje się ponownie po powrocie na nią.

## Web Bridge i userscript

Mostek słucha na `127.0.0.1:8767` (klucz `web_bridge.port`, zmiana działa po
restarcie Anki). Ten sam port musi być w stałej `ENDPOINT` pliku
`dictionaries-to-anki.user.js`, jeśli używasz go też w przeglądarce
(Tampermonkey). Porty 8765 i 8766 zajmuje AnkiConnect i jego forki. Gdy port
jest zajęty, Anki pokazuje ostrzeżenie.

Przyciski wysyłają **role** (`headword`, `meaning`, `definition`, `example`),
a mostek zamienia je na pola z **Ustawienia → Kolejka słówek**. Nazwy pól
zmieniasz więc tylko w ustawieniach. Wartości trafiają do pola jako zwykły
tekst. Okno „Dodaj” musi być otwarte. Po aktualizacji dodatku wgraj userscript
ponownie w menedżerze userscriptów.

## Konfiguracja

Sekcja `word_queue`:

- połączenie: `n8n_url`, `fallback_url`, `api_key`, `cf_client_id`, `cf_client_secret`, `table_id`,
- kolumny: `word_column`, `flag_column`,
- pola: `word_field` i `ai_fields` (`pl`, `definition`, `example` — nazwa klucza została po dawnym AI),
- zakładki: `link_templates`, `link_columns`, `page_js`,
- lista: `order`, `page_size`, `max_rows`.

Sekcja `web_bridge` trzyma `port`. `link_templates`, `link_columns`, `page_js`,
`page_size` i `max_rows` nie mają pól w oknie ustawień: zmienisz je w `meta.json`
przy zamkniętym Anki. Klucze trafiają do `meta.json`, które nie jest wersjonowane.
Stare klucze `ai_*` w `meta.json` są ignorowane.
