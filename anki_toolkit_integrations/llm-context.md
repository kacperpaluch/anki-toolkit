# LLM Context — Anki Toolkit: Integrations

Łączy Word Queue (n8n DataTable, panel i fallback Tailscale) z Web Bridge
(lokalny endpoint dla userscriptu). `word_queue.py` i `panel.py` obsługują
kolejkę; `bridge.py` endpoint, a `dictionaries-to-anki.user.js` jest jednym
źródłem przycisków dla przeglądarki i panelu. Nie rozdzielaj userscriptu na
dwie wersje.

Operacje HTTP n8n działają w tle, a kolekcja/edytor tylko na głównym wątku.
Bridge nasłuchuje wyłącznie na `127.0.0.1`; handler HTTP przekazuje zmianę do
głównego wątku i zachowuje protokół `{"fields": {...}}`. Panel odhacza wiersz
po `id`, a fallback bez panelu może odhaczyć go po słowie. Nie ma automatycznej
migracji konfiguracji: prywatne ustawienia przenosi się jednorazowo poza kodem.
