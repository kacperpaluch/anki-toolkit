"""
Simple template engine supporting {{variable}} substitution
and {% if field %} ... {% else %} ... {% endif %} conditionals.
"""

import re
from typing import Dict

MAX_DEPTH = 50

IF_PATTERN = re.compile(
    r'{%\s*if\s+([^%]+)%}(.*?)(?:{%\s*else\s*%}(.*?))?{%\s*endif\s*%}',
    re.DOTALL
)


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
