"""
Dictionary audio service for fetching pronunciation audio from Oxford, Cambridge, Diki.pl, and Longman.
"""

import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional, Literal
import logging
logger = logging.getLogger(__name__)
from ..common.http import fetch_url, fetch_text


def _normalize_word(word: str) -> str:
    """Normalize a word for filename/URL matching: lowercase, spaces/hyphens → underscore, drop apostrophes."""
    return word.lower().replace(' ', '_').replace('-', '_').replace("'", "")


DictionarySource = Literal[
    "oxford_uk", "oxford_us", "cambridge_uk", "cambridge_us", "diki_uk", "diki_us",
    "longman_uk", "longman_us"
]


@dataclass
class DictionaryAudioResult:
    """Normalized audio result container."""

    data: bytes
    source: str
    variant: str = ""


class OxfordAudioExtractor(HTMLParser):
    """HTML parser to extract audio URLs from Oxford dictionary pages."""

    def __init__(self, variant: str = "uk"):
        super().__init__()
        self.variant = variant
        self.audio_url: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        if self.audio_url is not None:
            return
        attrs_dict = dict(attrs)

        if tag == "div" and "class" in attrs_dict:
            classes = set(attrs_dict["class"].split())
            target_classes = {"sound", "audio_play_button", f"pron-{self.variant}", "icon-audio"}

            if target_classes.issubset(classes):
                if "data-src-mp3" in attrs_dict and attrs_dict["data-src-mp3"]:
                    self.audio_url = attrs_dict["data-src-mp3"]
                    logger.debug(f"Found Oxford audio URL ({self.variant}): {self.audio_url}")


class CambridgeAudioExtractor(HTMLParser):
    """HTML parser to extract audio URLs from Cambridge dictionary pages."""

    def __init__(self, variant: str = "uk", word: str = ""):
        super().__init__()
        self.variant = variant
        self.word = word.lower()
        self.audio_url: Optional[str] = None
        self.fallback_url: Optional[str] = None
        self.search_pattern = f"{variant}_pron"
        self.word_normalized = _normalize_word(self.word)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        attrs_dict = dict(attrs)

        if tag == "source":
            if attrs_dict.get("type") == "audio/mpeg" and "src" in attrs_dict:
                src = attrs_dict["src"]
                logger.debug(f"Cambridge parser found audio source: {src} (looking for pattern: {self.search_pattern})")
                if self.search_pattern in src:
                    logger.debug(f"Pattern '{self.search_pattern}' found in URL")
                    if self.fallback_url is None:
                        self.fallback_url = src
                    if self.word_normalized and self.word_normalized in src.lower():
                        self.audio_url = src
                        logger.debug(f"Found matching Cambridge audio URL for '{self.word}': {src}")
                    else:
                        logger.debug(f"URL validation: word '{self.word_normalized}' not found in '{src.lower()}', storing as fallback")


class LongmanAudioExtractor(HTMLParser):
    """HTML parser to extract audio URLs from Longman Dictionary (LDOCE) pages."""

    def __init__(self, variant: str = "uk"):
        super().__init__()
        self.variant = variant
        self.audio_url: Optional[str] = None
        self.target_class = "brefile" if variant == "uk" else "amefile"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        if self.audio_url is not None:
            return
        attrs_dict = dict(attrs)

        if tag == "span":
            if "data-src-mp3" in attrs_dict and "class" in attrs_dict:
                classes = set(attrs_dict["class"].split())
                if self.target_class in classes:
                    self.audio_url = attrs_dict["data-src-mp3"]
                    logger.debug(f"Found Longman audio URL ({self.variant}): {self.audio_url}")


