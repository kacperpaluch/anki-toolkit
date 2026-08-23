# TTS — Text-to-Speech

Generuje pliki audio MP3 dla kart Anki. Obsługuje dwa źródła:
- **Kokoro** — lokalny serwer TTS przez Dockera (darmowy, bez limitu)
- **OpenRouter** — API TTS przez chmurę (płatne per znak, lepsza jakość głosów)

## Wymagania

### Kokoro (lokalnie)
Lokalnie uruchomiony serwer Kokoro. Wtyczka nie startuje serwera samodzielnie — Kokoro musi działać pod adresem podanym w `api_url`.

### OpenRouter (API)
Klucz API z https://openrouter.ai/keys. Żadnych innych zależności.

## Jak używać

### Przeglądarka (batch)
W przeglądarce kart zaznacz notatki, a następnie **menu kontekstowe → Anki Toolkit → TTS**. Menu jest budowane dynamicznie na podstawie skonfigurowanych **zadań TTS**:

| Element menu | Opis |
|---|---|
| Każde zadanie jako osobna akcja | Np. "Generuj audio dla ang", "Generuj audio dla definicji" itd. |
| `Uruchom wszystkie` | Wykonuje wszystkie zadania po kolei jako jedną operację z jednym paskiem postępu i jednym podsumowaniem (widoczne tylko gdy >1 zadanie) |

### Edytor kart (pojedyncza notatka)
Przycisk **TTS** w toolbarze edytora. Najpierw zapisuje bieżącą treść pól edytora, a potem generuje audio dla aktualnie otwartej notatki według wszystkich skonfigurowanych zadań. Działa asynchronicznie — Anki nie zamarza podczas generowania. Jeśli na tym samym edytorze trwa już AI, pobieranie wymowy, TTS albo workflow, kolejna akcja Anki Toolkit jest blokowana, aby nie modyfikować notatki równolegle.

**PPM na polu docelowym** (np. `audio`, `przyklad`) — gdy pole jest `target_field` jakiegoś zadania TTS, pojawia się „Generuj TTS: [label]" (pole puste) lub „Regeneruj TTS: [label]" (pole pełne — stare audio jest usuwane i generowane jest nowe). Działa też w oknie dodawania nowej karty (AddCards).

Notatki które już mają audio w polu docelowym są pomijane — liczy się zarówno `[sound:...]`, jak i osadzony `<audio>` po konwersji przez Audio Embed. Ponowne kliknięcie przycisku podczas trwającej generacji jest ignorowane. Jeśli w trakcie generowania przełączysz się na inną kartę, audio trafia do **właściwej notatki** (zapis bezpośrednio do kolekcji) — nie do aktualnie wyświetlanej.

### Zadania TTS

Każde zadanie definiuje:
- **Etykieta** — nazwa wyświetlana w menu
- **Pole źródłowe** — skąd czytać tekst do syntezy
- **Pole docelowe** — gdzie zapisać `[sound:...]`
- **Tryb**:
  - `single` — jedno audio na notatkę (np. dla pola `ang`)
  - `split` — każdy segment dostaje osobne audio wstawiane **obok słowa** w to samo pole (np. `przyklad` rozdzielany `<br><br>` → `słowo [sound:...]`)
  - `split_audio` — dzieli pole źródłowe i wstawia do pola docelowego **tylko same tagi audio**, bez słów (np. `ang` = `motorway, highway` rozdzielane `,` → pole `audio` = `[sound:1.mp3][sound:2.mp3]`)
