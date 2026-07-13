# Kolejka słówek (`word_queue`)

Lista słówek z **n8n DataTable** wewnątrz Anki, obok okna „Dodaj", ze słownikami w zakładkach. Dodajesz kartę — wiersz w n8n odhacza się sam. Bez przełączania się do przeglądarki i bez ręcznego klikania toggle'a w panelu n8n.

## Po co to

Typowy cykl dodawania słówka z listy w n8n wyglądał tak:

1. otwórz przeglądarkę tabel n8n, odfiltruj `Anki = false`
2. „otwórz wszystkie linki" → trzy karty w przeglądarce (diki / Longman / Oxford)
3. w każdej karcie klikaj przyciski userscripta ([`web_bridge`](../web_bridge/README.md))
4. Alt-Tab do Anki, Enter
5. Alt-Tab z powrotem, przestaw toggle `Anki` na `true`
6. następny wiersz

Ten moduł zjada kroki 1, 2, 5 i większość Alt-Tabów. Zostaje: kliknij przyciski w słowniku, Enter.

## Jak to wygląda

```
┌─ Dodaj ──────────────┬─ Kolejka słówek ───────────────────────────┐
│ ang: tailgate ←auto  │ 963 do zrobienia · ✓ 0    [Losowo]         │
│ pol:                 │ [Ukryj zrobione] [Zrobione →] [Następne]   │
│ def:                 ├──────────────┬─────────────────────────────┤
│ przyklad:            │ ☐ tailgate   │ [ diki ][ Longman ][ Oxford]│
│                      │ ☐ backdrop   │                             │
│                      │ ☑ hereditary │   ← strona słownika,        │
│                      │ ☐ punchline  │     przyciski userscripta   │
└──────────────────────┴──────────────┴─────────────────────────────┘
```

Panel to `QDockWidget` doklejony do okna „Dodaj" (`AddCards` dziedziczy z `QMainWindow`, więc przyjmuje doki). Otwierasz go przyciskiem **📚** w edytorze albo z **Narzędzia → Anki Toolkit → Kolejka słówek (n8n)**.

Zakładki to `QWebEngineView` — pełny Chromium, ten sam, na którym stoi Anki. Wstrzykiwany jest do nich **ten sam** [`dictionaries-to-anki.user.js`](../web_bridge/dictionaries-to-anki.user.js), którego używasz w Tampermonkeyu. Jedno źródło prawdy: przyciski `→ hasło`, `→ def`, `+ przykład` działają identycznie w Anki i w przeglądarce, gadając z mostkiem `web_bridge` na `127.0.0.1:8766`.

## Znaczenie przycisków

| Akcja | Zapis w n8n | Lista | Nawigacja |
|---|---|---|---|
| **Dodaj** w Anki (Enter) | `Anki = true`, raz na wiersz | ptaszek + szarość | **zostajesz** na słówku |
| **checkbox** zaznaczony | `Anki = true` | szarość | — |
| **checkbox** odznaczony | `Anki = false` | kolor wraca | — |
| **Zrobione →** | `Anki = true` | ptaszek + szarość | następne słówko |
| **Następne** | — | — | następne (pominięcie) |
| **Ukryj zrobione** | — | chowa odhaczone | — |
| **Odśwież** | — | pobiera tabelę od nowa | pierwsze nierobione |
| **Losowo** | — | tasuje natychmiast | pierwsze widoczne |

Trzy decyzje projektowe, które warto rozumieć:

**Dodanie karty nie przeskakuje dalej.** Jedno hasło bywa kilkoma kartami (kilka znaczeń). Po Enterze pole `ang` jest wpisywane z powrotem, więc od razu robisz kolejne znaczenie. Wiersz odhacza się przy **pierwszym** dodaniu — semantyka kolumny to „obsłużone", a nie „skończone" (ile znaczeń zrobisz, wie tylko użytkownik).

**Ptaszek to stan, nie akcja.** Zaznaczenie ustawia `true`, odznaczenie `false`. Pomyłkę cofasz jednym kliknięciem, bez wchodzenia do przeglądarki n8n. Gdy PATCH padnie, ptaszek wraca skąd był — lista nigdy nie kłamie o stanie n8n.

**Nic nie znika samo.** Panel pobiera **całą tabelę** (992 wiersze ≈ 0,3 s) i chowa zrobione checkboxem „Ukryj zrobione" (domyślnie włączonym). Gdyby pobierał tylko `Anki = false`, „Odśwież" gubiłby wiersze odhaczone w tej sesji i cofnięcie przestawałoby działać.

## Bez panelu też działa

