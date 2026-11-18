# Anki Toolkit

Jeden dodatek do Anki do tworzenia kart: treść pól z AI,
wymowa i nagrania oraz porządki w kolekcji. Ustawienia są w jednym oknie.

## Gdzie kliknąć

| Miejsce | Co tam jest |
|---|---|
| Edytor (Dodaj / Edytuj) → przycisk **Toolkit ▾** | Działania dla bieżącej notatki: sekwencje, **Uzupełnij puste pola AI**, **Pobierz wymowę: …**, **Nagraj audio (TTS)** |
| Edytor → **Toolkit ▾ → Przypnij do paska** | Wybór działań, które mają własny przycisk obok „Toolkit ▾” (domyślnie **D** = Diki, **O** = Oxford). Przypięte znikają z menu; pasek zmienia się po ponownym otwarciu okna |
| Edytor → **Toolkit ▾ → Skróty klawiszowe…** | Własna kombinacja klawiszy dla każdego działania. Okno odrzuca kombinacje bez Cmd/Ctrl (wpisywałyby znaki), zajęte przez Anki lub inny dodatek i powtórzone; skróty działają po ponownym otwarciu okna |
| Przeglądarka kart → prawy klik → **Anki Toolkit** | To samo dla zaznaczonych notatek, w tym **Wygeneruj pola AI…** |
| **Narzędzia → Anki Toolkit** | **Ustawienia…** i **Operacje na kolekcji** (czyszczenie HTML) |

Menu pokazują tylko to, co pasuje do notatki lub zaznaczenia. Po pracy na wielu
notatkach dostajesz raport z błędami, a **Ustawienia → Diagnostyka** pozwala
ponowić nieudane notatki.

## Moduły

| Moduł | Do czego służy |
|---|---|
| [Prompty AI](ai_generator/README.md) | Treść pól z modeli językowych: prompt na pole, sekwencje, model zapasowy |
| [Wymowa ze słowników](dictionary/README.md) | Audio MP3 i IPA dla pojedynczych słów z czterech słowników |
| [Nagrania (TTS)](tts/README.md) | Audio dla wyrażeń i zdań przez OpenRouter (np. Kokoro) |
| [Czyszczenie HTML](html_cleanup/README.md) | Reguły „znajdź → zamień” przy dodawaniu notatki i dla kolekcji |

Klucze API (dostawcy AI, OpenRouter dla nagrań) są na stronie **Ustawienia → Konta i klucze**. Tam też wybierasz model
domyślny i poziom rozumowania każdego dostawcy. Oprócz dostawców API są
**Codex CLI** i **Claude CLI**, które działają na limitach subskrypcji.

Usunięte funkcje są zachowane w tagach Git: tryb tańszy Batch API
(`archive/batch-api`), „Utwórz karty z AI” w kolejce (`archive/ai-senses`),
kolejka słówek z n8n ze słownikami w zakładkach, mostkiem i userscriptem (`archive/word-queue`),
normalizacja audio przez `ffmpeg` (`archive/audio-normalizer`) i Workload
Service, czyli automatyczne limity nowych kart przez synchronizację (`archive/workload-service`).

## Instalacja

Wymaga Anki 25.09 lub nowszego.

Pobierz `anki-toolkit-<wersja>.ankiaddon` z
[Releases](https://github.com/kacperpaluch/anki-toolkit/releases) i otwórz go
dwuklikiem albo przez **Narzędzia → Dodatki → Zainstaluj z pliku…**, potem
uruchom Anki ponownie. Aktualizacja tą samą drogą zachowuje ustawienia i `user_files/`.

Ustawienia profilu są w `meta.json`, a dane robocze
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
tests/run_all.sh
```

Skrypt uruchamia testy jednostkowe, `compileall`, `git diff --check` i smoke testy Qt.

Smoke testy Qt (`tests/qt_*_smoke.py`) używają prawdziwych widżetów i syntetycznych
notatek, bez modeli, kolekcji i zapisu ustawień. Pojedynczy test uruchamiasz na Qt z Anki:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=/Applications/Anki.app/Contents/Resources/app_packages \
  python3.13 tests/qt_browser_menu_smoke.py
```

Potrzebny jest dokładnie Python 3.13 (dla niego Anki ma skompilowane `aqt`). Gdy nie ma go
w `PATH`, `tests/run_all.sh` bierze go z `uv python find 3.13`; inną ścieżkę podasz w `ANKI_PYTHON`.

Przy zmianach hooków, menu lub zapisu kolekcji sprawdź też działanie w Anki.

Paczkę buduje się z zatwierdzonego kodu:

```bash
git archive --format=zip -o anki-toolkit-X.Y.Z.ankiaddon HEAD -- . \
  ':!tests' ':!.gitignore' ':!AGENTS.md' ':!**/llm-context.md' ':!llm-context.md'
```
