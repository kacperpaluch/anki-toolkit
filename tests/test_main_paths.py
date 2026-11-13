"""The everyday path of each feature, end to end up to the network.

The regression files guard rare failures; these guard what runs on every word:
dictionary audio lands in the note, AI and TTS requests carry the text and the
key, a pasted list becomes queue entries. Only `common.http.urlopen` is faked.
"""
import io
import json
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

from test_addon_regressions import load
from test_content_regressions import _PKG, FakeNote, _load, http

dict_service = _load("dictionary.dictionary_service", "dictionary/dictionary_service.py")
service = _load("dictionary.service", "dictionary/service.py")
tts_api = _load("tts.api", "tts/api.py")
tts_config = _load("tts.config", "tts/config.py")
_load("ai_generator.field_generator", "ai_generator/field_generator.py")
import sys
providers = sys.modules[f"{_PKG}.ai_generator.providers"]

# Audio elements copied from the live entry pages for "schedule" on 2026-11-12.
# When a dictionary changes its markup, replace the tag here and fix the parser.
OXFORD = (
    '<div class="sound audio_play_button pron-uk icon-audio" data-src-mp3="https://www.oxfordlearnersdictionaries.com/media/english/uk_pron/s/sch/sched/schedule__gb_1.mp3" data-src-ogg="https://www.oxfordlearnersdictionaries.com/media/english/uk_pron_ogg/s/sch/sched/schedule__gb_1.ogg" title="schedule pronunciation&#10;                    English" style="cursor: pointer" valign="top">'
    '<div class="sound audio_play_button pron-us icon-audio" data-src-mp3="https://www.oxfordlearnersdictionaries.com/media/english/us_pron/s/sch/sched/schedule__us_1_rr.mp3" data-src-ogg="https://www.oxfordlearnersdictionaries.com/media/english/us_pron_ogg/s/sch/sched/schedule__us_1_rr.ogg" title="schedule pronunciation&#10;                    American" style="cursor: pointer" valign="top">'
)
CAMBRIDGE = (
    '<source type="audio/mpeg" src="/media/english/uk_pron/u/uks/uksch/uksched001.mp3"/>'
    '<source type="audio/mpeg" src="/media/english/us_pron/s/sch/sched/schedule.mp3"/>'
)
LONGMAN = (
    '<span data-src-mp3="https://www.ldoceonline.com/media/english/breProns/schedule_n0205.mp3?version=1.2.93" class="speaker brefile fas fa-volume-up hideOnAmp" title="Play British pronunciation of schedule">'
    '<span data-src-mp3="https://www.ldoceonline.com/media/english/ameProns/schedule1.mp3?version=1.2.93" class="speaker amefile fas fa-volume-up hideOnAmp" title="Play American pronunciation of schedule">'
    '<span data-src-mp3="https://www.ldoceonline.com/media/english/exaProns/p008-001581737.mp3?version=1.2.93" class="speaker exafile fas fa-volume-up hideOnAmp" title="Play Example">'
)


class Network:
    """Stands in for `common.http.urlopen`: records requests, answers by URL prefix."""

    def __init__(self, answers: dict):
        self.answers, self.requests = answers, []

    def __call__(self, request, timeout):
        self.requests.append(request)
        for prefix, body in self.answers.items():
            if request.full_url.startswith(prefix):
                return io.BytesIO(body)
        raise OSError("unexpected request: " + request.full_url)

    @property
    def urls(self):
        return [request.full_url for request in self.requests]

    def body(self, index=0):
        return json.loads(self.requests[index].data)


