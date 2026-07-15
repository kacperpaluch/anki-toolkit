"""Core field generation logic — provider-agnostic."""

import logging
import threading
import time
from contextlib import contextmanager
from typing import Dict, Optional

from anki.notes import Note

from ..common import clean_html_normalized, safe_str

from .template_engine import render_template
from .providers import get_provider, BaseProvider

logger = logging.getLogger(__name__)


def _collect_skip_tags(config: dict) -> list:
    raw = config.get("skip_tags", config.get("skip_tag", []))
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return [t for t in raw if isinstance(t, str) and t.strip()]


def iter_note_fields(note: Note, config: dict,
                     only_fields: Optional[set] = None,
                     overwrite: bool = False):
    """Yield (field_cfg, target_field) for each field eligible for generation.

    Shared selection logic for the sync generator and the batch backfill:
    honors skip_tags, the note-type config, only_fields, manual_only (only in
    auto mode, i.e. only_fields=None) and the empty-field skip.
    """
    skip_tags = _collect_skip_tags(config)
    if skip_tags and any(t in note.tags for t in skip_tags):
        return
    nt_config = config.get("note_types", {}).get(note.note_type()["name"])
    if not nt_config:
        return
    for field_cfg in nt_config.values():
        if not isinstance(field_cfg, dict):
            continue
        target_field = safe_str(field_cfg.get("target"))
        if not target_field or target_field not in note:
            continue
        if only_fields is not None and target_field not in only_fields:
            continue
        # manual_only wyklucza pole z trybu auto (only_fields=None); jawne
        # only_fields (PPM, submenu per-pole, batch na zaznaczeniu) je omija.
        if only_fields is None and field_cfg.get("manual_only"):
            continue
        if not overwrite and note[target_field].strip():
            continue
        yield field_cfg, target_field


