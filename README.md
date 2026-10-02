# Anki Toolkit

Anki Toolkit to jeden dodatek do Anki, wspierający cały proces tworzenia kart:
od pobrania słowa, przez wypełnienie treści i wymowę, po utrzymanie mediów.
Wszystko jest pod **Narzędzia → Anki Toolkit**, a ustawienia w jednym oknie.

## Menu

| Pozycja | Co robi |
|---|---|
| **Ustawienia…** | Jedno okno z paskiem bocznym dla wszystkich modułów (ten sam dialog otwiera **Config** w **Narzędzia → Dodatki**) |
| **Kolejka słówek (n8n)…** | Panel 📚 z kolejką słówek i czterema słownikami |
| **Pobierz i zastosuj wyniki Batch API** | Pobiera wyniki Batch API i wysyła kolejną porcję zadania |
| **Operacje na kolekcji → Rozdziel pola w kolekcji…** | Rozdzielanie pól dla wszystkich notatek, jednym krokiem cofania |
| **Operacje na kolekcji → Normalizuj audio (ffmpeg)…** | Ręczna normalizacja głośności całego katalogu mediów |
| **Operacje na kolekcji → Wyczyść HTML w kolekcji…** | Reguły HTML Cleanup dla wszystkich notatek, jednym krokiem cofania |

W Browserze PPM → **Anki Toolkit** zawiera workflowy, generowanie AI, wymowę,
TTS i rozdzielanie pól pasujące do zaznaczonych notatek. Sekcje można ukryć
w **Ustawienia → Workflowy**; Batch API pojawia się tylko dla pasujących promptów API.
AI rozróżnia uzupełnianie pustych pól od regenerowania jednego pola z potwierdzeniem
nadpisania. Po generowaniu AI lub workflow w Browserze pojawia się raport
zapisanych zmian, pominięć i błędów z identyfikatorami notatek oraz przyciskiem kopiowania.
Edytor notatki ma przyciski
workflowów, AI, słowników (np. **Diki**, **Oxford**) i TTS; okno **Dodaj** ma
dodatkowo 📚 (kolejka słówek) i 👁 (ukryte pola).

## Moduły

Okno ustawień grupuje moduły tak samo jak poniżej.

**Tworzenie kart**

| Moduł | Do czego służy |
|---|---|
| [AI Generator](ai_generator/README.md) | Pola z modeli językowych: wielu dostawców, prompty per pole, workflowy, Batch API i fallback modeli |
| [Słownik](dictionary/README.md) | Audio MP3 z wymową oraz IPA z czterech słowników online |
| [TTS](tts/README.md) | Audio z API TTS OpenRoutera |
| [Rozdzielanie pól](field_splitter/README.md) | Części pola źródłowego (po separatorze) w kolejnych polach |

Oprócz dostawców na klucz API są dwaj dostawcy lokalni — **Codex CLI**
i **Claude CLI** — którzy generują przez zainstalowanego, zalogowanego klienta
`codex` albo `claude`, na limitach Twojej subskrypcji zamiast płatnego API.
Poziom rozumowania (**effort**) ustawiasz domyślnie w **AI Generator → Dostawcy**, a osobno
możesz go nadpisać przy prompcie (także dla fallbacku) i w **Kolejka słówek →
AI: znaczenia**. Opcja „Dziedzicz: medium” pokazuje aktualny poziom dostawcy;
dostępność poziomów zależy od modelu i wersji CLI.

Edytor promptów zostawia więcej miejsca na tekst, a ustawienia zadania i modelu
zapasowego są zwijane. W ustawieniach kolejki najpierw widzisz AI; połączenia
i mapowanie pól są w osobnych zwijanych sekcjach. Panel kolejki ma listę i działania
po lewej, słowniki po prawej. Checkboxy zbierają słowa do AI, a opis wyboru
i przycisk **Utwórz karty z AI (n)** pokazują faktyczną paczkę. Ręczne oznaczenie
jako zrobione zwalnia wybór również przy błędzie n8n; błąd pobrania kolejki
pozostaje widoczny nad listą.

**Źródła** — [Kolejka słówek i Web Bridge](integrations/README.md).
Nowe notatki z **Utwórz karty z AI** mają tag dnia `ai-import::YYYY-MM-DD`;
szczegóły dopasowania opisuje dokumentacja modułu. Skrypty samych stron działają
tylko na zakładkach z `page_js` (domyślnie diki) — obejście błędu QtWebEngine 6.11.2,
przez który strony Cambridge, Oxfordu i LDoCE znikały po chwili.
Panel 📚 pobiera wiersze z n8n DataTable, wpisuje hasło do notatki, pokazuje
cztery słowniki w zakładkach (diki, Cambridge EN-PL, Oxford, LDoCE) i odhacza
wiersz po dodaniu karty. Własne słowa spoza tabeli działają tak samo. Obsługuje
adres główny i zapasowy n8n oraz Cloudflare Access (service token). Web Bridge przyjmuje dane
z userscriptu słownika. **Utwórz karty z AI** robi po jednej karcie na znaczenie
z diki; model tylko wskazuje pasującą definicję z Cambridge, Oxfordu lub LDoCE,
więc cała treść karty pochodzi ze słowników.
Okno **Wybierz karty do dodania** grupuje znaczenia według haseł, pokazuje każdą
propozycję osobno i liczy zaznaczone karty na przycisku **Dodaj karty (n)**.
Brak polskiego znaczenia kieruje do pola wymagającego poprawy.
Kolejkę przeszukasz po fragmencie hasła i przefiltrujesz przez **Wszystkie /
Niezrobione / Zrobione**. Dodatkowe pełne konstrukcje mają własne EN i są
domyślnie odznaczone. Ręcznie zaznaczone boczne zwroty diki trafiają do kolejki
n8n przy zatwierdzeniu **Dodaj karty**; osobny przycisk **Dodaj wybrane zwroty do
kolejki** pozwala dopisać je wcześniej, bez zatwierdzania kart.

**Porządki**

| Moduł | Do czego służy |
|---|---|
| [Normalizacja audio](audio_normalizer/README.md) | `ffmpeg` loudnorm ręcznie albo automatycznie dla nowych plików |
| [Czyszczenie HTML](html_cleanup/README.md) | Reguły „znajdź → zamień” w tabeli, stosowane przy dodawaniu notatki |
| [Ukrywanie pól](field_hider/README.md) | Pola pomocnicze schowane tylko w oknie Dodaj |

**Diagnostyka** pokazuje bufor logów wszystkich modułów i przełącza tryb debug.

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
rzeczywiste ustawienia profilu są w `meta.json`. Stan Batch API i historia
normalizacji audio są w `user_files/`. `meta.json`, `user_files/`, klucze API,
pliki `.env`, logi i certyfikaty są ignorowane przez Git. Workload Service
uruchomiony z tego samego checkoutu też zapisuje swoje dane do `user_files/`.

Przy wielu profilach Anki ustawienia i stan Batch API są wspólne, ale każdy
batch zna swoją kolekcję — po przełączeniu profilu czeka na powrót do swojego.

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
