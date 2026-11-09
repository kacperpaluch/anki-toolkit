# Anki Toolkit

Anki Toolkit to jeden dodatek do Anki, wspierający cały proces tworzenia kart:
od pobrania słowa, przez wypełnienie treści i wymowę, po utrzymanie mediów.
Wszystko jest w trzech miejscach, a ustawienia w jednym oknie:

- **edytor** (Dodaj / Edytuj) — jeden przycisk **Toolkit ▾**,
- **przeglądarka kart** — prawy klik → **Anki Toolkit**,
- **Narzędzia → Anki Toolkit** — kolejka słówek, ustawienia i operacje na całej kolekcji.

## Menu

| Pozycja | Co robi |
|---|---|
| **Ustawienia…** | Jedno okno z paskiem bocznym dla wszystkich modułów (ten sam dialog otwiera **Config** w **Narzędzia → Dodatki**) |
| **Kolejka słówek (n8n)…** | Panel 📚 z kolejką słówek i czterema słownikami |
| **Operacje na kolekcji → Rozdziel pola w kolekcji…** | Rozdzielanie pól dla wszystkich notatek, jednym krokiem cofania |
| **Operacje na kolekcji → Normalizuj audio (ffmpeg)…** | Ręczna normalizacja głośności całego katalogu mediów |
| **Operacje na kolekcji → Wyczyść HTML w kolekcji…** | Reguły HTML Cleanup dla wszystkich notatek, jednym krokiem cofania |

W przeglądarce kart prawy klik → **Anki Toolkit** zawiera sekwencje, **Wygeneruj pola AI…**,
wymowę, nagrania (TTS) i rozdzielanie pól — tylko to, co pasuje do zaznaczonych notatek.
**Wygeneruj pola AI…** otwiera jedno okno: zaznaczasz pola (puste pola automatyczne są
zaznaczone z góry, pola „tylko na żądanie” można dołączyć), opcjonalnie **Nadpisz pola,
które mają już treść** (z potwierdzeniem). Sekcje menu można ukryć w **Ustawienia → Sekwencje**.
Po generowaniu AI lub sekwencji pojawia się raport zapisanych zmian, pominięć i błędów
z identyfikatorami notatek oraz przyciskiem kopiowania.

Edytor ma jeden przycisk **Toolkit ▾**. Jego menu pokazuje to, co pasuje do bieżącej
notatki: sekwencje, **Uzupełnij puste pola AI**, **Wymowa: Diki / Oxford / …**,
**Nagraj audio (TTS)**, a w oknie **Dodaj** także **📚 Kolejka słówek** i **Pokaż/ukryj
schowane pola**; na końcu **Ustawienia…**. Sekwencja z opcją **Osobny przycisk w edytorze**
ma dodatkowo własny przycisk obok.

## Moduły

Okno ustawień otwiera się na stronie **Przegląd** (gdzie co jest i co jest skonfigurowane;
kliknięcie wiersza przenosi na stronę). Wszystkie klucze API i połączenia (dostawcy AI,
klucz OpenRouter dla nagrań, n8n, Cloudflare Access) są na jednej stronie **Konta
i klucze**; dostawcy AI, których nie używasz, są ukryci do czasu **+ Dodaj dostawcę**.
Ustawienia techniczne (limity, ponowienia, model zapasowy, temperatura, ffmpeg) są
w zwiniętych sekcjach **Zaawansowane**. Moduły są pogrupowane tak samo jak poniżej.

**Tworzenie kart**

| Moduł | Do czego służy |
|---|---|
| [Prompty AI](ai_generator/README.md) | Pola z modeli językowych: wielu dostawców, prompty per pole, sekwencje i modele zapasowe |
| [Wymowa ze słowników](dictionary/README.md) | Audio MP3 z wymową oraz IPA z czterech słowników online |
| [Nagrania (TTS)](tts/README.md) | Audio z API TTS OpenRoutera |
| [Rozdzielanie pól](field_splitter/README.md) | Części pola źródłowego (po separatorze) w kolejnych polach |

Oprócz dostawców na klucz API są dwaj dostawcy lokalni — **Codex CLI**
i **Claude CLI** — którzy generują przez zainstalowanego, zalogowanego klienta
`codex` albo `claude`, na limitach Twojej subskrypcji zamiast płatnego API.
Poziom rozumowania (**effort**) ustawiasz przy dostawcy w **Konta i klucze → Dostawcy AI**;
dostępność poziomów zależy od modelu i wersji CLI.

**Źródła** — [Kolejka słówek i Web Bridge](integrations/README.md).
Panel 📚 pobiera wiersze z n8n DataTable, wpisuje hasło do notatki, pokazuje
cztery słowniki w zakładkach (diki, Cambridge EN-PL, Oxford, LDoCE) i odhacza
wiersz po dodaniu karty. Przyciski userscriptu na stronach słowników wpisują
tłumaczenie, definicję i przykład do otwartej notatki przez Web Bridge.

