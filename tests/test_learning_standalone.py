import ast
from pathlib import Path
import unittest
class LearningSourceTests(unittest.TestCase):
 def test_package_has_filtered_deck_presets(self):
  source=Path(__file__).parent.parent/'anki_toolkit_learning/__init__.py'; ast.parse(source.read_text()); self.assertIn('rated:7',source.read_text())
