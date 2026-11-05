"""Hand-edited config: values whose type differs from the `config.json` template.

Pure (no Anki imports) so the check is testable and can run before any panel
reads the config — a wrong type there used to crash the settings window.
"""
import json
from pathlib import Path

_TEMPLATE = Path(__file__).resolve().parents[1] / "config.json"
KIND_NAMES = {"bool": "prawda/fałsz", "number": "liczba", "text": "tekst",
              "list": "lista", "dict": "obiekt"}


def load_template() -> dict:
    return json.loads(_TEMPLATE.read_text(encoding="utf-8"))


def _kind(value):
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return {str: "text", list: "list", dict: "dict"}.get(type(value))


def find_type_errors(cfg: dict, template: dict | None = None, prefix: str = "") -> list:
    """[(dotted key, expected kind, actual value)] for keys the template also has.

    Unknown keys and nulls are left alone; lists are not inspected item by item.
    """
    template = load_template() if template is None else template
    errors = []
    for key, default in template.items():
        if not isinstance(cfg, dict) or key not in cfg or cfg[key] is None:
            continue
        expected, value = _kind(default), cfg[key]
        if expected is None:
            continue
        if expected == "dict" and isinstance(value, dict):
            errors += find_type_errors(value, default, f"{prefix}{key}.")
        elif _kind(value) != expected:
            errors.append((f"{prefix}{key}", expected, value))
    return errors


def reset_to_defaults(cfg: dict, errors: list, template: dict | None = None) -> None:
    """Put the template value back for every key listed in `errors`."""
    template = load_template() if template is None else template
    for path, _expected, _value in errors:
        *parents, last = path.split(".")
        source, target = template, cfg
        for key in parents:
            source, target = source[key], target[key]
        target[last] = json.loads(json.dumps(source[last]))  # a copy, never the template


def describe(errors: list, limit: int = 12) -> str:
    lines = [f"• {path}: oczekiwano: {KIND_NAMES[expected]}, jest: {json.dumps(value, ensure_ascii=False)[:40]}"
             for path, expected, value in errors[:limit]]
    if len(errors) > limit:
        lines.append(f"• … i {len(errors) - limit} więcej")
    return "\n".join(lines)