**Porządki**

| Moduł | Do czego służy |
|---|---|
| [Normalizacja audio](audio_normalizer/README.md) | `ffmpeg` loudnorm ręcznie albo automatycznie dla nowych plików |
| [Czyszczenie HTML](html_cleanup/README.md) | Reguły „znajdź → zamień” w tabeli, stosowane przy dodawaniu notatki |
| [Ukrywanie pól](field_hider/README.md) | Pola pomocnicze schowane tylko w oknie Dodaj |

**Diagnostyka** pokazuje raporty ostatnich operacji z tej sesji (AI, sekwencje, wymowa,
nagrania, czyszczenie HTML) z przyciskiem „Ponów nieudane”, bufor logów wszystkich modułów
i przełącza tryb debug.

## Instalacja

Wymaga Anki 25.09 lub nowszego (Python 3.10+; oficjalne buildy mają 3.13).

Pobierz `anki-toolkit-<wersja>.ankiaddon` z
[Releases](https://github.com/kacperpaluch/anki-toolkit/releases) i otwórz go
dwuklikiem albo przez Narzędzia → Dodatki → Zainstaluj z pliku…, potem uruchom
Anki ponownie. Aktualizacja tą samą drogą zachowuje ustawienia i `user_files/`.

Paczkę buduje się z zatwierdzonego kodu (bez testów i Workload Service):

```bash
git archive --format=zip -o anki-toolkit-X.Y.Z.ankiaddon HEAD -- . \
  ':!tests' ':!workload_service' ':!.gitignore' ':!AGENTS.md' ':!**/llm-context.md' ':!llm-context.md'
```

## Instalacja w wersji deweloperskiej

Katalog główny repozytorium jest dodatkiem. Utwórz dowiązanie symboliczne
z katalogu `addons21` swojego profilu Anki do repozytorium i uruchom Anki
ponownie. Na macOS:

```bash
ln -s "/ścieżka/do/anki-toolkit" \
  "$HOME/Library/Application Support/Anki2/addons21/anki-toolkit"
```

Nie instaluj równocześnie dawnych osobnych dodatków `anki-toolkit-*` — rejestrują
te same hooki.

## Konfiguracja i dane prywatne

`config.json` jest bezpiecznym szablonem z sekcją dla każdego modułu;
rzeczywiste ustawienia profilu są w `meta.json`. Historia normalizacji audio
jest w `user_files/`. `meta.json`, `user_files/`, klucze API,
pliki `.env`, logi i certyfikaty są ignorowane przez Git. Workload Service
uruchomiony z tego samego checkoutu też zapisuje swoje dane do `user_files/`.

Przy wielu profilach Anki ustawienia są wspólne.

## Struktura repozytorium

```text
__init__.py           punkt wejścia dodatku: hooki i menu Narzędzia → Anki Toolkit
settings_dialog.py    wspólne okno ustawień
manifest.json         manifest dodatku; config.json — szablon ustawień
common/ settings/     współdzielone narzędzia i panele ustawień tworzenia kart
ai_generator/ …       moduły dodatku (każdy z własnym README.md)
workload_service/     niezależny klient headless dla limitów nowych kart (nie ładuje go Anki)
tests/                testy logiki i izolowane smoke testy Qt (nie ładuje ich Anki)
AGENTS.md             zasady pracy w repozytorium
llm-context.md        mapa modułów dla modeli AI
```

## Dla deweloperów

Przed zmianą przeczytaj [AGENTS.md](AGENTS.md), a następnie
[llm-context.md](llm-context.md) oraz kontekst tylko właściwego modułu.

Po zmianach w Pythonie uruchom:

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q -f .
git diff --check
```

Dodatkowe smoke testy używają rzeczywistych widżetów Qt i syntetycznych notatek,
bez połączeń z modelami, zmian w kolekcji ani zapisu ustawień użytkownika.
Pierwszy sprawdza ustawienia AI/kolejki, drugi PPM, menu Narzędzia i raporty.
Na macOS, z Pythonem Anki:

```bash
QT_QPA_PLATFORM=offscreen "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" tests/qt_ai_settings_smoke.py
QT_QPA_PLATFORM=offscreen "$HOME/Library/Application Support/AnkiProgramFiles/.venv/bin/python" tests/qt_browser_menu_smoke.py
```

Przy zmianach hooków, menu lub zapisu kolekcji sprawdź również działanie w Anki.
Testy Qt nie zastępują testu z rzeczywistą kolekcją i dostawcą AI.

## Automatyczne limity przez synchronizację

[Workload Service](workload_service/README.md) to niezależny klient dla AnkiWeb lub własnego
serwera Anki: codziennie analizuje historię i ustawia porcję nowych kart.
Działa na serwerze w Dockerze, bez Anki na komputerze; nie jest częścią dodatku.
