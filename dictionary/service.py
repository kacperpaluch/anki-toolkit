import logging
from dataclasses import dataclass
from typing import Optional

from aqt import mw

from ..common import clean_html_normalized

from .dictionary_service import dictionary_service
from .ipa_service import ipa_service

logger = logging.getLogger(__name__)


@dataclass
class ProcessNoteResult:
    saved_filenames: list[str]
    ipa_saved: bool = False
    audio_requested: bool = False
    audio_found: bool = False
    audio_skipped: bool = False

    @property
    def note_modified(self) -> bool:
        return bool(self.saved_filenames) or self.ipa_saved


def _get_ipa_source_for_dictionary(dictionary: str) -> Optional[str]:
    if dictionary.startswith("oxford"):
        return "oxford"
    elif dictionary.startswith("cambridge"):
        return "cambridge"
    return None


def process_note_group(note, config: dict, dictionaries: list[str],
                       batch_cache: Optional[dict] = None) -> ProcessNoteResult:
    source_field = config.get("source_field", "English")
    target_field = config.get("target_field", "Pronunciation")
    ipa_field = config.get("ipa_field", "")
    ipa_format = config.get("ipa_format", "compact")
    result = ProcessNoteResult(saved_filenames=[])

    if source_field not in note:
        return result

    word = clean_html_normalized(note[source_field])
    if not word:
        return result

    max_retries = int(config.get("max_retries", 3))
    page_timeout = int(config.get("page_timeout", 10))
    mp3_timeout = int(config.get("mp3_timeout", 10))

    page_cache: dict = {}
    if target_field in note and not note[target_field].strip():
        result.audio_requested = True
        sound_tags = []
        audio_results, page_cache = dictionary_service.fetch_audio_group(
            word, dictionaries,
            max_retries=max_retries, page_timeout=page_timeout, mp3_timeout=mp3_timeout,
            batch_cache=batch_cache,
        )
        for audio_result in audio_results:
            result.audio_found = True
            filename = f"dict_{audio_result.source}_{word.replace(' ', '_')}.mp3"
            media_filename = mw.col.media.write_data(filename, audio_result.data)
            sound_tags.append(f"[sound:{media_filename}]")
            result.saved_filenames.append(media_filename)
        if sound_tags:
            note[target_field] = " ".join(sound_tags)
    elif target_field in note and note[target_field].strip():
        result.audio_skipped = True

    ipa_source = next(
        (src for d in dictionaries if (src := _get_ipa_source_for_dictionary(d))),
        None
    )
    if ipa_source is None and any(d.startswith("diki") for d in dictionaries):
        if config.get("diki_ipa_fallback", False):
            ipa_source = config.get("diki_ipa_fallback_source", "wiktionary") or None

    if ipa_source and ipa_field and ipa_field in note and not note[ipa_field].strip():
        ipa_result = ipa_service.fetch_ipa(
            word, ipa_source, html=page_cache.get(ipa_source),
            max_retries=max_retries, timeout=page_timeout,
        )
        if ipa_result is None and ipa_source != "wiktionary" and config.get("wiktionary_ipa_fallback", True):
            logger.info(f"Primary IPA source '{ipa_source}' returned nothing for '{word}', trying Wiktionary")
            ipa_result = ipa_service.fetch_ipa(
                word, "wiktionary",
                max_retries=max_retries, timeout=page_timeout,
            )
        if ipa_result:
            formatted = ipa_service.format_ipa(ipa_result, format_style=ipa_format)
            if formatted:
                note[ipa_field] = formatted
                result.ipa_saved = True

    return result
