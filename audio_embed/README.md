# Audio Embed

Zamienia klasyczne `[sound:plik.mp3]` na osadzony odtwarzacz HTML5:

```
[sound:tts_elg0r5eypiev.mp3]
→ <audio class="ex-audio" src="tts_elg0r5eypiev.mp3" preload="none"></audio>
```

**Uniwersalny** — nie zależy od źródła audio. Nagranie może trafić do pola przez TTS, słownik albo ręcznie; moduł i tak przekonwertuje `[sound:...]` w wybranych polach.

## Zakres

Działa na **wybranych typach notatek** i **wybranych polach**. Pole `audio` (główne) zostaw poza listą pól — zachowa klasyczne `[sound:...]`, bo tam działa natywny odtwarzacz Anki. Konwersja dotyczy pól przykładowych: `przyklad`, `p1`–`p5` itd.

Operacja jest **idempotentna**: regex łapie tylko `[sound:...]`, więc ponowne uruchomienie nie tyka już osadzonych `<audio>`.

## Jak uruchomić

| Sposób | Gdzie |
|---|---|
| Zaznaczone notatki | Przeglądarka → PPM → **Anki Toolkit → Osadź audio (sound → <audio>)** |
| Cała kolekcja | Narzędzia → Anki Toolkit → **Osadź audio w kolekcji...** |
| Automatycznie po synchronizacji | `scan_on_sync: true` — skan po każdym syncu (łapie audio z każdego źródła, też z telefonu) |

## Konfiguracja

**Ustawienia → Konserwacja → Osadzanie audio** albo `config.json`:

```json
"audio_embed": {
    "note_types": ["angielski"],
    "fields": ["przyklad", "p1", "p2", "p3", "p4", "p5"],
    "css_class": "ex-audio",
    "preload": "none",
    "scan_on_sync": true
}
```

| Pole | Default | Opis |
|---|---|---|
| `note_types` | `["angielski"]` | Typy notatek, w których działa; **puste = wszystkie** |
| `fields` | `przyklad, p1…p5` | Pola do konwersji (nie dodawaj `audio`) |
| `css_class` | `ex-audio` | Klasa CSS wstawianego `<audio>` |
| `preload` | `none` | Atrybut `preload` (`none` / `metadata` / `auto`) |
| `scan_on_sync` | `true` | Auto-skan kolekcji po synchronizacji |

Widoczność akcji w menu przeglądarki: klucz `context_menu.audio_embed`.

## Uwaga o CSS

`<audio>` renderuje natywny kontroler przeglądarki. Wygląd (np. ukrycie/zmniejszenie) kontrolujesz przez `.ex-audio` w CSS szablonu karty — to już poza tym modułem.
