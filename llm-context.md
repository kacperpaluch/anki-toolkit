# LLM Context — Anki Toolkit Add-ons

Repozytorium zawiera osobne dodatki Anki w katalogach `anki_toolkit_*`. Każdy katalog dodatku ma
własne `manifest.json`, `config.json`, `.gitignore`, `README.md` i
`llm-context.md`. Konfiguracja użytkownika i dane runtime należą do `meta.json`
oraz `user_files/` danego dodatku i nie mogą trafić do Git.

| Dodatek | Zakres |
|---|---|
| `anki_toolkit_content` | AI, workflowy, słownik, TTS, Field Splitter |
| `anki_toolkit_learning` | talie filtrowane |
| `anki_toolkit_audio_normalizer` | ffmpeg i watcher mediów |
| `anki_toolkit_audio_embed` | `[sound:]` → `<audio>` |
| `anki_toolkit_html_cleanup` | czyszczenie HTML |
| `anki_toolkit_field_hider` | pola w Add Cards |
| `anki_toolkit_local_sources` | Oxford 5000 i SuperMemo |
| `anki_toolkit_integrations` | Word Queue/n8n i Web Bridge |

Przed zmianą czytaj `AGENTS.md`, a potem tylko `llm-context.md` właściwego
dodatku. Nie przywracaj scalonego root loadera.
