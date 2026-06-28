from .consts import ADDON_NAME
from .html import clean_html, clean_html_normalized
from .text import (
    unique, safe_str, unique_filename, normalize_float,
    split_separator_regex, plural_pl, apply_word_replacements,
)
from .http import fetch_url, fetch_text, extract_http_error, post_json, RETRYABLE_STATUS_CODES
from .config import get_full_config, save_full_config, get_module_config, save_module_config
from .debug_log import setup_logging, set_debug, get_log_lines, get_log_seq, clear_log
