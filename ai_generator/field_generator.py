"""Core field generation logic — provider-agnostic."""

import logging
from typing import Dict, Optional

from anki.notes import Note
from aqt import mw
from aqt.utils import showWarning

from ..common import clean_html_normalized, safe_float, safe_str

from . import stats
from .template_engine import render_template
from .providers import get_provider, BaseProvider

logger = logging.getLogger(__name__)


class FieldGenerator:
    """Fills empty note fields using AI providers configured in config.json.

    Each field must specify its own provider via the "provider" key.
    Fields without "provider" are skipped.

    Providers are instantiated lazily and cached for the lifetime of the config.
    """

    def __init__(self, config: dict):
        self._config = config
        self._providers: Dict[str, BaseProvider] = {}
        self.last_error: Optional[str] = None

    def _resolve_provider(self, provider_name: str) -> Optional[BaseProvider]:
        """Return a cached provider instance, creating it on first use."""
        if provider_name in self._providers:
            return self._providers[provider_name]

        providers_cfg = self._config.get("providers", {})
        provider_cfg = providers_cfg.get(provider_name)

        if provider_cfg is None:
            msg = (f"Provider '{provider_name}' nie istnieje w sekcji "
                   f"ai_generator.providers w config.json")
            mw.taskman.run_on_main(lambda m=msg: showWarning(m))
            return None

        api_key = provider_cfg.get("api_key", "")
        if not api_key or api_key.startswith("YOUR_"):
            msg = (f"Proszę podać klucz API dla providera '{provider_name}' "
                   f"w sekcji ai_generator.providers w config.json")
            mw.taskman.run_on_main(lambda m=msg: showWarning(m))
            return None

        try:
            max_retries = int(self._config.get("max_retries", 3))
            request_timeout = int(self._config.get("request_timeout", 30))
            provider = get_provider(provider_name, provider_cfg,
                                    max_retries=max_retries, timeout=request_timeout)
            self._providers[provider_name] = provider
            return provider
        except ValueError as e:
            mw.taskman.run_on_main(lambda m=str(e): showWarning(m))
            return None

    def process_note(self, note: Note) -> dict[str, str]:
        """Fill empty fields in note according to config.

        Returns a dict of {field_name: generated_value} for each field that was filled.
        Also writes results directly to note so dependent fields can reference them via templates.
        """
        self.last_error = None
        skip_tags_cfg = self._config.get("skip_tags", self._config.get("skip_tag", []))
        if isinstance(skip_tags_cfg, str):
            skip_tags = [t.strip() for t in skip_tags_cfg.split(",") if t.strip()]
        else:
            skip_tags = [t for t in skip_tags_cfg if isinstance(t, str) and t.strip()]
        if skip_tags and any(t in note.tags for t in skip_tags):
            return {}

        note_type_name = note.note_type()["name"]
        note_types_cfg: dict = self._config.get("note_types", {})
        nt_config = note_types_cfg.get(note_type_name)
        if not nt_config:
            return {}

        changed: dict[str, str] = {}
        fields_map = {fld: clean_html_normalized(note[fld]) for fld in note.keys()}

        for _key, field_cfg in nt_config.items():
            target_field = safe_str(field_cfg.get("target"))
            if not target_field or target_field not in note:
                continue

            if note[target_field].strip():
                continue

            provider_name = safe_str(field_cfg.get("provider"))
            if not provider_name:
                logger.warning(f"Pole '{target_field}' nie ma ustawionego 'provider' — pomijam.")
                continue

            provider = self._resolve_provider(provider_name)
            if provider is None:
                continue

            prompt_template = safe_str(field_cfg.get("prompt", ""))
            prompt = render_template(prompt_template, fields_map)

            provider.last_usage = (0, 0)
            result = provider.call_api(prompt)
            in_tokens, out_tokens = provider.last_usage
            stats.record_request(
                provider_name, provider.model, in_tokens, out_tokens,
                error=result is None, field_generated=bool(result),
            )
            if result:
                note[target_field] = result
                fields_map[target_field] = clean_html_normalized(result)  # update map for dependent fields
                changed[target_field] = result
                logger.info(
                    f"AI: pole '{target_field}' wygenerowane "
                    f"({provider_name}/{provider.model}, tokeny {in_tokens}→{out_tokens})"
                )
            else:
                provider_error = getattr(provider, "last_error", None)
                if provider_error:
                    self.last_error = (
                        f"Provider '{provider_name}', model '{provider.model}', "
                        f"pole '{target_field}': {provider_error}"
                    )
                else:
                    self.last_error = (
                        f"Provider '{provider_name}', model '{provider.model}', "
                        f"pole '{target_field}' nie zwrócił treści."
                    )
                logger.error(f"AI: {self.last_error}")

        if changed:
            stats.record_note()

        return changed