class DictionaryAudioTests(unittest.TestCase):
    CONFIG = {"source_field": "ang", "target_field": "audio", "max_retries": 1}

    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.written = {}
        col = types.SimpleNamespace(media=types.SimpleNamespace(
            dir=lambda: media.name,
            write_data=lambda name, data: self.written.setdefault(name, data) and name))
        patcher = patch.object(service.mw, "col", col)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fetch(self, word, dictionaries, answers, audio=""):
        note = FakeNote({"ang": word, "audio": audio})
        network = Network(answers)
        with patch.object(http, "urlopen", network):
            result = service.process_note_group(note, self.CONFIG, dictionaries)
        return note, network, result

    def test_every_dictionary_page_yields_its_uk_and_us_recording(self):
        get = dict_service.dictionary_service
        self.assertEqual(
            [get._get_oxford_audio_url(OXFORD, "schedule", v) for v in ("uk", "us")],
            ["https://www.oxfordlearnersdictionaries.com/media/english/uk_pron/s/sch/sched/schedule__gb_1.mp3",
             "https://www.oxfordlearnersdictionaries.com/media/english/us_pron/s/sch/sched/schedule__us_1_rr.mp3"])
        self.assertEqual(
            [get._get_cambridge_audio_url(CAMBRIDGE, "schedule", v) for v in ("uk", "us")],
            ["https://dictionary.cambridge.org/media/english/uk_pron/u/uks/uksch/uksched001.mp3",
             "https://dictionary.cambridge.org/media/english/us_pron/s/sch/sched/schedule.mp3"])
        self.assertEqual(
            [get._get_longman_audio_url(LONGMAN, "schedule", v) for v in ("uk", "us")],
            ["https://www.ldoceonline.com/media/english/breProns/schedule_n0205.mp3?version=1.2.93",
             "https://www.ldoceonline.com/media/english/ameProns/schedule1.mp3?version=1.2.93"])

    def test_oxford_recordings_land_in_the_audio_field(self):
        note, network, result = self.fetch("schedule", ["oxford_uk", "oxford_us"], {
            "https://www.oxfordlearnersdictionaries.com/definition/english/schedule": OXFORD.encode(),
            "https://www.oxfordlearnersdictionaries.com/media/english/uk_pron/": b"UK",
            "https://www.oxfordlearnersdictionaries.com/media/english/us_pron/": b"US"})
        self.assertEqual(len(network.urls), 3, "one page request serves both variants")
        uk, us = result.saved_filenames
        self.assertEqual(note["audio"], f"[sound:{uk}] [sound:{us}]")
        self.assertEqual((self.written[uk], self.written[us]), (b"UK", b"US"))
        self.assertTrue(uk.startswith("dict_oxford_uk_schedule_") and uk.endswith(".mp3"))

    def test_diki_phrase_is_fetched_by_its_file_name(self):
        note, network, _result = self.fetch("give up", ["diki_uk", "diki_us"],
                                            {"https://www.diki.pl/images-common/": b"MP3"})
        self.assertEqual(network.urls, ["https://www.diki.pl/images-common/en/mp3/give_up.mp3",
                                        "https://www.diki.pl/images-common/en-ame/mp3/give_up.mp3"])
        self.assertEqual(note["audio"].count("[sound:dict_diki_"), 2)

    def test_filled_audio_field_is_left_alone(self):
        note, network, result = self.fetch("schedule", ["oxford_uk"], {}, audio="[sound:mine.mp3]")
        self.assertEqual((note["audio"], network.urls), ("[sound:mine.mp3]", []))
        self.assertTrue(result.audio_skipped)

    def test_word_missing_from_the_dictionary_changes_nothing(self):
        note, _network, result = self.fetch("zzzz", ["oxford_uk"], {
            "https://www.oxfordlearnersdictionaries.com/definition/english/zzzz": b"<html>not found</html>"})
        self.assertEqual(note["audio"], "")
        self.assertTrue(result.audio_requested and not result.audio_found)


