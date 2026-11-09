# Nagrania (TTS) (`tts/`)

Tworzy pliki MP3 przez API TTS OpenRoutera (płatne za znak), np. modelem Kokoro
(`hexgrad/kokoro-82m`) albo OpenAI TTS. Ustawienia są w **Ustawienia → Nagrania (TTS)**,
a klucz API w **Konta i klucze → Nagrania (TTS) — OpenRouter** (osobny albo ten sam
co dla dostawców AI).

## Gdzie to jest

- **Edytor → Toolkit ▾ → Nagraj audio (TTS)** wykonuje wszystkie zadania dla bieżącej notatki.
- **Prawy klik na polu docelowym** → **Generuj TTS: …** (puste pole) albo **Regeneruj TTS: …**.
- **Przeglądarka → prawy klik → Anki Toolkit → Nagraj audio (TTS)** — każde zadanie osobno
  albo **Uruchom wszystkie**. Menu pokazuje tylko zadania, których pola są w zaznaczeniu.

Pole, które ma już `[sound:…]`, jest pomijane. Przy regeneracji stare nagranie
znika dopiero wtedy, gdy nowe powstanie; nieudane segmenty zachowują stare audio.
Zmiana pola w edytorze w trakcie pracy pomija wynik, żeby audio nie trafiło do innego tekstu.

## Zadania

Zadanie ma etykietę, pole źródłowe, pole docelowe i tryb:

| Tryb | Wynik |
|---|---|
| `single` | Jedno nagranie w osobnym polu. Pole z tekstem (nie tylko `[sound:]`) jest pomijane |
| `split` | Pole dzielone separatorem; każdy fragment dostaje nagranie obok siebie (np. zdania w `przyklad`) |
| `split_audio` | Pole dzielone separatorem; do pola docelowego trafiają same tagi audio (np. `motorway, highway` → `[sound:1.mp3][sound:2.mp3]`) |

Separator to wyrażenie regularne (domyślnie `<br><br>`, dla list zwykle `,`).
W trybie `split_audio` pole zostaje zastąpione dopiero po wygenerowaniu całego zestawu.

## Głosy i zamiana wyrazów

Każde nagranie losuje głos z listy `voices` (jeden głos = zawsze ten sam).
Po **Pobierz** przy modelu pojawia się tabela głosów z checkboxami i przyciskiem
**▶** do odsłuchu próbki. Głosy Kokoro mają nazwy `<język><płeć>_<imię>`,
np. `af_bella` (a = amerykański, b = brytyjski; f = kobieta, m = mężczyzna).

**Zamiana wyrazów** zmienia tylko tekst wysyłany do TTS, nie kartę: np. `sth`
→ `something`. Zamieniane są całe słowa, bez rozróżniania wielkości liter
(`Sth` → `Something`), a dłuższe klucze (`sb/sth`) mają pierwszeństwo.

## Wymuszenie dostawcy

Endpoint TTS OpenRoutera ignoruje preferencje dostawcy z żądania, więc ten sam
model może trafić do droższego hosta. Dostawcę wymusza ustawienie konta:

1. Utwórz osobny klucz tylko dla TTS (openrouter.ai/settings/keys).
2. Utwórz guardrail „Only Allow” z wybranym dostawcą i przypisz go do tego klucza.
3. Wklej klucz w **Konta i klucze** i odznacz „Użyj klucza OpenRouter z dostawców AI”.

## Konfiguracja (`tts`)

| Klucz | Domyślnie | Znaczenie |
|---|---|---|
| `openrouter_api_key` / `use_ai_openrouter_key` | `""` / `false` | Własny klucz albo klucz dostawców AI |
| `openrouter_model` | `openai/gpt-4o-mini-tts-2025-12-15` | Model TTS |
| `openrouter_provider` | `""` | Informacyjnie; OpenRouter go ignoruje (patrz wyżej) |
| `voices` | głosy Kokoro | Pula głosów do losowania |
| `replacements` | `{}` | Zamiana wyrazów |
| `speed` | `0.9` | Tempo mowy (0.1–3.0) |
| `tasks` | dwa przykładowe | `label`, `source_field`, `target_field`, `mode`, opcjonalnie `split_separator` |
| `max_workers` | `12` | Równoległe nagrania |
| `max_retries` | `3` | Ponowienia przy 429 i braku połączenia; timeout i 5xx nie są ponawiane (żądanie mogło być już policzone) |
| `timeout` | `60` | Limit czasu żądania (s) |
