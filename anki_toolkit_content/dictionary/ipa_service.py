"""
IPA (International Phonetic Alphabet) service for fetching phonetic transcriptions
from Oxford, Cambridge, and Wiktionary dictionaries.
"""

import re
import json
import urllib.parse
from html.parser import HTMLParser
from typing import Optional, Literal
from dataclasses import dataclass
import logging
logger = logging.getLogger(__name__)
from ..common.http import fetch_text


IPASource = Literal["cambridge", "oxford", "wiktionary"]


@dataclass
class IPAResult:
    """Container for IPA transcription results."""
    word: str
    uk: Optional[str] = None
    us: Optional[str] = None
    source: str = ""


class OxfordIPAExtractor(HTMLParser):
    """HTML parser to extract IPA notation from Oxford dictionary pages."""

    def __init__(self, word: str = ""):
        super().__init__()
        self.word = word.lower()
        self.uk_ipa: Optional[str] = None
        self.us_ipa: Optional[str] = None
        self.current_variant: Optional[str] = None
        self.phonetics_depth = 0
        self.capture_next_data = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        attrs_dict = dict(attrs)

        if tag == "div" and "class" in attrs_dict:
            classes = set(attrs_dict["class"].split())
            if "phons_br" in classes:
                self.current_variant = "uk"
                self.phonetics_depth = 1
            elif "phons_n_am" in classes:
                self.current_variant = "us"
                self.phonetics_depth = 1
            elif self.phonetics_depth > 0:
                self.phonetics_depth += 1

        if tag == "span" and "class" in attrs_dict and self.phonetics_depth > 0:
            classes = set(attrs_dict["class"].split())
            if "phon" in classes:
                self.capture_next_data = True

    def handle_data(self, data: str):
        if self.capture_next_data:
            ipa_text = data.strip().strip('/')
            if ipa_text and self.current_variant:
                if self.current_variant == "uk" and not self.uk_ipa:
                    self.uk_ipa = ipa_text
                    logger.debug(f"Found Oxford UK IPA for '{self.word}': /{ipa_text}/")
                elif self.current_variant == "us" and not self.us_ipa:
                    self.us_ipa = ipa_text
                    logger.debug(f"Found Oxford US IPA for '{self.word}': /{ipa_text}/")
            self.capture_next_data = False

    def handle_endtag(self, tag: str):
        if tag == "div" and self.phonetics_depth > 0:
            self.phonetics_depth -= 1
            if self.phonetics_depth == 0:
                self.current_variant = None


class CambridgeIPAExtractor(HTMLParser):
    """HTML parser to extract IPA notation from Cambridge dictionary pages."""

    def __init__(self, word: str = ""):
        super().__init__()
        self.word = word.lower()
        self.uk_ipa: Optional[str] = None
        self.us_ipa: Optional[str] = None
        self.current_variant: Optional[str] = None
        self.in_ipa_span = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]):
        attrs_dict = dict(attrs)

        if tag == "span" and "class" in attrs_dict:
            classes = set(attrs_dict["class"].split())
            if "dpron-i" in classes:
                if "uk" in classes:
                    self.current_variant = "uk"
                elif "us" in classes:
                    self.current_variant = "us"

        if tag == "span" and "class" in attrs_dict and self.current_variant:
            classes = set(attrs_dict["class"].split())
            if "ipa" in classes and "dipa" in classes:
                self.in_ipa_span = True

    def handle_data(self, data: str):
        if self.in_ipa_span and self.current_variant:
            ipa_text = data.strip().strip('/')
            if ipa_text:
                if self.current_variant == "uk" and not self.uk_ipa:
                    self.uk_ipa = ipa_text
                    logger.debug(f"Found Cambridge UK IPA for '{self.word}': /{ipa_text}/")
                elif self.current_variant == "us" and not self.us_ipa:
                    self.us_ipa = ipa_text
                    logger.debug(f"Found Cambridge US IPA for '{self.word}': /{ipa_text}/")

    def handle_endtag(self, tag: str):
        if tag == "span":
            self.in_ipa_span = False


