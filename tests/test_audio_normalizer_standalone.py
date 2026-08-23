import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).parent.parent / "anki_toolkit_audio_normalizer"
spec = importlib.util.spec_from_file_location("normalizer_config", ROOT / "config.py")
config = importlib.util.module_from_spec(spec); spec.loader.exec_module(config)

class AudioNormalizerStandaloneTests(unittest.TestCase):
    def test_extensions_cover_supported_formats(self):
        self.assertIn(".mp3", config.AUDIO_EXTENSIONS)
        self.assertIn(".flac", config.AUDIO_EXTENSIONS)
