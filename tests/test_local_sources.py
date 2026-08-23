import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).parent.parent/'anki_toolkit_local_sources/logic.py';s=importlib.util.spec_from_file_location('sources_logic',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class LocalSourcesTests(unittest.TestCase):
 def test_oxford_skips_filled(self):self.assertEqual(m.oxford_fields({'pol':'x'},{'pol':'ok','ang':'a'},'ang'),{})
 def test_sm_mapping(self):self.assertEqual(m.sm_fields({'Translation':'x'},{'pol':'','ang':'a'},{'Translation':'pol'},'ang'),{'pol':'x'})
