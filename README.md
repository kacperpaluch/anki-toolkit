# Anki Toolkit Add-ons

Anki Toolkit to zestaw niezależnych dodatków do Anki, wspierających cały proces
tworzenia kart: od pobrania słowa, przez wypełnienie treści i wymowę, po
organizację powtórek oraz utrzymanie mediów. Każdy dodatek działa i aktualizuje
się osobno — instalujesz tylko te funkcje, których używasz.

## Dodatki

| Dodatek | Do czego służy | Gdzie zacząć |
|---|---|---|
| [Content](anki_toolkit_content/README.md) | AI Generator, Batch API, workflowy, słowniki, TTS i dzielenie pól. | **Narzędzia → Anki Toolkit: Content** |
| [Learning](anki_toolkit_learning/README.md) | Talie filtrowane z presetów szybkich powtórek. | **Narzędzia → Anki Toolkit: Learning…** |
| [Audio Normalizer](anki_toolkit_audio_normalizer/README.md) | Normalizacja głośności mediów przez `ffmpeg`, ręcznie lub automatycznie. | **Narzędzia → Anki Toolkit: Audio Normalizer** |
| [Audio Embed](anki_toolkit_audio_embed/README.md) | Zamiana `[sound:...]` na odtwarzacze HTML5 w wybranych polach. | **Narzędzia → Anki Toolkit: Audio Embed** |
| [HTML Cleanup](anki_toolkit_html_cleanup/README.md) | Usuwanie `&nbsp;` i normalizacja bloków `<div>`. | **Narzędzia → Anki Toolkit: HTML Cleanup** |
| [Field Hider](anki_toolkit_field_hider/README.md) | Ukrywanie pomocniczych pól tylko w oknie Dodaj. | **Narzędzia → Anki Toolkit: Field Hider…** |
| [Local Sources](anki_toolkit_local_sources/README.md) | Lokalne bazy Oxford 5000 i SuperMemo; przyciski **OX** i **SM**. | **Narzędzia → Anki Toolkit: Local Sources — Ustawienia…** |
| [Integrations](anki_toolkit_integrations/README.md) | Kolejka słówek n8n, fallback Tailscale, panel słowników i Web Bridge. | **Narzędzia → Anki Toolkit: Integrations** |

## Instalacja w wersji deweloperskiej

Każdy katalog `anki_toolkit_*` jest samodzielnym dodatkiem Anki. W środowisku
deweloperskim utwórz dowiązanie symboliczne z katalogu `addons21` swojego
profilu Anki do wybranego katalogu w tym repozytorium. Przykład dla Content na
macOS:

```bash
ln -s "/ścieżka/do/anki-toolkit/anki_toolkit_content" \
  "$HOME/Library/Application Support/Anki2/addons21/anki-toolkit-content"
```

Po dodaniu, usunięciu lub przełączeniu dodatku uruchom Anki ponownie. Nie
instaluj równocześnie starego, scalonego Anki Toolkit ani dwóch dodatków,
które realizują tę samą funkcję.

## Typowy przepływ tworzenia kart

```text
n8n / słownik / ręczne hasło
          ↓
Content: AI, definicje i przykłady
          ↓
Content: słownik lub TTS
          ↓
Content: rozdzielenie przykładów na pola
          ↓
Audio Embed / Audio Normalizer
```

Możesz używać tylko wybranych kroków. Workflowy w Content łączą AI, słownik,
TTS i Field Splitter w kolejności dostosowanej do Twojego typu notatki.

## Konfiguracja i dane prywatne

Każdy dodatek ma własne ustawienia dostępne z menu **Narzędzia**. `config.json`
jest bezpiecznym szablonem domyślnym, a rzeczywiste ustawienia profilu Anki są
zapisywane w `meta.json` dodatku.

Pliki trwałe, takie jak lokalne bazy Oxford/SuperMemo, stan Batch API czy
historia normalizacji audio, należą do `user_files/` odpowiedniego dodatku.
`meta.json`, `user_files/`, klucze API, pliki `.env`, logi i certyfikaty są
ignorowane przez Git i nie powinny trafiać do repozytorium.

## Struktura repozytorium

```text
anki_toolkit_*/       samodzielne dodatki Anki
tests/                testy czystej logiki dodatków
docs/                 plan podziału i notatki architektoniczne
AGENTS.md             zasady pracy w repozytorium
llm-context.md        mapa dodatków dla modeli AI
```

Każdy dodatek zawiera własne `README.md` oraz `llm-context.md`: README opisuje
użycie, a context dokumentuje granice techniczne, hooki i niezmienniki.

## Dla deweloperów

Przed zmianą przeczytaj [AGENTS.md](AGENTS.md), a następnie
[llm-context.md](llm-context.md) oraz context tylko właściwego dodatku.

Po zmianach w Pythonie uruchom:

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q -f .
git diff --check
```
