"""
Simple template engine supporting {{variable}} substitution
and {% if field %} ... {% else %} ... {% endif %} conditionals.

Limitation: nested {% if %} blocks are not supported — the regex matches
the first {% endif %} it encounters.
"""

import re
from typing import Dict, List

MAX_DEPTH = 50

IF_PATTERN = re.compile(
    r'{%\s*if\s+([^%]+)%}(.*?)(?:{%\s*else\s*%}(.*?))?{%\s*endif\s*%}',
    re.DOTALL
)

_BLOCK_TOKEN_PATTERN = re.compile(r'{%\s*(if\b[^%]*?|else|endif)\s*%}')


def template_structure_problems(template: str) -> List[str]:
    """Return human-readable problems with {% if %} block structure (empty = OK)."""
    problems: List[str] = []
    depth = 0
    else_seen = False

    for match in _BLOCK_TOKEN_PATTERN.finditer(template):
        token = match.group(1).strip()
        if token.startswith("if"):
            if not token[2:].strip():
                problems.append("{% if %} bez nazwy pola.")
            if depth >= 1:
                problems.append("Zagnieżdżone {% if %} nie są obsługiwane przez silnik szablonów.")
            depth += 1
            else_seen = False
        elif token == "else":
            if depth == 0:
                problems.append("{% else %} bez otwartego {% if %}.")
            elif else_seen:
                problems.append("Podwójny {% else %} w jednym bloku {% if %}.")
            else:
                else_seen = True
        else:  # endif
            if depth == 0:
                problems.append("{% endif %} bez otwartego {% if %}.")
            else:
                depth -= 1
                else_seen = False

    if depth > 0:
        problems.append("Niedomknięty {% if %} — brakuje {% endif %}.")

    return list(dict.fromkeys(problems))


def render_template(template: str, fields: Dict[str, str], _depth: int = 0) -> str:
    """Render a template string by substituting fields and evaluating conditionals."""
    if _depth > MAX_DEPTH:
        return template

    def replace_if(match):
        field_name = match.group(1).strip()
        if_content = match.group(2)
        else_content = match.group(3) if match.group(3) else ""

        if fields.get(field_name) and fields.get(field_name).strip():
            return render_template(if_content, fields, _depth + 1)
        else:
            return render_template(else_content, fields, _depth + 1)

    template = IF_PATTERN.sub(replace_if, template)

    def replace_var(match):
        var_name = match.group(1).strip()
        return fields.get(var_name, match.group(0))

    template = re.sub(r'{{(.*?)}}', replace_var, template)
    return template
