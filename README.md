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
| [HTML Cleanup](anki_toolkit_html_cleanup/README.md) | Reguły „znajdź → zamień” dla HTML w polach notatek, definiowane w tabeli. | **Narzędzia → Anki Toolkit: HTML Cleanup** |
| [Field Hider](anki_toolkit_field_hider/README.md) | Ukrywanie pomocniczych pól tylko w oknie Dodaj. | **Narzędzia → Anki Toolkit: Field Hider…** |
| [Local Sources](anki_toolkit_local_sources/README.md) | Lokalne bazy Oxford 5000 i SuperMemo; przyciski **OX** i **SM**. | **Narzędzia → Anki Toolkit: Local Sources…** |
| [Integrations](anki_toolkit_integrations/README.md) | Kolejka słówek n8n, fallback Tailscale, panel słowników i Web Bridge. | **Narzędzia → Anki Toolkit: Integrations** |

## Opis dodatków

### Content

Główne narzędzie do budowania treści kart. Pozwala generować wybrane pola przez
modele AI, pobierać nagrania i IPA ze słowników, tworzyć audio przez TTS oraz
dzielić dłuższe pole z przykładami na kolejne pola notatki. Konfigurujesz tu
prompty, dostawców AI, zadania TTS i akcje dostępne w edytorze albo Browserze.

### Learning

Tworzy lub odświeża talie filtrowane z gotowych presetów: karty uczone ostatnio,
trudne, wszystkie nie-nowe albo losowe. Wybierasz preset i limit kart, a oceny
w takiej talii nie zmieniają zwykłego harmonogramu powtórek.

### Audio Normalizer

Wyrównuje głośność plików w katalogu mediów Anki przez `ffmpeg`. Można uruchomić
normalizację ręcznie dla całej kolekcji albo włączyć watcher, który po krótkim
opóźnieniu normalizuje nowe pliki z TTS, słowników, synchronizacji lub ręcznego
dodania.

### Audio Embed

Przepisuje znaczniki `[sound:plik.mp3]` w wybranych polach na elementy `<audio>`.
To przydaje się zwłaszcza dla przykładów i pól pomocniczych, gdzie chcesz własny
wygląd odtwarzacza CSS. Dodatek nie pobiera audio i nie zależy od jego źródła.

### HTML Cleanup

Czyści artefakty z wklejanego HTML według listy reguł „znajdź → zamień”,
które definiujesz w tabeli w ustawieniach: zwykły tekst albo regex, z
zakresem pól i opcją powtarzania. Domyślnie zamienia `&nbsp;` na spacje i
normalizuje tagi `<div>`. Działa automatycznie przy dodawaniu notatek, a na
żądanie może przeskanować całą kolekcję jednym krokiem cofania.

### Field Hider

Pozwala ukryć pola pomocnicze tylko w oknie Dodaj, bez zmiany modelu notatki i
bez ukrywania ich w Browserze. Jest przydatny, gdy część pól ma być później
wypełniana przez inne dodatki, ale nie powinna rozpraszać przy ręcznym wpisie.

### Local Sources

Wykorzystuje lokalne eksporty Oxford 5000 i SuperMemo przechowywane poza
kolekcją. Przyciski **OX** i **SM** znajdują hasło, pozwalają wybrać znaczenie
i uzupełniają wyłącznie puste pola; nie wymagają sieci ani nie nadpisują Twojej
treści.

### Integrations

Łączy Anki z kolejką słówek w n8n DataTable. Panel 📚 pobiera wiersze, wpisuje
hasło do notatki, pokazuje strony słowników w zakładkach i odhaczą wiersz po
dodaniu karty. Obsługuje adres domowy n8n oraz adres zapasowy przez Tailscale.
Web Bridge przyjmuje dane z userscriptu słownika i wpisuje je do otwartego okna
Dodaj.

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

## Konfiguracja i dane prywatne

Każdy dodatek ma własne ustawienia dostępne z menu **Narzędzia**. Ten sam
dialog otwiera przycisk **Config** przy dodatku w **Narzędzia → Dodatki** —
żaden dodatek nie pokazuje już surowego edytora JSON. `config.json` jest
bezpiecznym szablonem domyślnym, a rzeczywiste ustawienia profilu Anki są
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
