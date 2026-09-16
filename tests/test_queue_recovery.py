"""Recovery checks without HTTP, Qt, credentials or a user's collection."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, ROOT / 'integrations' / f'{filename}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecoveryTests(unittest.TestCase):
    def test_state_survives_restart_and_is_scoped(self):
        State = load('queue_state').QueueState
        with tempfile.TemporaryDirectory() as folder:
            cfg = {'n8n_url': 'https://queue', 'table_id': '1'}
            state = State('/profile/collection.anki2', cfg, folder)
            state.data['drafts'] = [{'row_id': 7, 'word': 'mother'}]
            state.data['owed'] = {'7': 'mother'}
            state.save()
            again = State('/profile/collection.anki2', cfg, folder)
            self.assertEqual(again.data['owed'], {'7': 'mother'})
            again.drop_drafts({7})
            self.assertEqual(again.data['drafts'], [])
            self.assertEqual(State('/other/collection.anki2', cfg, folder).data['owed'], {})
            self.assertEqual(State('/profile/collection.anki2', {**cfg, 'table_id': '2'}, folder).data['owed'], {})

    def test_broken_file_never_blocks_the_panel(self):
        State = load('queue_state').QueueState
        with tempfile.TemporaryDirectory() as folder:
            state = State('/profile/collection.anki2', {}, folder)
            state.path.write_text('{"drafts": ', encoding='utf-8')
            with self.assertLogs(level='ERROR'):
                fresh = State('/profile/collection.anki2', {}, folder)
            self.assertEqual(fresh.data, {'drafts': [], 'local_rows': [], 'owed': {}})
            self.assertTrue(state.path.with_suffix('.broken').exists())

    def test_local_word_moves_onto_its_n8n_row(self):
        State = load('queue_state').QueueState
        with tempfile.TemporaryDirectory() as folder:
            state = State('/profile/collection.anki2', {}, folder)
            state.data['local_rows'] = [{'id': -1, 'Slowko': 'mother'}, {'id': -2, 'Slowko': 'dup'}]
            state.data['drafts'] = [{'row_id': -1, 'word': 'mother'}]
            state.data['owed'] = {'-1': 'mother'}
            rows = [{'id': 7, 'Slowko': 'Mother '}, {'id': 8, 'Slowko': 'dup'}, {'id': 9, 'Slowko': 'dup'}]
            self.assertEqual(state.resolve_local_rows(rows, 'Slowko'), {-1: 7})
            self.assertEqual(state.data['local_rows'], [{'id': -2, 'Slowko': 'dup'}])  # ambiguous stays
            self.assertEqual(state.data['drafts'][0]['row_id'], 7)
            self.assertEqual(state.data['owed'], {'7': 'mother'})

    def test_failed_atomic_save_keeps_previous_file(self):
        module = load('queue_state')
        with tempfile.TemporaryDirectory() as folder:
            state = module.QueueState('/profile/collection.anki2', {}, folder)
            state.save()
            original = state.path.read_bytes()
            state.data['owed']['7'] = 'mother'
            with patch.object(module.os, 'replace', side_effect=OSError('disk')):
                with self.assertRaises(OSError):
                    state.save()
            self.assertEqual(state.path.read_bytes(), original)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)

    def test_post_is_never_repeated_after_lost_response(self):
        m = load('word_queue')
        cfg = {**m._DEFAULTS, 'n8n_url': 'https://primary', 'fallback_url': 'https://fallback',
               'table_id': '1', 'api_key': 'test'}
        saved = [{'id': 9, 'Slowko': 'mother', 'Anki': False}]
        with patch.object(m, '_get_json', return_value=({'data': []}, None)), \
             patch.object(m, 'post_json', return_value=(None, 'timeout')) as post, \
             patch.object(m, 'fetch_queue', return_value=(saved, None)):
            self.assertEqual(m.add_rows(['mother'], cfg), (saved, None))
            post.assert_called_once()
            self.assertEqual(post.call_args.kwargs['max_retries'], 1)
        with patch.object(m, '_get_json', return_value=({'data': []}, None)), \
             patch.object(m, 'post_json', return_value=(None, 'timeout')) as post, \
             patch.object(m, 'fetch_queue', return_value=([], 'offline')):
            rows, error = m.add_rows(['mother'], cfg)
            self.assertEqual(rows, [])
            self.assertIn('niepewny', error)
            post.assert_called_once()

    def test_incomplete_queue_is_not_reported_as_complete(self):
        m = load('word_queue')
        cfg = {**m._DEFAULTS, 'n8n_url': 'https://primary', 'max_rows': 1}
        with patch.object(m, '_get_json', return_value=({'data': [{'id': 1}], 'nextCursor': 'more'}, None)):
            rows, error = m.fetch_queue(cfg)
        self.assertEqual(rows, [])
        self.assertIn('max_rows', error)

    def test_quotes_and_mapping_reject_silent_corruption(self):
        m = load('ai_senses')
        raw = json.dumps({'senses': [{'pl': 'kot', 'en': 'a cat', 'src': 'Oxford', 'match': 'exact'}]})
        self.assertEqual(m.parse_senses(raw, {'diki': 'kotlet', 'Oxford': 'a cat'})[0], [])
        self.assertTrue(m.contains_quote('give up', 'to give   up.'))
        self.assertFalse(m.contains_quote('cat', 'cats'))
        self.assertTrue(m.contains_quote('łódź', '(Łódź)'))
        self.assertIsNotNone(m.validate_mapping({'word_field': 'ang', 'ai_fields': {'pl': 'ang'}}))
        self.assertIsNotNone(m.validate_mapping({'word_field': '', 'ai_fields': {'pl': 'pol'}}))
        self.assertIsNone(m.validate_mapping({'word_field': 'ang', 'ai_fields': {'pl': 'pol'}}))


if __name__ == '__main__':
    unittest.main()
