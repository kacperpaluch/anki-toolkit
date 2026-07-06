# Web Bridge

Mostek HTTP **strona WWW → otwarte okno „Dodaj" w Anki**. Klikasz przycisk na słowniku w przeglądarce, a hasło / tłumaczenie / definicja **wpisuje się do pól** aktualnie otwartego okna „Dodaj". Nic nie zapisuje się samo — zatwierdzasz kartę ręcznie (Enter).

## Po co to

Dodawanie słówek to zwykle: znajdź słowo w słowniku → skopiuj → wklej do Anki → powtórz dla tłumaczenia/definicji. Web Bridge tnie to do jednego kliknięcia na fragment: tekst ląduje od razu w odpowiednim polu otwartej karty. W przeciwieństwie do AnkiConnect (`guiAddCards`, który zamyka i otwiera okno na nowo, podmieniając całą notatkę) **wpisuje tylko wskazane pola do okna, które już masz otwarte** — reszta notatki zostaje nietknięta.

## Zasada działania

- Moduł wystawia lokalny serwer HTTP na `127.0.0.1:8766` (osobny wątek, daemon).
- `POST` z ciałem `{"fields": {"nazwa_pola": "wartość"}}` → wpisuje te pola do edytora **otwartego** okna „Dodaj" i przeładowuje widok. Zwraca `{"ok": true}` albo `{"ok": false, "error": "..."}`.
- Okno „Dodaj" **musi być otwarte** — jeśli nie jest, endpoint zwraca błąd (`Okno „Dodaj" nie jest otwarte`).
- Które pole dostaje jaką wartość **decyduje strona wysyłająca** (userscript), więc moduł jest uniwersalny — nie zna żadnego słownika.
- Zapis do notatki idzie przez `mw.taskman.run_on_main` (edytor tylko na wątku głównym); handler HTTP czeka na wynik (timeout 5 s).

## Userscript (przeglądarka)

W repo: [`dictionaries-to-anki.user.js`](dictionaries-to-anki.user.js) — wgraj do Tampermonkey / Violentmonkey / Userscripts (Safari). Dodaje przyciski na trzech słownikach:

| Strona | Przycisk | Pole (domyślnie) |
|---|---|---|
| **diki.pl** | `→ hasło` | `ang` |
| | `→ Anki` (samo tłumaczenie) | `pol` |
| | `→ oba` (hasło + tłumaczenie) | `ang` + `pol` |
| **Oxford Learner's** | `→ hasło` · `→ def` · `+ przykład` | `ang` · `def` · `przyklad` (doklejane) |
| **Longman (LDOCE)** | `→ hasło` · `→ def` · `+ przykład` | `ang` · `def` · `przyklad` (doklejane) |
| **Cambridge** (EN i EN-PL) | `→ hasło` · `→ def` · `+ przykład` · `→ pol`¹ | `ang` · `def` · `przyklad` (doklejane) · `pol` |

¹ `→ pol` (tłumaczenie polskie) pojawia się tylko na wariancie **EN-PL** (`/dictionary/english-polish/…`). Cambridge kończy definicje dwukropkiem `:` — jest ucinany przed wysłaniem.

Nazwy pól zmienisz w bloku `FIELDS` na górze userscriptu. Hasło/tłumaczenie/definicja **zamieniają** zawartość pola (jedno znaczenie na kartę). **Przykłady doklejają się** — każdy klik `+ przykład` dodaje zdanie do pola `przyklad`, oddzielając kolejne przez `<br><br>`:

```
The army invaded the neighboring country early in the morning.<br><br>
Historians studied how the empire invaded and conquered new territories.<br><br>
Enemy forces invaded the small nation without warning.
```

(separator `<br><br>` = ten sam, po którym `field_splitter` rozdziela pole na `p1`/`p2`/`p3`).

### Dlaczego userscript, a nie zwykły `fetch`

Strony słowników są na `https`, a mostek na `http://127.0.0.1` — przeglądarka (zwłaszcza Safari) blokuje takie żądania jako *mixed content*. Userscript strzela przez `GM_xmlhttpRequest` / `GM.xmlHttpRequest` menedżera, co omija i mixed content, i CORS. Serwer i tak zwraca nagłówki CORS, więc AnkiConnect ani jego `webCorsOriginList` **nie są potrzebne**.

## Endpoint / protokół

```
POST http://127.0.0.1:8766
Content-Type: application/json
{"fields": {"ang": "mother", "pol": "matka"}}                        # nadpisuje pola
{"fields": {"przyklad": "She invaded..."}, "append": true}           # dokleja (sep. <br><br>)
{"fields": {"przyklad": "..."}, "append": true, "separator": "; "}   # własny separator

→ 200 {"ok": true, "error": null}
→ 200 {"ok": false, "error": "Okno „Dodaj\" nie jest otwarte"}
```

- `append: true` → dokleja wartość do istniejącej treści pola przez `separator` (domyślnie `<br><br>`); puste pole dostaje samą wartość.
- `OPTIONS` (preflight) → `200` z nagłówkami CORS. Serwer bindowany tylko na `127.0.0.1` (nie wychodzi w sieć).

## Konfiguracja i włączanie

Brak własnej zakładki w Ustawieniach — port i mapowanie pól są w kodzie (mostek) i w userscripcie (pola). Włączanie/wyłączanie: **Ustawienia → Moduły** lub `config.json` → `modules.web_bridge`. Zmiana wymaga restartu Anki (serwer startuje na `profile_did_open`). Port zajęty → moduł loguje ostrzeżenie i nie wstaje (nie wysadza wtyczki).