class DictionaryService:
    """Service for fetching pronunciation audio from online dictionaries."""

    OXFORD_BASE_URL = "https://www.oxfordlearnersdictionaries.com/definition/english/"
    CAMBRIDGE_BASE_URL = "https://dictionary.cambridge.org/dictionary/english/"
    CAMBRIDGE_WEBSITE = "https://dictionary.cambridge.org"
    DIKI_BASE_URL = "https://www.diki.pl/images-common/"
    LONGMAN_BASE_URL = "https://www.ldoceonline.com/dictionary/"

    def _get_oxford_audio_url(self, html: str, word: str, variant: str) -> Optional[str]:
        parser = OxfordAudioExtractor(variant)
        parser.feed(html)
        return parser.audio_url

    def _get_cambridge_audio_url(self, html: str, word: str, variant: str) -> Optional[str]:
        parser = CambridgeAudioExtractor(variant, word)
        parser.feed(html)
        url = parser.audio_url or parser.fallback_url
        if url and url.startswith('/'):
            url = self.CAMBRIDGE_WEBSITE + url
        return url

    def _get_longman_audio_url(self, html: str, word: str, variant: str) -> Optional[str]:
        parser = LongmanAudioExtractor(variant)
        parser.feed(html)
        return parser.audio_url

    def fetch_audio_group(
        self, word: str, sources: list[str],
        max_retries: int = 3, page_timeout: int = 10, mp3_timeout: int = 10,
        batch_cache: Optional[dict] = None,
    ) -> tuple[list[DictionaryAudioResult], dict[str, str]]:
        """Fetch audio for all given sources, using at most one page request per dictionary.

        Args:
            batch_cache: Optional dict shared across calls in a browser batch. When provided,
                         results for identical (word, sources) combinations are returned from
                         cache instead of repeating HTTP requests.

        Returns:
            results:    list of audio results
            page_cache: maps base dictionary name ('oxford', 'cambridge', 'longman') to
                        the fetched HTML, so callers can reuse it (e.g. for IPA) without
                        issuing another HTTP request.
        """
        cache_key = (word, tuple(sorted(sources)))
        if batch_cache is not None and cache_key in batch_cache:
            return batch_cache[cache_key]

        results: list[DictionaryAudioResult] = []
        page_cache: dict[str, str] = {}

        scraped = {
            "oxford":    (self.OXFORD_BASE_URL,    self._get_oxford_audio_url),
            "cambridge": (self.CAMBRIDGE_BASE_URL,  self._get_cambridge_audio_url),
            "longman":   (self.LONGMAN_BASE_URL,    self._get_longman_audio_url),
        }

        for base, (base_url, get_url_fn) in scraped.items():
            matching = [s for s in sources if s.startswith(base)]
            if not matching:
                continue
            url = base_url + urllib.parse.quote(word)
            logger.info(f"Fetching {base.capitalize()} page for {matching}: {url}")
            html = fetch_text(url, max_retries=max_retries, timeout=page_timeout)
            if not html:
                continue
            page_cache[base] = html
            for source in matching:
                variant = "uk" if source.endswith("_uk") else "us"
                audio_url = get_url_fn(html, word, variant)
                if audio_url:
                    audio = fetch_url(audio_url, max_retries=max_retries, timeout=mp3_timeout)
                    if audio:
                        results.append(DictionaryAudioResult(data=audio, source=source))
                else:
                    logger.warning(f"No {source} audio found for word: {word}")

        for source in [s for s in sources if s.startswith("diki")]:
            audio = self._fetch_diki_audio(word, source, max_retries=max_retries, timeout=mp3_timeout)
            if audio:
                results.append(DictionaryAudioResult(data=audio, source=source))

        result_tuple = (results, page_cache)
        if batch_cache is not None:
            batch_cache[cache_key] = result_tuple
        return result_tuple

    def _fetch_diki_audio(self, word: str, source: str, max_retries: int = 3, timeout: int = 10) -> Optional[bytes]:
        base = word.lower().replace(' ', '_').replace("'", "")
        variant = "uk" if source == "diki_uk" else "us"
        sub = "en/mp3" if variant == "uk" else "en-ame/mp3"
        for candidate in (base.replace('-', '_'), base):
            audio_url = f"{self.DIKI_BASE_URL}{sub}/{candidate}.mp3"
            logger.info(f"Fetching Diki.pl audio from: {audio_url}")
            data = fetch_url(audio_url, max_retries=max_retries, timeout=timeout)
            if data:
                return data
        return None


# Singleton instance
dictionary_service = DictionaryService()
