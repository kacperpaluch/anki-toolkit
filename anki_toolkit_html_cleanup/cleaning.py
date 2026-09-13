"""Pure HTML cleanup helpers — a user-editable list of find/replace rules."""

import re


MAX_PASSES = 20
MAX_FIELD_CHARS = 1_000_000


def legacy_default_rules(skip_field: str = "ang") -> list[dict]:
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


def default_rules(skip_field: str = "ang") -> list[dict]:
    rules = legacy_default_rules(skip_field)
    rules[1].update(find=r"</?div\b[^>]*>", to="<br>", repeat=False)
    rules[-1].update(name="Obetnij brzegowe <br>", find=r"^(?:<br>\s*)+|(?:<br>\s*)+$")
    rules.insert(3, {"on": True, "name": "Scal sąsiadujące <br>",
                     "find": r"(?:<br>\s*){2,}", "to": "<br>", "regex": True,
                     "fields": rules[1]["fields"], "repeat": False})
    return rules


def _replace_bounded(value, find, replacement, regex):
    if len(value) > MAX_FIELD_CHARS or len(replacement) > MAX_FIELD_CHARS:
        raise ValueError("Reguła HTML przekracza limit 1 000 000 znaków pola; notatka nie została zmieniona.")
    pattern = re.compile(find if regex else re.escape(find), re.DOTALL | re.IGNORECASE if regex else 0)
    parts, length, end, count = [], 0, 0, 0
    for match in pattern.finditer(value):
        if regex and "\\" in replacement:
            # Conservative bound before expand(): repeated backreferences can
            # otherwise allocate gigabytes before the output-size check below.
            largest_group = max(stop - start for start, stop in match.regs)
            if len(replacement) + replacement.count("\\") * largest_group > MAX_FIELD_CHARS:
                raise ValueError("Zamiennik regex przekracza bezpieczny limit rozmiaru; notatka nie została zmieniona.")
        text = match.expand(replacement) if regex else replacement
        length += match.start() - end + len(text)
        if length + len(value) - match.end() > MAX_FIELD_CHARS:
            raise ValueError("Reguła HTML nadmiernie powiększa pole; notatka nie została zmieniona.")
        parts.extend((value[end:match.start()], text))
        end = match.end()
        count += 1
    parts.append(value[end:])
    return "".join(parts), count


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
        # ponytail: size/pass caps; regex execution time still follows Python re.
        for _ in range(MAX_PASSES if rule.get("repeat") else 1):
            previous = value
            try:
                value, replaced = _replace_bounded(value, find, to, rule.get("regex"))
            except re.error:
                break
            total += replaced
            if not replaced or value == previous:
                break
        if total:
            counts[index] = total
    return value, counts
