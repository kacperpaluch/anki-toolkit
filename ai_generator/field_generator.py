"""Core field generation logic — provider-agnostic."""

import logging
from typing import Dict, Optional

from anki.notes import Note

from ..common import clean_html_normalized, safe_str

from . import stats
from .template_engine import render_template
from .providers import get_provider, BaseProvider

logger = logging.getLogger(__name__)


class FieldGenerator:
    """Fills empty note fields using AI providers configured in config.json.

    Each field specifies a provider and may override its default model.
    Fields without "provider" are skipped.

    Providers are instantiated lazily and cached for the lifetime of the config.
    Resolution failures (missing key, unknown provider) are cached too and
    reported via last_error — no UI calls here, so batches with a broken
    provider don't spawn one dialog per note.
    """

    def __init__(self, config: dict):
        self._config = config
        self._providers: Dict[tuple[str, str], Optional[BaseProvider]] = {}
        self.last_error: Optional[str] = None

    def _resolve_provider(self, provider_name: str,
                          requested_model: str = "") -> Optional[BaseProvider]:
        """Resolve and cache a provider for one concrete provider/model pair."""
        providers_cfg = self._config.get("providers", {})
        provider_cfg = providers_cfg.get(provider_name)
        effective_model = requested_model.strip()
        if isinstance(provider_cfg, dict) and not effective_model:
            effective_model = safe_str(provider_cfg.get("model"))
        cache_key = (provider_name, effective_model)

        if cache_key in self._providers:
            provider = self._providers[cache_key]
            if provider is None:
                self.last_error = (
                    f"Provider '{provider_name}', model '{effective_model}' "
                    f"jest błędnie skonfigurowany "
                    f"(szczegóły w logach)."
                )
            return provider

        if provider_cfg is None:
            self.last_error = (f"Provider '{provider_name}' nie istnieje w sekcji "
                               f"dostawców AI — sprawdź Ustawienia → AI Generator.")
            logger.error(self.last_error)
            self._providers[cache_key] = None
            return None

        api_key = provider_cfg.get("api_key", "")
        if not api_key or api_key.startswith("YOUR_"):
            self.last_error = (f"Brak klucza API dla providera '{provider_name}' — "
                               f"uzupełnij w Ustawienia → AI Generator → Dostawcy.")
            logger.error(self.last_error)
            self._providers[cache_key] = None
            return None

        if not effective_model:
            self.last_error = (
                f"Brak modelu dla providera '{provider_name}' — wybierz model "
                f"w konfiguracji promptu."
            )
            logger.error(self.last_error)
            self._providers[cache_key] = None
            return None

        try:
            max_retries = int(self._config.get("max_retries", 3))
            request_timeout = int(self._config.get("request_timeout", 30))
            effective_cfg = dict(provider_cfg)
            effective_cfg["model"] = effective_model
            provider = get_provider(provider_name, effective_cfg,
                                    max_retries=max_retries, timeout=request_timeout)
            self._providers[cache_key] = provider
            return provider
        except ValueError as e:
            self.last_error = str(e)
            logger.error(self.last_error)
            self._providers[cache_key] = None
            return None

    def process_note(self, note: Note,
                     only_fields: Optional[set] = None,
                     overwrite: bool = False) -> dict[str, str]:
        """Fill empty fields in note according to config.

        Returns a dict of {field_name: generated_value} for each field that was filled.
        Also writes results directly to note so dependent fields can reference them via templates.

        only_fields: if set, only consider those target field names (others are
        skipped entirely). None = all configured target fields.
        overwrite: if True, generate even when the field is already filled
        (overwrites). False = skip filled fields (today's behavior).
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

            if only_fields is not None and target_field not in only_fields:
                continue

            # ponytail: manual_only wyklucza pole z batcha/workflow/generowania
            # "wszystkie puste"; pomijane tylko gdy only_fields=None (tryb auto).
            # Jawne tylko_fields (PPM, submenu per-pole) omija ten warunek.
            if only_fields is None and field_cfg.get("manual_only"):
                continue

            if not overwrite and note[target_field].strip():
                continue

            provider_name = safe_str(field_cfg.get("provider"))
            if not provider_name:
                logger.warning(f"Pole '{target_field}' nie ma ustawionego 'provider' — pomijam.")
                continue

            model_name = safe_str(field_cfg.get("model"))
            provider = self._resolve_provider(provider_name, model_name)
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
