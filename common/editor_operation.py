"""Shared guard for asynchronous operations on one Anki editor."""

_ATTR = "_anki_toolkit_operation"


def begin_editor_operation(editor, label: str):
    """Acquire the editor guard, returning an ownership token or None."""
    if getattr(editor, _ATTR, None) is not None:
        return None
    token = object()
    setattr(editor, _ATTR, (token, label))
    return token


def active_editor_operation(editor) -> str:
    current = getattr(editor, _ATTR, None)
    return current[1] if current else "inna operacja"


def finish_editor_operation(editor, token) -> None:
    """Release the guard only when token still owns it."""
    current = getattr(editor, _ATTR, None)
    if current is not None and current[0] is token:
        delattr(editor, _ATTR)
