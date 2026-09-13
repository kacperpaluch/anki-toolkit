# Repository instructions

## Start here

Before changing code:

1. Read `llm-context.md`.
2. Follow its routing table and read only the context relevant to the task.
3. Use the add-on's own `README.md` plus its `config.json` template as the
   configuration reference — each add-on documents its own keys.
4. Do not load every module context unless the task genuinely spans them.

`README.md` is user-facing documentation. `llm-context.md` describes architecture
and routes to domain context. Keep this file focused on working agreements.

## Project constraints

- This is an Anki add-on written in Python and PyQt.
- Keep Anki collection access and mutations on the main thread.
- Background work on an editor's note runs on a detached copy
  (`common.editor_operation.detach_note` / `merge_note`) — never mutate
  `editor.note` from a worker, and never overwrite a field the user edited
  while the operation was running.
- Background workers may perform HTTP, AI, TTS, parsing, and ffmpeg work.
- Prefer `CollectionOp` for collection changes initiated from the UI.
- Return appropriate `OpChanges` after manual collection mutations.
- Browser context-menu registration is centralized in root `__init__.py`.
- Preserve unknown configuration keys when saving a section.
- Runtime-generated persistent data belongs in `user_files/`.
- Never commit `meta.json`, API keys, user data, logs, or generated media.
- Do not add production dependencies without a clear need and justification.

## UI architecture

Each add-on owns exactly one settings dialog and registers one Tools-menu entry
for it. Content assembles its tabs in `content_settings.py` from
`settings/*.py`; the single-module add-ons keep theirs in `settings.py`.

Do not add a top-level tab for a small feature — extend the tab of the module it
belongs to. Do not reintroduce a cross-add-on dashboard: an add-on's dialog only
configures that add-on.

## Implementation guidance

- Separate pure, testable logic from Qt and Anki glue.
- Avoid new cross-domain imports; use a local soft import for optional integration.
- Do not register a second global Anki Toolkit menu from a module.
- Qt callbacks that may outlive their widgets must guard against deleted objects.
- Keep batch and sync operations idempotent where they may be retried.
- Preserve unrelated user changes and avoid broad stylistic rewrites.

## Verification

After Python changes, run:

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q -f .
git diff --check
```

All tests must pass before committing. Changes involving Qt, Anki hooks, menus,
or collection behavior also require a smoke test in a running Anki instance when
that environment is available.

## Documentation

When behavior changes:

- update the relevant module README for user-visible behavior,
- update the add-on's `README.md` and `config.json` template when configuration changes,
- update the relevant domain context when an invariant changes,
- keep root `llm-context.md` compact and architectural,
- document non-obvious constraints instead of copying implementation details,
- do not create a module `llm-context.md` for small, self-contained code.

Before committing, verify that documentation paths and UI names match the code.