class RateLimiter:
    """Per-provider request pacing: even RPM spacing + a concurrency cap.

    Singleton with one bucket per provider. A bucket spaces request *starts* by
    60/rpm so requests don't burst past an RPS/RPM cap (e.g. Mistral free tier's
    0.83 req/s), and caps how many run at once. rpm<=0 disables pacing,
    max_concurrent<=0 disables the cap. Thread-safe — the browser batch hits
    this from a ThreadPoolExecutor.

    free_only=True applies the bucket only to models whose id contains ':free'
    (OpenRouter free variants); paid models on the same provider pass straight
    through. free_only=False throttles every request for the provider — used by
    free-tier API keys (e.g. Mistral) where the whole key is rate-limited.

    ponytail: paces request *starts*, not tokens. A tokens-per-minute cap
    (Mistral free = 25k TPM) can't be known before the call returns; the 429
    backoff in post_json() absorbs the occasional overflow. Add token
    accounting only if TPM 429s actually persist.
    """

    _instance = None
    _new_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._new_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_buckets"):
            self._buckets: dict[str, dict] = {}
            self._mtx = threading.Lock()

    def configure(self, provider: str, rpm: int = 0,
                  max_concurrent: int = 0, free_only: bool = False) -> None:
        interval = 60.0 / rpm if rpm and rpm > 0 else 0.0
        mc = int(max_concurrent) if max_concurrent and max_concurrent > 0 else 0
        with self._mtx:
            old = self._buckets.get(provider)
            # ponytail: Semaphore can't be resized — rebuild the bucket only
            # when concurrency changes, preserving the last-start timestamp so
            # an in-progress batch keeps its pacing.
            if old is None or old["mc"] != mc:
                self._buckets[provider] = {
                    "lock": threading.Lock(),
                    "sem": threading.Semaphore(mc) if mc else None,
                    "last": old["last"] if old else 0.0,
                    "mc": mc,
                    "interval": interval,
                    "free_only": free_only,
                }
            else:
                old["interval"] = interval
                old["free_only"] = free_only

    def _bucket_for(self, provider: str, model: str) -> Optional[dict]:
        b = self._buckets.get(provider)
        if not b:
            return None
        if b["free_only"] and ":free" not in model.lower():
            return None
        if b["interval"] <= 0 and not b["sem"]:
            return None
        return b

    @contextmanager
    def slot(self, provider: str, model: str):
        """Gate one API call for *provider*: RPM spacing + concurrency cap.

        No-op when the provider has no applicable limit. Concurrent worker
        threads are paced to one start every 60/rpm seconds, so a batch never
        bursts past the provider's rate limit.
        """
        b = self._bucket_for(provider, model)
        if b is None:
            yield
            return
        sem = b["sem"]  # capture: configure() may swap it concurrently
        if sem:
            sem.acquire()
        try:
            interval = b["interval"]
            if interval > 0:
                # Hold the bucket lock across the sleep so request starts stay
                # evenly spaced even with several worker threads queued here.
                with b["lock"]:
                    wait = b["last"] + interval - time.monotonic()
                    if wait > 0:
                        logger.info(
                            f"Rate limit {provider} — czekam {wait:.1f}s"
                        )
                        time.sleep(wait)
                    b["last"] = time.monotonic()
            yield
        finally:
            if sem:
                sem.release()


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
                          requested_model: str = "",
                          temperature: Optional[float] = None) -> Optional[BaseProvider]:
        """Resolve and cache a provider for one concrete provider/model pair.

        temperature: per-prompt override; None = use the provider's default.
        """
        providers_cfg = self._config.get("providers", {})
        provider_cfg = providers_cfg.get(provider_name)
        effective_model = requested_model.strip()
        if isinstance(provider_cfg, dict) and not effective_model:
            effective_model = safe_str(provider_cfg.get("model"))
        cache_key = (provider_name, effective_model, temperature)

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
            if temperature is not None:
                effective_cfg["temperature"] = temperature
            provider = get_provider(provider_name, effective_cfg,
                                    max_retries=max_retries, timeout=request_timeout)
            self._configure_rate_limit(provider_name, provider_cfg)
            self._providers[cache_key] = provider
            return provider
        except ValueError as e:
            self.last_error = str(e)
            logger.error(self.last_error)
            self._providers[cache_key] = None
            return None

    def _configure_rate_limit(self, provider_name: str, provider_cfg: dict) -> None:
        """Register this provider's rate-limit bucket from its config.

        Reads per-provider `rpm`, `max_concurrent`, `rate_limit_free_only`.
        Back-compat: if openrouter has no per-provider `rpm`, fall back to the
        legacy global `free_model_rate_limit`/`free_model_max_concurrent`
        (which only ever throttled :free models)."""
        rpm = int(provider_cfg.get("rpm", 0) or 0)
        max_concurrent = int(provider_cfg.get("max_concurrent", 0) or 0)
        free_only = bool(provider_cfg.get("rate_limit_free_only", False))
        if not rpm and provider_name == "openrouter":
            rpm = int(self._config.get("free_model_rate_limit", 0) or 0)
            if rpm:
                free_only = True
                if not max_concurrent:
                    max_concurrent = int(
                        self._config.get("free_model_max_concurrent", 1) or 1
                    )
        RateLimiter().configure(
            provider_name, rpm=rpm,
            max_concurrent=max_concurrent, free_only=free_only,
        )

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
        changed: dict[str, str] = {}
        fields_map = {fld: clean_html_normalized(note[fld]) for fld in note.keys()}

        for field_cfg, target_field in iter_note_fields(
            note, self._config, only_fields=only_fields, overwrite=overwrite
        ):
            provider_name = safe_str(field_cfg.get("provider"))
            if not provider_name:
                logger.warning(f"Pole '{target_field}' nie ma ustawionego 'provider' — pomijam.")
                continue

            model_name = safe_str(field_cfg.get("model"))
            # Per-prompt temperature — property of the task, so the fallback
            # call below reuses it too. None = provider default.
            temperature = field_cfg.get("temperature")
            if not isinstance(temperature, (int, float)):
                temperature = None
            provider = self._resolve_provider(provider_name, model_name, temperature)
            if provider is None:
                continue

            prompt_template = safe_str(field_cfg.get("prompt", ""))
            prompt = render_template(prompt_template, fields_map)

            _rate_limiter = RateLimiter()
            with _rate_limiter.slot(provider_name, provider.model):
                result = provider.call_api(prompt)
            if result:
                note[target_field] = result
                fields_map[target_field] = clean_html_normalized(result)  # update map for dependent fields
                changed[target_field] = result
                logger.info(
                    f"AI: pole '{target_field}' wygenerowane "
                    f"({provider_name}/{provider.model})"
                )
            else:
                # Fallback: per-prompt (fallback_provider + fallback_model) overrides
                # per-provider (fallback_model in provider config).
                fallback_provider_name = safe_str(field_cfg.get("fallback_provider"))
                fallback_model = safe_str(field_cfg.get("fallback_model"))
                if not fallback_model:
                    # No per-prompt fallback — check provider-level fallback_model.
                    p_cfg = self._config.get("providers", {}).get(provider_name, {})
                    if isinstance(p_cfg, dict):
                        fallback_model = safe_str(p_cfg.get("fallback_model"))
                    # Per-provider fallback uses the same provider.
                    fallback_provider_name = ""
                if not fallback_model:
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
                    continue
                fb_name = fallback_provider_name.strip() or provider_name
                fb_provider = self._resolve_provider(fb_name, fallback_model, temperature)
                if fb_provider is None:
                    continue
                logger.warning(
                    f"AI: fallback dla pola '{target_field}': "
                    f"{provider_name}/{provider.model} → {fb_name}/{fb_provider.model}"
                )
                with _rate_limiter.slot(fb_name, fb_provider.model):
                    result = fb_provider.call_api(prompt)
                if result:
                    note[target_field] = result
                    fields_map[target_field] = clean_html_normalized(result)
                    changed[target_field] = result
                    logger.info(
                        f"AI: pole '{target_field}' wygenerowane przez fallback "
                        f"({fb_name}/{fb_provider.model})"
                    )
                else:
                    provider_error = getattr(fb_provider, "last_error", None)
                    if provider_error:
                        self.last_error = (
                            f"Fallback {fb_name}/{fb_provider.model}, "
                            f"pole '{target_field}': {provider_error}"
                        )
                    else:
                        self.last_error = (
                            f"Fallback {fb_name}/{fb_provider.model}, "
                            f"pole '{target_field}' nie zwrócił treści."
                        )
                    logger.error(f"AI: {self.last_error}")

        return changed
