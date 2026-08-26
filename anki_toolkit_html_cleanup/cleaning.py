"""Pure HTML cleanup helpers — a user-editable list of find/replace rules."""

import re


MAX_PASSES = 20


def default_rules(skip_field: str = "ang") -> list[dict]:
    """The built-in rule set, scoped to a single-line field named `skip_field`.

    Also used to migrate configs written before rules were editable.
    """
    keep = f"!{skip_field}" if skip_field else ""
    return [
        {
            "on": True,
            "name": "&nbsp; → spacja",
            "find": "&nbsp;",
            "to": " ",
            "regex": False,
            "fields": "",
            "repeat": False,
        },
        {
            "on": True,
            "name": "Bloki <div> → <br>",
            "find": r"<div[^>]*>((?:(?!</?div\b).)*?)</div>",
            "to": r"\1<br>",
            "regex": True,
            "fields": keep,
            "repeat": True,
        },
        {
            "on": bool(skip_field),
            "name": "Usuń tagi <div>",
            "find": r"</?div[^>]*>",
            "to": "",
            "regex": True,
            "fields": skip_field,
            "repeat": False,
        },
        {
            "on": True,
            "name": "Obetnij końcowy <br>",
            "find": r"<br>\s*$",
            "to": "",
            "regex": True,
            "fields": keep,
            "repeat": False,
        },
    ]


def applies_to(fields: str, name: str) -> bool:
    """Empty spec = every field, `a, b` = only those, `!a, b` = every other."""
    spec = (fields or "").strip()
    if not spec:
        return True
    negated = spec.startswith("!")
    listed = {part.strip() for part in spec.lstrip("!").split(",") if part.strip()}
    return (name not in listed) if negated else (name in listed)


def clean_field(name: str, value: str, rules: list[dict]) -> tuple[str, dict[int, int]]:
    """Return the cleaned value and {rule index: number of replacements}.

    Regex rules run with DOTALL and IGNORECASE. A rule whose pattern does not
    compile is skipped — the settings dialog rejects those before they reach here.
    """
    value = value or ""
    counts: dict[int, int] = {}
    for index, rule in enumerate(rules):
        if not rule.get("on", True) or not applies_to(rule.get("fields", ""), name):
            continue
        find = rule.get("find") or ""
        if not find:
            continue
        to = rule.get("to", "")
        total = 0
        # ponytail: a flat pass cap, not growth detection. Real nesting is a
        # handful of levels deep; the cap only has to stop a self-feeding rule
        # (find "<br>" → "<br><br>") before it eats the field. Raise it only
        # alongside a size guard — passes cost is exponential, not linear.
        for _ in range(MAX_PASSES if rule.get("repeat") else 1):
            if rule.get("regex"):
                try:
                    value, replaced = re.subn(find, to, value, flags=re.DOTALL | re.IGNORECASE)
                except re.error:
                    break
            else:
                replaced = value.count(find)
                if replaced:
                    value = value.replace(find, to)
            total += replaced
            if not replaced:
                break
        if total:
            counts[index] = total
    return value, counts
