"""Gemini → Orynx fail-over and the Chinese → Myanmar source language."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import recap_planner as rp  # noqa: E402


def _unit(uid, start, end, text):
    return {"id": uid, "speech_start": start, "speech_end": end, "source_text": text,
            "source_transcript_id": uid - 1, "timestamp": f"{rp._fmt_ts(start)} --> {rp._fmt_ts(end)}"}


class FakeAI:
    """Just what _configure_gemini_key_pool / _gemini_json touch."""

    def __init__(self):
        self.provider = "gemini"
        self.proxy_calls = []

    def set_provider(self, provider):
        self.provider = provider

    def _enable_proxy(self):
        self.proxy_calls.append(("on", self.provider))

    def _disable_proxy(self):
        self.proxy_calls.append(("off", self.provider))


class FakeClient:
    """Client whose behaviour depends on the base URL: Gemini (none) fails, Orynx answers."""

    def __init__(self, api_key, http_options, gemini_error="429 RESOURCE_EXHAUSTED quota"):
        self.api_key = api_key
        self.base_url = (http_options or {}).get("baseUrl", "")
        self.gemini_error = gemini_error
        self.models = self

    def generate_content(self, model, contents):
        if not self.base_url:
            raise RuntimeError(self.gemini_error)
        return mock.Mock(text=json.dumps({"ok": True, "model": model, "key": self.api_key}))


class ProviderStageTests(unittest.TestCase):
    def test_default_order_is_gemini_then_orynx(self):
        stages = rp.build_provider_stages(gemini_keys=[("G1", "g1")], orynx_keys=[("O1", "o1")])
        providers = [s["provider"] for s in stages]
        self.assertEqual(providers, ["gemini"] * len(rp.GEMINI_MODEL_FALLBACK_CHAIN) + ["orynx"] * len(rp.ORYNX_MODEL_FALLBACK_CHAIN))
        self.assertEqual(stages[-1]["base_url"], "https://api.orynx.dev")
        self.assertEqual(stages[0]["base_url"], "")

    def test_order_can_put_orynx_first_or_alone(self):
        order = rp.parse_provider_order("orynx, gemini")
        stages = rp.build_provider_stages(gemini_keys=[("G1", "g1")], orynx_keys=[("O1", "o1")], order=order)
        self.assertEqual(stages[0]["provider"], "orynx")
        only = rp.build_provider_stages(gemini_keys=[("G1", "g1")], orynx_keys=[("O1", "o1")],
                                        order=rp.parse_provider_order("orynx"))
        self.assertEqual({s["provider"] for s in only}, {"orynx"})
        self.assertEqual(rp.parse_provider_order("nonsense"), ["gemini", "orynx"])

    def test_a_provider_without_keys_is_left_out(self):
        stages = rp.build_provider_stages(gemini_keys=[], orynx_keys=[("O1", "o1")])
        self.assertEqual({s["provider"] for s in stages}, {"orynx"})
        self.assertEqual(rp.build_provider_stages(gemini_keys=[], orynx_keys=[]), [])

    def test_orynx_keys_are_collected_in_numeric_order(self):
        env = {"ORYNX_API_KEY_3": "c", "ORYNX_API_KEY": "a", "ORYNX_API_KEY_2": "b", "ORYNX_API_KEY_9": "a", "OTHER": "x"}
        self.assertEqual([k for _l, k in rp.collect_orynx_keys(env)], ["a", "b", "c"])

    def test_credit_and_payment_errors_move_on_to_the_next_key(self):
        for text in ("402 Payment Required", "Insufficient credit on this key", "key expired", "HTTP 401"):
            self.assertTrue(rp._is_gemini_key_rejection(RuntimeError(text)), text)
        self.assertFalse(rp._is_gemini_key_rejection(RuntimeError("Expecting ':' delimiter")))


class FailoverTests(unittest.TestCase):
    def _configure(self, ai, gemini_error="429 RESOURCE_EXHAUSTED quota", orynx_keys=(("ORYNX_API_KEY", "o1"),)):
        stages = rp.build_provider_stages(gemini_keys=[("G1", "g1"), ("G2", "g2")], orynx_keys=list(orynx_keys))
        logs = []
        rp._configure_gemini_key_pool(
            ai, [("G1", "g1"), ("G2", "g2")],
            client_factory=lambda api_key, http_options: FakeClient(api_key, http_options, gemini_error),
            log=logs.append, stages=stages)
        return logs

    def test_used_up_gemini_keys_hand_over_to_orynx_with_the_same_request(self):
        ai = FakeAI()
        logs = self._configure(ai)
        self.assertEqual(ai.provider, "gemini")
        data = rp._gemini_json(ai, "translate this", log=logs.append)
        self.assertTrue(data["ok"])
        self.assertEqual(data["key"], "o1")
        self.assertEqual(ai.provider, "orynx")
        self.assertEqual(ai.text_model, rp.ORYNX_MODEL_FALLBACK_CHAIN[0])
        self.assertTrue(any("Orynx fallback" in line for line in logs))

    def test_a_503_skips_straight_to_the_next_stage(self):
        ai = FakeAI()
        logs = self._configure(ai, gemini_error="503 UNAVAILABLE high demand")
        data = rp._gemini_json(ai, "x", log=logs.append)
        self.assertEqual(data["key"], "o1")

    def test_the_proxy_follows_the_provider(self):
        ai = FakeAI()
        self._configure(ai)
        rp._gemini_json(ai, "x")
        # the last request went out while the provider was orynx
        self.assertIn(("on", "orynx"), ai.proxy_calls)

    def test_everything_exhausted_raises_the_pool_error(self):
        ai = FakeAI()
        stages = rp.build_provider_stages(gemini_keys=[("G1", "g1")], orynx_keys=[])
        rp._configure_gemini_key_pool(
            ai, [("G1", "g1")], log=lambda _m: None, stages=stages,
            client_factory=lambda api_key, http_options: FakeClient(api_key, http_options))
        with self.assertRaises(rp.GeminiKeyPoolExhaustedError):
            rp._gemini_json(ai, "x")

    def test_gemini_only_setup_behaves_as_before(self):
        ai = FakeAI()
        logs = []
        rp._configure_gemini_key_pool(
            ai, [("G1", "g1")], log=logs.append,
            client_factory=lambda api_key, http_options: FakeClient(api_key, http_options))
        self.assertEqual(ai.text_model, rp.GEMINI_MODEL_FALLBACK_CHAIN[0])
        self.assertEqual(ai._recap_model_pool_size, len(rp.GEMINI_MODEL_FALLBACK_CHAIN))


class ChineseTests(unittest.TestCase):
    def setUp(self):
        rp.configure_source_language("zh")

    def tearDown(self):
        rp.configure_source_language("en")

    def test_language_switch_changes_the_cache_identity(self):
        self.assertEqual(rp.PLANNER_MODE, "timestamp_translation_zh_to_mm_narrator_v1")
        self.assertEqual(rp.TRANSLATION_DIRECTION, "zh_to_mm")
        self.assertEqual((rp.WHISPER_MODEL, rp.WHISPER_LANGUAGE), ("small", "zh"))
        rp.configure_source_language("zh", "medium")
        self.assertEqual(rp.WHISPER_MODEL, "medium")
        rp.configure_source_language("en")
        self.assertEqual((rp.PLANNER_MODE, rp.WHISPER_MODEL), ("timestamp_translation_en_to_mm_narrator_v1", "small.en"))
        with self.assertRaises(ValueError):
            rp.configure_source_language("xx")

    def test_chinese_words_are_joined_without_spaces_english_with(self):
        self.assertEqual(rp._join_words(["我们", "今天", "去", "公园。"]), "我们今天去公园。")
        self.assertEqual(rp._join_words(["他", "说", "OK", "了。"]), "他说OK了。")
        self.assertEqual(rp._join_words(["Hello", "world."]), "Hello world.")
        self.assertEqual(rp._join_words(["Hi.", "Next", "one."]), "Hi. Next one.")

    def test_sentences_are_cut_at_chinese_punctuation(self):
        transcript = {"segments": [{
            "id": 0, "start": 0.0, "end": 8.0, "text": "我们今天去公园。他很高兴！",
            "words": [{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.45}
                      for i, t in enumerate(["我们", "今天", "去", "公园。", "他", "很", "高兴！"])],
        }]}
        units = rp.atomicize_timestamp_segments(transcript, sentence_locked=True)
        self.assertEqual([u["source_text"] for u in units], ["我们今天去公园。", "他很高兴！"])
        self.assertAlmostEqual(units[0]["speech_start"], 0.0)

    def test_a_segment_without_word_times_is_split_per_character(self):
        self.assertEqual(rp._split_fallback_words("他说：好的。"), ["他", "说：", "好", "的。"])
        self.assertEqual(rp._split_fallback_words("Hello world."), ["Hello", "world."])
        transcript = {"segments": [{"id": 0, "start": 0.0, "end": 4.0, "text": "你好吗？我很好。", "words": []}]}
        units = rp.atomicize_timestamp_segments(transcript, sentence_locked=True)
        self.assertEqual([u["source_text"] for u in units], ["你好吗？", "我很好。"])
        self.assertLess(units[0]["speech_end"], units[1]["speech_end"])

    def test_chinese_speech_check(self):
        lines = ["很久以前，山里住着一位老人。", "他每天清晨都会去河边打水。", "有一天，河里漂来一个木盒子。",
                 "老人好奇地打开了盒子。", "里面装着一把古老的宝剑。", "他不知道这把剑的来历。",
                 "村里的人都说它会带来灾难。", "可是老人并不相信这些话。", "夜里，宝剑忽然发出了光芒。",
                 "一个声音在他耳边响起。", "从今以后你就是我的主人。", "老人吓得坐在了地上。"]
        chinese = {"segments": [{"id": i, "start": i * 2.0, "end": i * 2.0 + 1.8, "text": t}
                                for i, t in enumerate(lines)]}
        rp._check_source_speech(chinese, "t.txt")                         # fine
        english = {"segments": [{"id": i, "start": i * 2.0, "end": i * 2.0 + 1.8,
                                 "text": f"This is sentence number {i} of an English video."} for i in range(12)]}
        with self.assertRaises(RuntimeError) as caught:
            rp._check_source_speech(english, "t.txt")
        self.assertIn("တရုတ်စကား", str(caught.exception))
        loop = {"segments": [{"id": i, "start": i * 2.0, "end": i * 2.0 + 1.8, "text": "我不会放弃的我不会放弃的。"}
                             for i in range(14)]}
        with self.assertRaises(RuntimeError):
            rp._check_source_speech(loop, "t.txt")

    def test_chinese_translation_prompt(self):
        prompts = []

        def answer(_ai, prompt, **_kw):
            prompts.append(prompt)
            return {"items": [{"id": 1, "translation": "သူ အိမ်ပြန်လာခဲ့တယ်။"}]}

        with mock.patch.object(rp, "_gemini_json", answer):
            out = rp.translate_batch(None, story_context={}, previous_context=[],
                                     current=[_unit(1, 0.0, 2.0, "他回家了。")], next_context=[], log=lambda _m: None)
        self.assertEqual(out[0]["translation"], "သူ အိမ်ပြန်လာခဲ့တယ်။")
        self.assertIn("CURRENT Chinese (Mandarin) items", prompts[0])
        self.assertIn("CHINESE SOURCE NOTES", prompts[0])
        self.assertNotIn("CURRENT English items", prompts[0])

    def test_chinese_characters_left_in_the_burmese_are_asked_again(self):
        self.assertTrue(rp._foreign_letters("张伟 က ပြန်လာတယ်"))
        answers = [{"items": [{"id": 1, "translation": "张伟 အိမ်ပြန်လာတယ်။"}]},
                   {"items": [{"id": 1, "translation": "ဇန်ဝေ့ အိမ်ပြန်လာတယ်။"}]}]
        prompts = []

        def answer(_ai, prompt, **_kw):
            prompts.append(prompt)
            return answers[len(prompts) - 1]

        with mock.patch.object(rp, "_gemini_json", answer):
            out = rp.translate_batch(None, story_context={}, previous_context=[],
                                     current=[_unit(1, 0.0, 2.0, "张伟回家了。")], next_context=[], log=lambda _m: None)
        self.assertEqual(out[0]["translation"], "ဇန်ဝေ့ အိမ်ပြန်လာတယ်။")
        self.assertIn("letters of another script", prompts[1])

    def test_english_prompt_is_unchanged_after_switching_back(self):
        rp.configure_source_language("en")
        prompts = []

        def answer(_ai, prompt, **_kw):
            prompts.append(prompt)
            return {"items": [{"id": 1, "translation": "သူ အိမ်ပြန်လာခဲ့တယ်။"}]}

        with mock.patch.object(rp, "_gemini_json", answer):
            rp.translate_batch(None, story_context={}, previous_context=[], current=[_unit(1, 0.0, 2.0, "He came home.")],
                               next_context=[], log=lambda _m: None)
        self.assertIn("Translate ONLY the CURRENT English items", prompts[0])
        self.assertNotIn("CHINESE SOURCE NOTES", prompts[0])


if __name__ == "__main__":
    unittest.main()
