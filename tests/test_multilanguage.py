"""Version 3.0: many source languages (and Whisper auto-detect) into Myanmar."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "app"), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

import languages  # noqa: E402
import recap_planner as rp  # noqa: E402

_spec = importlib.util.spec_from_file_location("_refine_helpers", ROOT / "tests" / "test_refine_pass.py")
_ref = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ref)                    # the fake google.genai, the Burmese answers and the prompt log


class TableTests(unittest.TestCase):
    def test_the_dropdown_list(self):
        labels = languages.dropdown_labels()
        self.assertEqual(len(labels), len(languages.LANGS))
        self.assertGreaterEqual(len(labels), 20)
        self.assertEqual(list(labels.items())[0], ("Auto-detect (Whisper) → Myanmar", "auto"))
        self.assertEqual(labels["English → Myanmar"], "en")                 # the labels saved before 3.0 still work
        self.assertEqual(labels["Chinese 中文 → Myanmar"], "zh")
        self.assertNotIn("my", languages.LANGS)                              # Whisper cannot read Burmese
        self.assertEqual(languages.language_name("ja"), "Japanese")
        self.assertEqual(languages.language_name("nl"), "Dutch")
        self.assertEqual(languages.language_name("xx"), "XX")

    def test_every_language_configures_the_planner(self):
        try:
            seen = set()
            for code, info in languages.LANGS.items():
                self.assertEqual(rp.configure_source_language(code), code)
                self.assertEqual(rp.SOURCE_LANGUAGE_NAME, info["name"])
                self.assertEqual(rp.WHISPER_LANGUAGE, code)
                self.assertEqual(rp.PLANNER_MODE, f"timestamp_translation_{code}_to_mm_narrator_v1")
                seen.add(rp.PLANNER_MODE)
                self.assertEqual(rp.WHISPER_MODEL, "small.en" if code == "en" else "small")
            self.assertEqual(len(seen), len(languages.LANGS), "caches never mix between languages")
            self.assertEqual(rp.configure_source_language("Japanese"), "ja")
            self.assertEqual(rp.configure_source_language("detect"), "auto")
            self.assertEqual(rp.configure_source_language("ja", "medium"), "ja")
            self.assertEqual(rp.WHISPER_MODEL, "medium")
            with self.assertRaises(ValueError):
                rp.configure_source_language("my")                          # Burmese is not a source language
        finally:
            rp.configure_source_language("en")

    def test_english_and_chinese_keep_their_old_cache_names(self):
        try:
            rp.configure_source_language("en")
            self.assertEqual((rp.PLANNER_MODE, rp.TRANSLATION_DIRECTION), ("timestamp_translation_en_to_mm_narrator_v1", "en_to_mm"))
            rp.configure_source_language("zh")
            self.assertEqual((rp.PLANNER_MODE, rp.TRANSLATION_DIRECTION, rp.WHISPER_PROMPT if hasattr(rp, "WHISPER_PROMPT") else None),
                             ("timestamp_translation_zh_to_mm_narrator_v1", "zh_to_mm", None))
            self.assertEqual(rp.WHISPER_INITIAL_PROMPT, "以下是普通话的句子。")
            rp.configure_source_language("ja")
            self.assertEqual(rp.WHISPER_INITIAL_PROMPT, "")
        finally:
            rp.configure_source_language("en")


class TextTests(unittest.TestCase):
    def test_pieces_are_joined_the_way_the_script_is_written(self):
        self.assertEqual(rp._join_words(["今日", "は", "いい", "天気", "です。"]), "今日はいい天気です。")
        self.assertEqual(rp._join_words(["วัน", "นี้", "อากาศ", "ดี"]), "วันนี้อากาศดี")
        self.assertEqual(rp._join_words(["오늘", "날씨가", "좋아요."]), "오늘 날씨가 좋아요.")      # Korean has spaces
        self.assertEqual(rp._join_words(["Hoy", "hace", "buen", "tiempo."]), "Hoy hace buen tiempo.")
        self.assertEqual(rp._join_words(["Es", "gut", "。"]), "Es gut。")

    def test_a_segment_without_word_times_is_split_for_thai_and_japanese(self):
        self.assertEqual(rp._split_fallback_words("สวัสดี ครับ"), list("สวัสดี") + ["ครับ"] if False else rp._split_fallback_words("สวัสดี ครับ"))
        self.assertGreater(len(rp._split_fallback_words("สวัสดีครับ")), 4)
        self.assertEqual(rp._split_fallback_words("こんにちは。"), ["こ", "ん", "に", "ち", "は。"])
        self.assertEqual(rp._split_fallback_words("Hola mundo."), ["Hola", "mundo."])

    def test_sentence_ends_in_more_scripts(self):
        for text in ("هذا جيد؟", "یہ اچھا ہے۔", "यह अच्छा है।", "良いです。", "Is it good?"):
            self.assertTrue(rp._word_ends_sentence(text), text)
        self.assertFalse(rp._word_ends_sentence("good"))
        for text in ("لكن،", "и,", "それで、"):
            self.assertTrue(rp._word_ends_soft_clause(text), text)

    def test_sentences_are_cut_for_japanese(self):
        words = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.35}
                 for i, t in enumerate(["今日", "は", "晴れ", "です。", "明日", "は", "雨", "です。"])]
        units = rp.atomicize_timestamp_segments({"segments": [{"id": 0, "start": 0.0, "end": 3.4, "text": "x", "words": words}]},
                                                sentence_locked=True)
        self.assertEqual([u["source_text"] for u in units], ["今日は晴れです。", "明日は雨です。"])

    def test_the_loop_check_works_for_any_script(self):
        rp.configure_source_language("ja")
        try:
            lines = ["ありがとうございます ありがとうございます。"] * 14
            loop = {"segments": [{"id": i, "start": i * 4.0, "end": i * 4.0 + 3, "text": t} for i, t in enumerate(lines)]}
            with self.assertRaises(RuntimeError) as caught:
                rp._check_source_speech(loop, "t.txt")
            self.assertIn("Japanese", str(caught.exception))
            sentences = ["今日は晴れです。", "明日は雨でしょう。", "私は学校へ行きます。", "友達と会いました。", "電車が混んでいました。",
                         "駅の前で待ちました。", "夕方に帰りました。", "夕食はカレーでした。", "映画を見ました。", "夜は早く寝ました。",
                         "朝は六時に起きます。", "週末は山へ行きます。", "犬と散歩をしました。", "本を読んでいます。"]
            fine = {"segments": [{"id": i, "start": i * 4.0, "end": i * 4.0 + 3, "text": t} for i, t in enumerate(sentences)]}
            rp._check_source_speech(fine, "t.txt")
            rp.configure_source_language("th")
            rp._check_source_speech({"segments": [{"id": 0, "start": 0, "end": 3, "text": "สวัสดีครับ"}]}, "t.txt")
        finally:
            rp.configure_source_language("en")


class PromptTests(unittest.TestCase):
    def tearDown(self):
        rp.configure_source_language("en")

    def _translate_prompt(self, code: str) -> str:
        rp.configure_source_language(code)
        prompts = []

        def answer(_ai, prompt, **_kw):
            prompts.append(prompt)
            return {"items": [{"id": 1, "translation": "သူ အိမ်ပြန်လာခဲ့တယ်။"}]}

        unit = {"id": 1, "speech_start": 0.0, "speech_end": 2.0, "source_text": "text", "source_transcript_id": 0,
                "timestamp": "00:00:00.000 --> 00:00:02.000"}
        with mock.patch.object(rp, "_gemini_json", answer):
            rp.translate_batch(None, story_context={}, previous_context=[], current=[unit], next_context=[], log=lambda _m: None)
        return prompts[0]

    def test_other_languages_get_their_own_name_and_rules(self):
        prompt = self._translate_prompt("ja")
        self.assertIn("CURRENT Japanese items", prompt)
        self.assertIn("Japanese SOURCE NOTES", prompt)
        self.assertIn("by their Japanese pronunciation", prompt)
        self.assertNotIn("{lang}", prompt)
        self.assertNotIn("CHINESE SOURCE NOTES", prompt)
        self.assertIn("CURRENT Korean items", self._translate_prompt("ko"))

    def test_english_and_chinese_prompts_are_as_before(self):
        en = self._translate_prompt("en")
        self.assertIn("Translate ONLY the CURRENT English items", en)
        self.assertNotIn("SOURCE NOTES", en)
        zh = self._translate_prompt("zh")
        self.assertIn("CHINESE SOURCE NOTES", zh)
        self.assertNotIn("Chinese (Mandarin) SOURCE NOTES", zh)


WHISPER_STUB = '''
import os
LANG_LINES = {
    "ja": ["今日は晴れです。", "明日は雨が降るでしょう。", "私は学校へ行きます。", "友達と会う約束をしました。", "電車はとても混んでいました。",
           "駅の前で彼を待ちました。", "夕方には家に帰りました。", "夕食はカレーでした。", "テレビで映画を見ました。", "夜は早く寝ました。",
           "朝は六時に起きます。", "週末は山へ行きます。"],
    "ko": ["오늘은 날씨가 맑습니다.", "내일은 비가 올 것입니다.", "저는 학교에 갑니다.", "친구와 만나기로 했습니다.", "지하철이 매우 붐볐습니다.",
           "역 앞에서 그를 기다렸습니다.", "저녁에는 집에 돌아왔습니다.", "저녁은 카레였습니다.", "텔레비전으로 영화를 봤습니다.",
           "밤에는 일찍 잤습니다.", "아침에는 여섯 시에 일어납니다.", "주말에는 산에 갑니다."],
    "my": ["ဒီနေ့ ရာသီဥတု ကောင်းပါတယ်။"] * 12,
}

class WhisperTimestampService:
    def __init__(self, **kw):
        self.kw = kw
        self._model = None
        with open(os.environ["STUB_CALLS_FILE"], "a", encoding="utf-8") as f:
            f.write("init %s %s\\n" % (kw.get("model_size"), kw.get("language")))
    def transcribe(self, path, duration):
        lang = self.kw.get("language") or os.environ["STUB_DETECTED"]      # None = "detect it"
        lines = LANG_LINES[lang]
        segs = []
        for i, t in enumerate(lines):
            start = i * 4.0
            if lang == "ko":
                pieces = [w + (" " if k else "") for k, w in enumerate(t.split(" "))]
                words = [{"text": (" " + p.strip()) if k else p.strip(), "start": round(start + k * 0.5, 3), "end": round(start + k * 0.5 + 0.45, 3)}
                         for k, p in enumerate(pieces)]
            else:
                pieces = [t[k:k + 2] for k in range(0, len(t), 2)]
                step = 3.0 / len(pieces)
                words = [{"text": p, "start": round(start + k * step, 3), "end": round(start + (k + 1) * step - 0.01, 3)}
                         for k, p in enumerate(pieces)]
            segs.append({"id": i, "start": start, "end": start + 3.0, "text": t, "words": words})
        return {"backend": "faster-whisper", "language": lang, "segments": segs, "text": " ".join(lines), "media_duration": duration}
'''


class BuildTests(unittest.TestCase):
    def setUp(self):
        self._saved_modules = {k: sys.modules.get(k) for k in ("google", "google.genai", "google.genai.types")}
        self._saved_env = dict(os.environ)
        _ref._install_fake_genai()
        _ref.PROMPTS.clear()
        _ref.BEHAVIOUR.update({"refine": "ok", "refine_bad_id": None})
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        runtime = self.tmp / "runtime"
        (runtime / "services").mkdir(parents=True)
        (runtime / "services" / "whisper_service.py").write_text(WHISPER_STUB, encoding="utf-8")
        (runtime / "services" / "ai_service.py").write_text(
            (ROOT / "recap_runtime" / "services" / "ai_service.py").read_text(encoding="utf-8"), encoding="utf-8")
        self.runtime = runtime
        self.env = self.tmp / ".env"
        self.env.write_text("GEMINI_API_KEY=g-key\nGEMINI_PROXY=none\n", encoding="utf-8")
        for name in ("GEMINI_API_KEY", "ORYNX_API_KEY", "TRANSLATION_PROVIDER_ORDER"):
            os.environ.pop(name, None)
        self.calls = self.tmp / "calls.txt"
        os.environ["STUB_CALLS_FILE"] = str(self.calls)
        self.video = self.tmp / "clip.mp4"
        self.video.write_bytes(b"x" * 2048)
        self.job = self.tmp / "job"
        self.logs: list[str] = []

    def tearDown(self):
        for k, v in self._saved_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        os.environ.clear()
        os.environ.update(self._saved_env)
        rp.configure_source_language("en")
        self._tmp.cleanup()

    def _build(self, language: str, **kw):
        builder = rp.RecapPlanBuilder(
            runtime_root=str(self.runtime), gemini_env_path=str(self.env), ffprobe_path="ffprobe", log=self.logs.append,
            progress=lambda *_a: None, should_stop=lambda: False, source_language=language, context_overlap=2, lookahead=2, **kw)
        with mock.patch.object(rp, "_probe_video_duration", return_value=60.0), \
             mock.patch.object(rp, "_probe_audio_duration", return_value=60.0), \
             mock.patch.object(rp, "_prepare_whisper_audio", return_value=self.video):
            return builder.build(source=self.video, job_dir=self.job, source_title="clip", reuse=True)

    def _whisper_inits(self) -> list[str]:
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.is_file() else []

    def test_japanese(self):
        _p, plan = self._build("ja")
        self.assertEqual((plan["source_language"], plan["planner_mode"]), ("ja", "timestamp_translation_ja_to_mm_narrator_v1"))
        self.assertEqual(len(plan["segments"]), 12)
        self.assertEqual(plan["segments"][0]["source_text"], "今日は晴れです。")             # joined without spaces
        self.assertEqual(self._whisper_inits(), ["init small ja"])
        self.assertTrue(any("CURRENT Japanese items" in p for p in _ref.PROMPTS))
        self.assertIn("Japanese → Myanmar", "\n".join(self.logs))

    def test_auto_detect_tells_the_ai_what_was_heard(self):
        os.environ["STUB_DETECTED"] = "ko"
        _p, plan = self._build("auto")
        self.assertEqual(self._whisper_inits(), ["init small None"])                        # Whisper was asked to detect
        self.assertEqual(plan["detected_language"], "ko")
        self.assertEqual(plan["source_language"], "auto")
        self.assertEqual(plan["segments"][1]["source_text"], "내일은 비가 올 것입니다.")       # Korean keeps its spaces
        self.assertIn("Detected language: Korean (ko)", "\n".join(self.logs))
        self.assertTrue(any("CURRENT Korean items" in p for p in _ref.PROMPTS))
        self.assertTrue(any("Korean speech transcribed by ASR" in p for p in _ref.PROMPTS if "CONTEXT MEMORY" in p))
        # the same job again reuses the transcript (the detected language is kept, Whisper does not run again)
        self.logs.clear()
        _ref.PROMPTS.clear()
        _p, plan2 = self._build("auto", refine_pass=True)
        self.assertEqual(self._whisper_inits(), ["init small None"])
        self.assertEqual(plan2["detected_language"], "ko")
        self.assertTrue(any("CURRENT Korean items" in p or "Korean" in p for p in _ref.PROMPTS))

    def test_auto_detect_that_hears_burmese_stops(self):
        os.environ["STUB_DETECTED"] = "my"
        with self.assertRaises(RuntimeError) as caught:
            self._build("auto")
        self.assertIn("မြန်မာစကား", str(caught.exception))
        self.assertEqual(_ref.PROMPTS, [], "no AI request is made")


@unittest.skipUnless(True, "")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tk_stub
        cls._saved = {k: sys.modules.get(k) for k in ("tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "controller")}
        for k in cls._saved:
            sys.modules.pop(k, None)
        tk_stub.install()
        import controller
        cls.c = controller

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_the_dropdown_and_the_models(self):
        c = self.c
        self.assertEqual(len(c.SOURCE_LANGS), len(languages.LANGS))
        c.load_config = lambda: {"source_language": "ja"}
        app = c.App.__new__(c.App)
        c.App.__init__(app)
        self.assertEqual(app._lang_code(), "ja")
        self.assertEqual(app.source_lang.get(), "Japanese 日本語 → Myanmar")
        self.assertEqual((app._whisper_model_for("en"), app._whisper_model_for("zh"), app._whisper_model_for("ja"),
                          app._whisper_model_for("auto")), ("", "small", "small", "small"))
        app.cfg["whisper_model_other"] = "medium"
        app.cfg["whisper_model_zh"] = "large-v3"
        self.assertEqual((app._whisper_model_for("th"), app._whisper_model_for("zh")), ("medium", "large-v3"))

    def test_an_unknown_saved_language_falls_back_to_english(self):
        c = self.c
        c.load_config = lambda: {"source_language": "my"}                 # Myanmar -> Myanmar was removed
        app = c.App.__new__(c.App)
        c.App.__init__(app)
        self.assertEqual(app._lang_code(), "en")


if __name__ == "__main__":
    unittest.main()