- **Separator** — regex dzielący tekst w trybach `split`/`split_audio` (domyślnie `<br><br>`; dla wariantu „tylko audio" zwykle `,`)

Zadania konfiguruje się w **Ustawienia → Wymowa → TTS → Zadania TTS** (przyciski Dodaj/Edytuj/Usuń) lub bezpośrednio w `config.json`.

W przeglądarce pojedyncze zadanie i `Uruchom wszystkie` zapisują wyniki dopiero po zakończeniu generowania danej operacji. Przy anulowaniu zapisują już wygenerowane pliki i pokazują jedno podsumowanie.

## Konfiguracja (`config.json` → sekcja `tts`)

```json
"tts": {
    "tts_provider": "kokoro",
    "button_label": "TTS",
    "api_url": "http://localhost:8880/v1/audio/speech",
    "model": "kokoro",
    "openrouter_api_key": "",
    "use_ai_openrouter_key": false,
    "openrouter_model": "openai/gpt-4o-mini-tts-2025-12-15",
    "voices": ["af_bella", "af_heart", "bm_lewis"],
    "replacements": {"sb": "somebody", "sth": "something"},
    "speed": 0.9,
    "max_workers": 12,
    "max_retries": 3,
    "timeout": 60,
    "tasks": [
        {"label": "Generuj audio dla ang",    "source_field": "ang",      "target_field": "audio",    "mode": "single"},
        {"label": "Generuj audio dla przykł.", "source_field": "przyklad", "target_field": "przyklad", "mode": "split", "split_separator": "<br><br>"}
    ]
}
```

| Pole | Domyślnie | Opis |
|---|---|---|
| `tts_provider` | `kokoro` | Dostawca TTS: `kokoro` (lokalny) lub `openrouter` (API) |
| `button_label` | `"TTS"` | Etykieta przycisku w edytorze kart |
| `api_url` | `http://localhost:8880/v1/audio/speech` | Adres serwera Kokoro (tylko dla `kokoro`) |
| `model` | `kokoro` | Nazwa modelu Kokoro (tylko dla `kokoro`) |
| `openrouter_api_key` | `""` | Klucz API OpenRouter (tylko dla `openrouter`) |
| `use_ai_openrouter_key` | `false` | Użyj klucza OpenRouter z AI Generatora zamiast wpisywać osobno |
| `openrouter_model` | `openai/gpt-4o-mini-tts-2025-12-15` | Model TTS OpenRouter. Kliknij **Pobierz** w ustawieniach aby zobaczyć dostępne modele i ich głosy |
| `voices` | `["af_bella", "af_heart", "bm_lewis"]` | Pula głosów do losowania. Dla OpenRouter: po wybraniu modelu i kliknięciu **Pobierz**, lista głosów wypełnia się automatycznie |
| `replacements` | `{}` | Zamiana całych słów **tylko w tekście wysyłanym do TTS** — treść karty zostaje bez zmian. Słownikowe placeholdery (`sb` → `somebody`, `sth` → `something`) są rozwijane przed syntezą. Dopasowanie bez rozróżniania wielkości liter; wielka litera na początku trafienia jest zachowywana (`Sth` → `Something`). Klucze dłuższe mają priorytet (`sb/sth` zamienia się w całości, zanim zadziałają `sb`/`sth`). Edytowalne w **Ustawienia → Wymowa → TTS → Zamiana wyrazów** (tabela Skrót/Zamiennik + Dodaj/Usuń) |
| `speed` | `0.9` | Tempo mowy (0.1–3.0) |
| `tasks` | `[...]` | Lista zadań TTS — każde definiuje `label`, `source_field`, `target_field`, `mode` (`single`, `split` lub `split_audio`) i opcjonalnie `split_separator`. `split` zapisuje segmenty z audio, a `split_audio` tylko połączone tagi `[sound:...]`. Menu TTS jest budowane z tej listy; pusta lista = brak zadań. Legacy pola pozostają w szablonie `config.json`, ale są ignorowane, gdy istnieje `tasks` |
| `max_workers` | `12` | Liczba równoległych wątków generowania audio |
| `max_retries` | `3` | Liczba prób przy błędach API 429/5xx |
| `timeout` | `60` | Timeout pojedynczego żądania TTS w sekundach |

## Zamiana wyrazów

Słownikowe skróty (`sb`, `sth`, `sb/sth`…) brzmią źle czytane przez TTS. Sekcja **Ustawienia → Wymowa → TTS → Zamiana wyrazów** pozwala zdefiniować własne pary skrót→pełne słowo (tabela z przyciskami Dodaj/Usuń). Zamiana działa **tylko na tekście wysyłanym do silnika** — to, co widzisz na karcie, zostaje nietknięte.

- Zamieniane są **całe słowa** (`sth` w „absinthe" nie ruszy).
- Bez rozróżniania wielkości liter; wielka litera na początku trafienia jest zachowywana (`Sth` → `Something`).
- Dłuższe klucze mają priorytet, więc `sb/sth` rozwija się w całości zanim zadziałają pojedyncze `sb`/`sth`.

Przykład:

```json
"replacements": {"sb": "somebody", "sth": "something", "sb/sth": "somebody or something"}
```

„be reckless of sth" → silnik dostaje „be reckless of something" (na karcie dalej widnieje „sth").

## Głosy

Każda notatka/zdanie losuje głos z listy `voices`. Można podać jeden głos (zawsze ten sam) lub wiele (losowanie).

### Kokoro — ręczne wpisywanie

Dodawanie głosów do `config.json`:
```json
"voices": ["af_bella", "af_heart", "bm_lewis", "bf_emma"]
```

### OpenRouter — wybór z listy (checklist)

W ustawieniach TTS, po wybraniu OpenRouter:
1. Wpisz klucz API
2. Kliknij **Pobierz** obok pola Model — wtyczka pobiera dostępne modele TTS z OpenRouter (wraz z cenami)
3. Wybierz model z rozwijanej listy
4. Pod spodem pojawi się tabela głosów z checkboxami — zaznacz które chcesz używać
5. Przyciski **Zaznacz wszystkie** / **Odznacz wszystkie** ułatwiają szybką selekcję
6. Pole "Głosy" poniżej aktualizuje się automatycznie
7. **▶** — przycisk obok każdego głosu generuje krótki sample i go odtwarza (nie musisz zaznaczać głosu żeby go posłuchać; koszt jednego krótkiego żądania TTS; dla Kokoro darmowe)

Głosy są specyficzne dla każdego modelu (np. OpenAI TTS używa `alloy`, `nova`, `echo`; Voxtral używa `en_paul_happy` itd.)

### Amerykański angielski (`en-us`)

| ID głosu | Płeć |
|---|---|
| `af_alloy` | kobieta |
| `af_aoede` | kobieta |
| `af_bella` | kobieta |
| `af_heart` | kobieta |
| `af_jessica` | kobieta |
| `af_kore` | kobieta |
| `af_nicole` | kobieta |
| `af_nova` | kobieta |
| `af_river` | kobieta |
| `af_sarah` | kobieta |
| `af_sky` | kobieta |
| `am_adam` | mężczyzna |
| `am_echo` | mężczyzna |
| `am_eric` | mężczyzna |
| `am_fenrir` | mężczyzna |
| `am_liam` | mężczyzna |
| `am_michael` | mężczyzna |
| `am_onyx` | mężczyzna |
| `am_puck` | mężczyzna |
| `am_santa` | mężczyzna |

### Brytyjski angielski (`en-gb`)

| ID głosu | Płeć |
|---|---|
| `bf_alice` | kobieta |
| `bf_emma` | kobieta |
| `bf_isabella` | kobieta |
| `bf_lily` | kobieta |
| `bm_daniel` | mężczyzna |
| `bm_fable` | mężczyzna |
| `bm_george` | mężczyzna |
| `bm_lewis` | mężczyzna |

### Pozostałe języki

| ID głosu | Język | Płeć |
|---|---|---|
| `ef_dora` | Hiszpański (`es`) | kobieta |
| `em_alex` | Hiszpański (`es`) | mężczyzna |
| `em_santa` | Hiszpański (`es`) | mężczyzna |
| `ff_siwis` | Francuski (`fr-fr`) | kobieta |
| `hf_alpha` | Hindi (`hi`) | kobieta |
| `hf_beta` | Hindi (`hi`) | kobieta |
| `hm_omega` | Hindi (`hi`) | mężczyzna |
| `hm_psi` | Hindi (`hi`) | mężczyzna |
| `if_sara` | Włoski (`it`) | kobieta |
| `im_nicola` | Włoski (`it`) | mężczyzna |
| `jf_alpha` | Japoński (`ja`) | kobieta |
| `jf_gongitsune` | Japoński (`ja`) | kobieta |
| `jf_nezumi` | Japoński (`ja`) | kobieta |
| `jf_tebukuro` | Japoński (`ja`) | kobieta |
| `jm_kumo` | Japoński (`ja`) | mężczyzna |
| `pf_dora` | Portugalski BR (`pt-br`) | kobieta |
| `pm_alex` | Portugalski BR (`pt-br`) | mężczyzna |
| `pm_santa` | Portugalski BR (`pt-br`) | mężczyzna |
| `zf_xiaobei` | Chiński mandaryński (`zh`) | kobieta |
| `zf_xiaoni` | Chiński mandaryński (`zh`) | kobieta |
| `zf_xiaoxiao` | Chiński mandaryński (`zh`) | kobieta |
| `zf_xiaoyi` | Chiński mandaryński (`zh`) | kobieta |
| `zm_yunjian` | Chiński mandaryński (`zh`) | mężczyzna |
| `zm_yunxi` | Chiński mandaryński (`zh`) | mężczyzna |
| `zm_yunxia` | Chiński mandaryński (`zh`) | mężczyzna |
| `zm_yunyang` | Chiński mandaryński (`zh`) | mężczyzna |

### Schemat nazw głosów

```
af_bella
│└─── nazwa głosu
└──── język + płeć:
      a = American English   b = British English
      e = Spanish            f = French
      h = Hindi              i = Italian
      j = Japanese           p = Brazilian Portuguese
      z = Mandarin Chinese

      f = kobieta (female)   m = mężczyzna (male)
```