class PaidRequestTests(unittest.TestCase):
    def test_ai_request_carries_key_model_and_prompt_and_returns_the_answer(self):
        network = Network({"https://api.openai.com/": json.dumps(
            {"choices": [{"message": {"content": "a plan of events"}}]}).encode()})
        provider = providers.get_provider("openai", {"api_key": "sk-test", "model": "gpt-4o"}, max_retries=1)
        with patch.object(http, "urlopen", network):
            self.assertEqual(provider.call_api("Define: schedule"), "a plan of events")
        request = network.requests[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")
        self.assertEqual(network.body()["model"], "gpt-4o")
        self.assertEqual(network.body()["messages"], [{"role": "user", "content": "Define: schedule"}])

    def test_tts_request_carries_key_text_and_voice_and_returns_the_audio(self):
        network = Network({"https://openrouter.ai/api/v1/audio/speech": b"ID3-mp3-bytes"})
        config = {"openrouter_api_key": "or-test", "max_retries": 1, "replacements": {"sth": "something"}}
        with patch.object(http, "urlopen", network):
            self.assertEqual(tts_api.generate_audio("give sth up", config, "alloy"), b"ID3-mp3-bytes")
        self.assertEqual(network.requests[0].get_header("Authorization"), "Bearer or-test")
        body = network.body()
        self.assertEqual((body["input"], body["voice"], body["response_format"]),
                         ("give something up", "alloy", "mp3"))

    def test_tts_speed_is_omitted_at_default_for_models_without_speed_control(self):
        network = Network({"https://openrouter.ai/api/v1/audio/speech": b"ID3-mp3-bytes"})
        with patch.object(http, "urlopen", network):
            for speed in (1.0, 0.9):
                tts_api.generate_audio("hi", {"openrouter_api_key": "or-test", "speed": speed}, "alloy")
        self.assertNotIn("speed", network.body(0))
        self.assertEqual(network.body(1)["speed"], 0.9)

    def test_pcm_only_models_get_pcm_encoded_to_mp3_at_their_rate(self):
        pcm = b"{\x00" * 2400  # a first byte of "{" must not read as a JSON error
        encoded = []

        def encode_mp3(wav_path, mp3_path):  # stands in for Anki's lame
            with wave.open(wav_path) as wav:
                encoded.append((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                                wav.readframes(wav.getnframes())))
            with open(mp3_path, "wb") as file:
                file.write(b"ID3-mp3-bytes")

        network = Network({"https://openrouter.ai/api/v1/audio/speech": pcm})
        with patch.object(http, "urlopen", network), \
                patch.object(sys.modules["aqt.sound"], "_encode_mp3", encode_mp3, create=True):
            for model, voice in (("google/gemini-3.8-flash-tts", "Kore"), ("heygen/heygen-voice-1", "nadine")):
                config = {"openrouter_api_key": "or-test", "openrouter_model": model}
                self.assertEqual(tts_api.generate_audio("hi", config, voice), b"ID3-mp3-bytes")
        self.assertEqual([network.body(i)["response_format"] for i in (0, 1)], ["pcm", "pcm"])
        self.assertEqual(encoded, [(1, 2, 24000, pcm), (1, 2, 44100, pcm)])

    def test_no_voice_selected_asks_for_the_model_default_voice(self):
        # Fish Audio and ByteDance list no voices and reject "" as a voice.
        network = Network({"https://openrouter.ai/api/v1/audio/speech": b"ID3-mp3-bytes"})
        config = {"openrouter_api_key": "or-test", "openrouter_model": "fish-audio/s1", "voices": []}
        with patch.object(http, "urlopen", network):
            for voice in tts_config.get_voices(config):
                tts_api.generate_audio("hi", config, voice)
        self.assertEqual(len(network.requests), 1)
        self.assertNotIn("voice", network.body())


class WordQueueInputTests(unittest.TestCase):
    def test_pasted_list_keeps_phrases_whole_and_drops_repeats(self):
        parse = load("integrations", "word_queue.py").parse_words
        self.assertEqual(parse("give up, household income;  Mother\nmother\n\n look   after "),
                         ["give up", "household income", "Mother", "look after"])


if __name__ == "__main__":
    unittest.main()