class WiktionaryIPAExtractor:
    """Parser to extract IPA notation from Wiktionary wikitext."""

    def __init__(self, word: str = ""):
        self.word = word.lower()

    def extract(self, wikitext: str) -> tuple[Optional[str], Optional[str]]:
        uk_ipa = None
        us_ipa = None

        uk_pattern = r'\{\{a\|(?:UK|RP|Received Pronunciation)\}\}\s*\{\{IPA\|en\|/([^/]+)/[^}]*\}\}'
        us_pattern = r'\{\{a\|(?:US|GA|GenAm|General American)\}\}\s*\{\{IPA\|en\|/([^/]+)/[^}]*\}\}'

        uk_match = re.search(uk_pattern, wikitext, re.IGNORECASE)
        if uk_match:
            uk_ipa = uk_match.group(1)
            logger.debug(f"Found Wiktionary UK IPA for '{self.word}': /{uk_ipa}/")

        us_match = re.search(us_pattern, wikitext, re.IGNORECASE)
        if us_match:
            us_ipa = us_match.group(1)
            logger.debug(f"Found Wiktionary US IPA for '{self.word}': /{us_ipa}/")

        if not uk_ipa:
            uk_pattern2 = r'\{\{IPA\|en\|/([^/]+)/[^}]*a=(?:UK|RP)[^}]*\}\}'
            uk_match2 = re.search(uk_pattern2, wikitext, re.IGNORECASE)
            if uk_match2:
                uk_ipa = uk_match2.group(1)
                logger.debug(f"Found Wiktionary UK IPA (alt format) for '{self.word}': /{uk_ipa}/")

        if not us_ipa:
            us_pattern2 = r'\{\{IPA\|en\|/([^/]+)/[^}]*a=(?:US|GA)[^}]*\}\}'
            us_match2 = re.search(us_pattern2, wikitext, re.IGNORECASE)
            if us_match2:
                us_ipa = us_match2.group(1)
                logger.debug(f"Found Wiktionary US IPA (alt format) for '{self.word}': /{us_ipa}/")

        return uk_ipa, us_ipa


