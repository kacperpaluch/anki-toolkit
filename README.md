# Anki Toolkit

Jeden dodatek do Anki do tworzenia kart: kolejka słówek, treść pól z AI,
wymowa i nagrania oraz porządki w kolekcji. Ustawienia są w jednym oknie.

## Gdzie kliknąć

| Miejsce | Co tam jest |
|---|---|
| Edytor (Dodaj / Edytuj) → przycisk **Toolkit ▾** | Działania dla bieżącej notatki: sekwencje, **Uzupełnij puste pola AI**, wymowa, **Nagraj audio (TTS)**; w oknie Dodaj także **📚 Kolejka słówek** i **Pokaż/ukryj schowane pola** |
| Przeglądarka kart → prawy klik → **Anki Toolkit** | To samo dla zaznaczonych notatek, w tym **Wygeneruj pola AI…** i rozdzielanie pól |
| **Narzędzia → Anki Toolkit** | **Kolejka słówek (n8n)…**, **Ustawienia…** i **Operacje na kolekcji** (rozdzielanie pól, czyszczenie HTML) |

Menu pokazują tylko to, co pasuje do notatki lub zaznaczenia. Po pracy na wielu
notatkach dostajesz raport z błędami, a **Ustawienia → Diagnostyka** pozwala
ponowić nieudane notatki.

## Moduły

| Moduł | Do czego służy |
|---|---|
| [Prompty AI](ai_generator/README.md) | Treść pól z modeli językowych: prompt na pole, sekwencje, model zapasowy |
| [Wymowa ze słowników](dictionary/README.md) | Audio MP3 i IPA dla pojedynczych słów z czterech słowników |
| [Nagrania (TTS)](tts/README.md) | Audio dla wyrażeń i zdań przez OpenRouter (np. Kokoro) |
| [Rozdzielanie pól](field_splitter/README.md) | Części pola (po separatorze) w kolejnych polach |
| [Kolejka słówek](integrations/README.md) | Słowa z n8n DataTable, cztery słowniki w zakładkach, przyciski userscriptu |
| [Czyszczenie HTML](html_cleanup/README.md) | Reguły „znajdź → zamień” przy dodawaniu notatki i dla kolekcji |
| [Ukrywanie pól](field_hider/README.md) | Pola pomocnicze schowane w oknie Dodaj |

Klucze API i połączenia (dostawcy AI, OpenRouter dla nagrań, n8n, Cloudflare
Access) są na stronie **Ustawienia → Konta i klucze**. Tam też wybierasz model
domyślny i poziom rozumowania każdego dostawcy. Oprócz dostawców API są
**Codex CLI** i **Claude CLI**, które działają na limitach subskrypcji.

Usunięte funkcje są zachowane w tagach Git: tryb tańszy Batch API
(`archive/batch-api`), „Utwórz karty z AI” w kolejce (`archive/ai-senses`)
i normalizacja audio przez `ffmpeg` (`archive/audio-normalizer`).

## Instalacja

Wymaga Anki 25.09 lub nowszego.

Pobierz `anki-toolkit-<wersja>.ankiaddon` z
[Releases](https://github.com/kacperpaluch/anki-toolkit/releases) i otwórz go
dwuklikiem albo przez **Narzędzia → Dodatki → Zainstaluj z pliku…**, potem
uruchom Anki ponownie. Aktualizacja tą samą drogą zachowuje ustawienia i `user_files/`.

Ustawienia profilu są w `meta.json`, a dane robocze (stan kolejki)
w `user_files/`. Oba miejsca są poza Gitem. `config.json`
to szablon z wartościami domyślnymi. Przy wielu profilach Anki ustawienia są wspólne.

## Dla deweloperów

Katalog główny repozytorium jest dodatkiem. Na macOS podepnij go dowiązaniem:

```bash
ln -s "/ścieżka/do/anki-toolkit" \
  "$HOME/Library/Application Support/Anki2/addons21/anki-toolkit"
```

Przed zmianą przeczytaj [AGENTS.md](AGENTS.md) i [llm-context.md](llm-context.md).
Po zmianach w Pythonie:

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q -f .
git diff --check
```

Smoke testy Qt (`tests/qt_*_smoke.py`) używają prawdziwych widżetów i syntetycznych
notatek, bez modeli, kolekcji i zapisu ustawień. Uruchamiasz je na Qt z Anki:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=/Applications/Anki.app/Contents/Resources/app_packages \
  python3.13 tests/qt_browser_menu_smoke.py
```

`tests/live_selectors.py` sprawdza zakładki słowników na żywych stronach (wymaga sieci).
Przy zmianach hooków, menu lub zapisu kolekcji sprawdź też działanie w Anki.

Paczkę buduje się z zatwierdzonego kodu:

```bash
git archive --format=zip -o anki-toolkit-X.Y.Z.ankiaddon HEAD -- . \
  ':!tests' ':!workload_service' ':!.gitignore' ':!AGENTS.md' ':!**/llm-context.md' ':!llm-context.md'
```

## Workload Service

[Workload Service](workload_service/README.md) to osobny klient dla AnkiWeb lub
własnego serwera Anki. Codziennie analizuje historię i ustawia porcję nowych kart.
Działa w Dockerze na serwerze i nie jest częścią dodatku.