Sam hook `add_cards_did_add_note` odhacza słówko również przy zamkniętym panelu — dopasowując kolumnę `Slowko` do zawartości pola `ang` (`eq`, wrażliwe na wielkość liter). To zawodzi, gdy wpiszesz formę inną niż w tabeli (Oxford pokazuje `sprawl`, tabela ma `sprawling`). **Panel patchuje po `id` i trafia zawsze** — dlatego jest wersją pewną.

Notatki, których słówka nie ma w tabeli, są cicho pomijane (tylko wpis w Logach) — karty dodajesz też spoza kolejki. Błąd sieci pokazuje tooltip, bo cichy rozjazd Anki↔n8n wyszedłby dopiero przy następnym przeglądzie tabeli.

> **Uwaga:** przy otwartym panelu **każda** dodana notatka odhacza bieżący wiersz, także dodana obok kolejki. Świadome uproszczenie — panel otwierasz po to, żeby robić kolejkę.

## Adres zapasowy (Tailscale)

Kolejność prób: **ostatni działający host → domowy → zapasowy**. Pierwszy, który odpowie, zostaje zapamiętany do końca sesji.

```
Adres n8n (domowy)  http://192.168.1.50:5678
Adres zapasowy      https://n8n.twoj-tailnet.ts.net
```

Dzięki temu poza domem panel łączy się przez Tailscale bez zmiany ustawień. Zapytania `GET` mają **jedną próbę i 5 s timeoutu** — gdyby retry'owały trzykrotnie (domyślnie w `common.http`), martwy host domowy blokowałby na ~20 s zanim kod w ogóle spróbowałby adresu zapasowego. `PATCH` zachowuje dwie próby, bo utrata odhaczenia to rozjazd z n8n.

## Konfiguracja

**Ustawienia → Integracje → Kolejka słówek.** Przycisk „Pobierz listę" ciągnie tabele z `GET /api/v1/data-tables` i wypełnia rozwijankę; działa też jako test połączenia (sprawdza wartości **z pól**, nie zapisane).

| Klucz | Domyślnie | Znaczenie |
|---|---|---|
| `n8n_url` | `""` | Adres w sieci domowej, próbowany pierwszy |
| `fallback_url` | `""` | Adres zapasowy (Tailscale MagicDNS, bez portu) |
| `api_key` | `""` | Klucz z n8n → Settings → API |
| `table_id` | `""` | ID tabeli (nie nazwa) — z rozwijanki |
| `word_field` | `"ang"` | Pole notatki, do którego wpisywane jest hasło |
| `word_column` | `"Slowko"` | Kolumna z hasłem |
| `flag_column` | `"Anki"` | Kolumna `boolean`: `false` = do zrobienia |
| `link_columns` | `{"diki":"URL","Longman":"Longman","Oxford":"Oxford"}` | Etykieta zakładki → kolumna z URL-em (kolejność ma znaczenie) |
| `page_size` | `250` | Maksimum, jakie przyjmuje n8n |
| `max_rows` | `5000` | Bezpiecznik pętli stronicowania |
| `random_order` | `false` | Startowy stan checkboxa „Losowo" |

Wiersz bez URL-a w danej kolumnie → zakładka wyszarzona i czyszczona (`about:blank`), żeby nie dało się przypadkiem kliknąć przycisku userscripta na stronie poprzedniego hasła. Zakładki ładują się **leniwie**, przy pierwszym wejściu: Chromium na zakładkę to ~100 MB, a Longmana z Oxfordem często nawet nie otwierasz.

Klucz API trafia do `meta.json` w profilu Anki (poza gitem). Zmiany w Ustawieniach wymagają ponownego otwarcia panelu — konfigurację bierze przy tworzeniu.

## Wymagania

- Tabela w n8n z kolumną `boolean` (flaga) i kolumną tekstową z hasłem. URL-e słowników muszą już być w wierszach — moduł ich nie buduje, tylko ładuje.
- **`word_column` musi być unikatowa**, jeśli zamierzasz korzystać z odhaczania bez panelu. Przy duplikatach `filter eq` odhaczy wszystkie pasujące wiersze (dla powtórzonego hasła to zachowanie poprawne).
- Moduł [`web_bridge`](../web_bridge/README.md) włączony — bez niego przyciski w zakładkach nie mają z czym rozmawiać.
- Profil `QWebEngineProfile("ankitoolkit-dict")` jest nazwany, więc ciasteczka (zgody RODO Oxforda, logowanie) przeżywają restart Anki.

Włączanie: **Ustawienia → Moduły** (`modules.word_queue`). Zmiana wymaga restartu Anki.
