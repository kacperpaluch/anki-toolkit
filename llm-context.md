# LLM Context — Anki Toolkit Add-ons

Repozytorium zawiera osobne dodatki Anki w katalogach `anki_toolkit_*`. Każdy katalog dodatku ma
własne `manifest.json`, `config.json`, `.gitignore`, `README.md` i
`llm-context.md`. Konfiguracja użytkownika i dane runtime należą do `meta.json`
oraz `user_files/` danego dodatku i nie mogą trafić do Git.

| Dodatek | Zakres |
|---|---|
| `anki_toolkit_content` | AI, workflowy, słownik, TTS, Field Splitter |
| `anki_toolkit_learning` | talie filtrowane |
| `anki_toolkit_workload` | elastyczny plan dnia, spokojne tempo nowych kart, szczegóły obciążenia |
| `anki_toolkit_audio_normalizer` | ffmpeg i watcher mediów |
| `anki_toolkit_html_cleanup` | czyszczenie HTML |
| `anki_toolkit_field_hider` | pola w Add Cards |
| `anki_toolkit_local_sources` | Oxford 5000 i SuperMemo |
| `anki_toolkit_integrations` | Word Queue/n8n, karty z AI, Web Bridge, czytnik StarDict |

Przed zmianą czytaj `AGENTS.md`, a potem tylko `llm-context.md` właściwego
dodatku. Nie przywracaj scalonego root loadera.

`workload_service/` to osobny klient headless: przeczytaj jego `README.md` oraz
kontekst Workload. Własna replika, oficjalny sync, tylko limity nowych;
bez bezpośredniego dostępu do bazy serwera. Stan i token w `user_files/`.

Usługa: `WORKLOAD_CONFIG` w Compose nadpisuje plik; `dashboard.py` czyta historię
i uruchamia `worker.py run` jako osobny proces. Dostęp do kolekcji nadal tylko
w głównym wątku workera, chroniony flock. Panel nie udostępnia plików wolumenu.

`notifications.py` wysyła raport udanego run/restore i jeden alert na trwający identyczny błąd;
`notification_state.json` utrwala deduplikację. Pełny sync wstrzymuje harmonogram przez
`intervention.json`; ręczny `download` robi backup, sprawdza limity i zastępuje tylko replikę.
Błąd maila nie zmienia sukcesu sync. `mail.json` zawiera sekret SMTP i pozostaje
w `user_files/`; Compose montuje katalog hosta zamiast nazwanego wolumenu.
