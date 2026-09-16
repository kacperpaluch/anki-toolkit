# Anki Toolkit

Anki Toolkit to jeden dodatek do Anki, wspierający cały proces tworzenia kart:
od pobrania słowa, przez wypełnienie treści i wymowę, po plan powtórek oraz
utrzymanie mediów. Wszystko jest pod **Narzędzia → Anki Toolkit**, a ustawienia
w jednym oknie.

## Menu

| Pozycja | Co robi |
|---|---|
| **Ustawienia…** | Jedno okno z paskiem bocznym dla wszystkich modułów (ten sam dialog otwiera **Config** w **Narzędzia → Dodatki**) |
| **Kolejka słówek (n8n)…** | Panel 📚 z kolejką słówek i czterema słownikami |
| **Plan nauki…** | Elastyczny plan na dziś i spokojne tempo nowych kart |
| **Sprawdź batche AI** | Pobiera wyniki Batch API i wysyła kolejną porcję zadania |
| **Rozdziel pola w kolekcji…** | Field Splitter dla wszystkich notatek |
| **Normalizuj audio (ffmpeg)…** | Ręczna normalizacja głośności całego katalogu mediów |
| **Wyczyść HTML w kolekcji…** | Reguły HTML Cleanup dla wszystkich notatek, jednym krokiem cofania |

W Browserze PPM → **Anki Toolkit** zawiera workflowy, generowanie AI, wymowę,
TTS i rozdzielanie pól dla zaznaczonych notatek. W oknie **Dodaj** są przyciski
AI, słownika, TTS, 📚 i 👁.

## Moduły

Okno ustawień grupuje moduły tak samo jak poniżej.

**Tworzenie kart**

| Moduł | Do czego służy |
|---|---|
| [AI Generator](ai_generator/README.md) | Pola z modeli językowych: wielu dostawców, prompty per pole, workflowy, Batch API i fallback modeli |
| [Słownik](dictionary/README.md) | Audio MP3 z wymową oraz IPA z czterech słowników online |
| [TTS](tts/README.md) | Audio z lokalnego Kokoro albo OpenRouter |
| [Rozdzielanie pól](field_splitter/README.md) | Części pola źródłowego (po separatorze) w kolejnych polach |

Oprócz dostawców na klucz API są dwaj dostawcy lokalni — **Codex CLI**
i **Claude CLI** — którzy generują przez zainstalowanego, zalogowanego klienta
`codex` albo `claude`, na limitach Twojej subskrypcji zamiast płatnego API.

**Źródła** — [Kolejka słówek i Web Bridge](integrations/README.md).
Panel 📚 pobiera wiersze z n8n DataTable, wpisuje hasło do notatki, pokazuje
cztery słowniki w zakładkach (diki, Cambridge EN-PL, Oxford, LDoCE) i odhacza
wiersz po dodaniu karty. Własne słowa spoza tabeli działają tak samo. Obsługuje
adres domowy n8n i zapasowy przez Tailscale. Web Bridge przyjmuje dane
z userscriptu słownika. **AI: znaczenia** robi z jednego hasła po jednej karcie
na każde znaczenie, cytując definicje dosłownie z otwartych zakładek.

**Nauka** — [Plan nauki](workload/README.md). Domyślnie 15 minut
jako punkt odniesienia, 30 minut jako górna granica i 3 nowe karty dziennie
łącznie. Uwzględnia dzisiejszą naukę, zaległości i częste „Ponownie”. Doradza —
nie zmienia limitów Anki ani harmonogramu.

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
pliki `.env`, logi i certyfikaty są ignorowane przez Git.

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
tests/                testy czystej logiki (nie ładuje ich Anki)
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

## Automatyczne limity przez synchronizację

[Workload Service](workload_service/README.md) to niezależny klient dla AnkiWeb lub własnego
serwera Anki: codziennie analizuje historię i ustawia porcję nowych kart.
Moduł w Anki pozostaje doradczy.