class IPAService:
    """Service for fetching IPA transcriptions from online dictionaries."""

    OXFORD_BASE_URL = "https://www.oxfordlearnersdictionaries.com/definition/english/"
    CAMBRIDGE_BASE_URL = "https://dictionary.cambridge.org/dictionary/english/"
    WIKTIONARY_API_URL = "https://en.wiktionary.org/w/api.php"

    def fetch_ipa(self, word: str, source: IPASource, html: Optional[str] = None,
                  max_retries: int = 3, timeout: int = 10) -> Optional[IPAResult]:
        """Fetch IPA for a word.

        Args:
            html: Pre-fetched HTML content for Oxford or Cambridge. When provided, skips
                  the HTTP request and parses the given content directly. Ignored for
                  Wiktionary (which uses a JSON API).
        """
        try:
            if source == "oxford":
                return self._fetch_oxford_ipa(word, html, max_retries=max_retries, timeout=timeout)
            elif source == "cambridge":
                return self._fetch_cambridge_ipa(word, html, max_retries=max_retries, timeout=timeout)
            elif source == "wiktionary":
                return self._fetch_wiktionary_ipa(word, max_retries=max_retries, timeout=timeout)
            else:
                logger.error(f"Unknown IPA source: {source}")
                return None
        except Exception as e:
            logger.error(f"Error fetching IPA from {source} for word '{word}': {e}")
            return None

    def _fetch_oxford_ipa(self, word: str, html: Optional[str] = None,
                          max_retries: int = 3, timeout: int = 10) -> Optional[IPAResult]:
        if html is None:
            url = self.OXFORD_BASE_URL + urllib.parse.quote(word)
            logger.info(f"Fetching Oxford IPA from: {url}")
            html = fetch_text(url, max_retries=max_retries, timeout=timeout)
            if html is None:
                return None
        parser = OxfordIPAExtractor(word)
        parser.feed(html)
        if parser.uk_ipa or parser.us_ipa:
            return IPAResult(word=word, uk=parser.uk_ipa, us=parser.us_ipa, source="oxford")
        logger.warning(f"No Oxford IPA found for word: {word}")
        return None

    def _fetch_cambridge_ipa(self, word: str, html: Optional[str] = None,
                             max_retries: int = 3, timeout: int = 10) -> Optional[IPAResult]:
        if html is None:
            url = self.CAMBRIDGE_BASE_URL + urllib.parse.quote(word)
            logger.info(f"Fetching Cambridge IPA from: {url}")
            html = fetch_text(url, max_retries=max_retries, timeout=timeout)
            if html is None:
                return None
        parser = CambridgeIPAExtractor(word)
        parser.feed(html)
        if parser.uk_ipa or parser.us_ipa:
            return IPAResult(word=word, uk=parser.uk_ipa, us=parser.us_ipa, source="cambridge")
        logger.warning(f"No Cambridge IPA found for word: {word}")
        return None

    def _fetch_wiktionary_ipa(self, word: str, max_retries: int = 3, timeout: int = 10) -> Optional[IPAResult]:
        logger.info(f"Fetching Wiktionary IPA for: {word}")
        try:
            params = {
                "action": "parse",
                "page": word,
                "format": "json",
                "prop": "wikitext"
            }
            url = f"{self.WIKTIONARY_API_URL}?{urllib.parse.urlencode(params)}"
            raw = fetch_text(url, max_retries=max_retries, timeout=timeout)
            if raw is None:
                logger.warning(f"No Wiktionary page found for word: {word}")
                return None
            data = json.loads(raw)
            if "parse" not in data or "wikitext" not in data["parse"]:
                logger.warning(f"No Wiktionary page found for word: {word}")
                return None
            wikitext_obj = data["parse"]["wikitext"]
            if "*" not in wikitext_obj:
                logger.warning(f"Wiktionary wikitext missing '*' key for word: {word}")
                return None
            wikitext = wikitext_obj["*"]
            extractor = WiktionaryIPAExtractor(word)
            uk_ipa, us_ipa = extractor.extract(wikitext)
            if uk_ipa or us_ipa:
                return IPAResult(word=word, uk=uk_ipa, us=us_ipa, source="wiktionary")
            logger.warning(f"No Wiktionary IPA found for word: {word}")
            return None
        except Exception as e:
            logger.error(f"Error fetching Wiktionary IPA: {e}")
            return None

    def format_ipa(
        self,
        result: IPAResult,
        format_style: str = "both",
    ) -> str:
        """
        Format IPA for display.

        Styles:
        - "both":     "UK: /θɔːt/ • US: /θɔːt/"
        - "compact":  "/θɔːt/" (if UK=US, otherwise same as "both")
        - "uk_only":  "/θɔːt/"
        - "us_only":  "/θɔːt/"
        """
        uk = result.uk
        us = result.us

        if not uk and not us:
            return ""

        if format_style == "uk_only":
            return f"/{uk}/" if uk else ""

        if format_style == "us_only":
            return f"/{us}/" if us else ""

        if format_style == "compact":
            if uk == us or not us:
                return f"/{uk}/" if uk else f"/{us}/"
            elif not uk:
                return f"/{us}/"

        # "both" or compact with different UK/US values
        if uk and us:
            if uk == us:
                return f"/{uk}/"
            return f"UK: /{uk}/ • US: /{us}/"
        elif uk:
            return f"UK: /{uk}/"
        else:
            return f"US: /{us}/"


# Singleton instance
ipa_service = IPAService()
