# LLM Context — Anki Toolkit: Integrations

Łączy Word Queue (n8n DataTable, panel i fallback Tailscale) z Web Bridge
(lokalny endpoint dla userscriptu). `word_queue.py` i `panel.py` obsługują
kolejkę; `bridge.py` endpoint. Nie rozdzielaj userscriptu na dwie wersje.
Operacje HTTP są w tle, a kolekcja/edytor tylko na głównym wątku.

Przy pierwszym uruchomieniu `_migrate_legacy_config()` kopiuje sekcję
`word_queue` ze starego dodatku `anki-toolkit`; migracja jest jednorazowa i nie
nadpisuje konfiguracji już ustawionej w Integrations.
