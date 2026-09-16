# Repository instructions

## Start here

Before changing code:

1. Read `llm-context.md`.
2. Follow its routing table and read only the context relevant to the task.
3. Use the module's `README.md` plus its section of the root `config.json`
   as the configuration reference.
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
- The Tools menu, the Browser context menu and the config action are registered
  only in the root `__init__.py`; modules expose callables for them. Modules
  register their own editor, Add Cards and profile hooks when imported.
- Preserve unknown configuration keys when saving a section.
- Runtime-generated persistent data belongs in `user_files/`.
- Never commit `meta.json`, API keys, user data, logs, or generated media.
- Do not add production dependencies without a clear need and justification.

## UI architecture

The repository root is the add-on. There is one **Tools → Anki Toolkit** submenu and
one settings window (`settings_dialog.py`). Its grouped sidebar lists panels
from `settings/*.py` and each module's `settings.py`; a panel reads the full
config in `__init__`, writes only its own sections in `apply(cfg)` and may veto
saving with `validate()`.

Do not add a sidebar page for a small feature — extend the panel of the module it
belongs to. Do not give a module its own dialog or Tools-menu entry.

## Implementation guidance

- Separate pure, testable logic from Qt and Anki glue.
- Modules share `common/`; do not copy helpers between modules.
- Read and write config through `common` (`get_module_config`,
  `update_module_config`, or `ADDON_NAME`). Never pass `__package__`/`__name__`
  to `mw.addonManager` — inside a module they are not the add-on name.
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
- update the module's `README.md` and its section of the root `config.json` when configuration changes,
- update the relevant domain context when an invariant changes,
- keep root `llm-context.md` compact and architectural,
- document non-obvious constraints instead of copying implementation details,
- do not create a module `llm-context.md` for small, self-contained code.

Before committing, verify that documentation paths and UI names match the code.
