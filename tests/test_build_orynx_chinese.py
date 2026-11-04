"""End-to-end planner run (no network, no GPU): Chinese video, every Gemini request fails with 429, Orynx answers.

The real recap_planner.build() and the real ai_service.py run; google.genai and Whisper are replaced by fakes.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import types as pytypes
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import recap_planner as rp  # noqa: E402

CALLS: list[dict] = []


class _Types(pytypes.SimpleNamespace):
    class HttpOptions:
        def __init__(self, base_url=None, **kw):
            self.base_url = base_url


_WORDS = ["တောင်ပေါ်ရွာမှာ", "မြစ်ကမ်းဘေးကို", "သစ်သားသေတ္တာတစ်လုံး", "ဓားတစ်လက်ကို", "လင်းလက်တဲ့အလင်းရောင်",
          "နားထဲကို ရောက်လာတဲ့အသံ", "ရွာသားအားလုံးက", "ကံဆိုးမှုတွေ ဖြစ်လာမယ်လို့", "ညဘက်အချိန်မှာ", "အသက်ကြီးတဲ့အဘိုးအိုက",
          "ထူးဆန်းတဲ့စွမ်းအားကို", "ကြောက်လန့်တကြား"]


def _burmese_line(i: int) -> str:
    """A different Burmese line per ID (the planner rejects near-identical neighbours)."""
    return f"ဇန်ဝေ့ {_WORDS[i % 12]} {_WORDS[(i * 5 + 3) % 12]} {_WORDS[(i * 7 + 1) % 12]} ပြောပြတယ်။"


class _FakeModels:
    def __init__(self, api_key, base_url):
        self.api_key, self.base_url = api_key, base_url

    def generate_content(self, model, contents):
        CALLS.append({"key": self.api_key, "base_url": self.base_url, "model": model})
        if not self.base_url:                                  # "Google": quota used up
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        if "You are building CONTEXT MEMORY" in contents:
            body = {"characters": ["张伟"], "relationships": [], "places": [], "terms": [],
                    "plot_state": [], "name_consistency": ["张伟 → ဇန်ဝေ့"], "unresolved": []}
        elif "TRANSLATION AUDITOR" in contents:
            ids = json.loads(re.search(r"exact required CURRENT ID sequence is: (\[[^\]]*\])", contents).group(1))
            body = {"checks": [{"id": i, "status": "pass"} for i in ids]}
        else:
            ids = json.loads(re.search(
                r"Copy this exact ID sequence without dropping, renumbering, or inventing any ID:\n(\[[^\]]*\])", contents).group(1))
            body = {"items": [{"id": i, "translation": _burmese_line(i)} for i in ids]}
        return mock.Mock(text=json.dumps(body, ensure_ascii=False))


class _FakeClient:
    def __init__(self, api_key=None, http_options=None):
        opts = http_options
        base = opts.get("baseUrl", "") if isinstance(opts, dict) else (getattr(opts, "base_url", "") or "")
        self.models = _FakeModels(api_key, base)


def _install_fake_genai():
    google = pytypes.ModuleType("google")
    genai = pytypes.ModuleType("google.genai")
    genai.Client = _FakeClient
    genai.types = _Types()
    google.genai = genai
    sys.modules.update({"google": google, "google.genai": genai, "google.genai.types": genai.types})


WHISPER_STUB = '''
class WhisperTimestampService:
    def __init__(self, **kw):
        self.kw = kw
        self._model = None
    def transcribe(self, path, duration):
        lines = ["很久以前，山里住着一位老人。", "他每天清晨都会去河边打水。", "有一天，河里漂来一个木盒子。",
                 "老人好奇地打开了盒子。", "里面装着一把古老的宝剑。", "他不知道这把剑的来历。",
                 "村里的人都说它会带来灾难。", "可是老人并不相信这些话。", "夜里，宝剑忽然发出了光芒。",
                 "一个声音在他耳边响起。", "从今以后你就是我的主人。", "老人吓得坐在了地上。"]
        segs = []
        for i, t in enumerate(lines):
            start = i * 4.0
            chars = [c for c in t]
            step = 3.0 / len(chars)
            words = [{"text": c, "start": round(start + k * step, 3), "end": round(start + (k + 1) * step - 0.01, 3)}
                     for k, c in enumerate(chars)]
            segs.append({"id": i, "start": start, "end": start + 3.0, "text": t, "words": words})
        return {"backend": "faster-whisper", "model": "small", "language": "zh", "segments": segs,
                "text": "".join(lines), "media_duration": duration, "initial_prompt_seen": self.kw.get("initial_prompt")}
'''


class BuildTests(unittest.TestCase):
    def setUp(self):
        self._saved_modules = {k: sys.modules.get(k) for k in ("google", "google.genai", "google.genai.types")}
        self._saved_env = dict(os.environ)
        _install_fake_genai()
        CALLS.clear()

    def tearDown(self):
        for k, v in self._saved_modules.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        os.environ.clear()
        os.environ.update(self._saved_env)
        rp.configure_source_language("en")

    def test_chinese_video_falls_over_from_gemini_to_orynx(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            runtime = tmp / "runtime"
            (runtime / "services").mkdir(parents=True)
            (runtime / "services" / "whisper_service.py").write_text(WHISPER_STUB, encoding="utf-8")
            (runtime / "services" / "ai_service.py").write_text(
                (ROOT / "recap_runtime" / "services" / "ai_service.py").read_text(encoding="utf-8"), encoding="utf-8")
            env = tmp / ".env"
            env.write_text("GEMINI_API_KEY=g-key\nORYNX_API_KEY=o-key\nGEMINI_PROXY=none\n", encoding="utf-8")
            for name in ("GEMINI_API_KEY", "ORYNX_API_KEY", "TRANSLATION_PROVIDER_ORDER", "ORYNX_MODELS", "GEMINI_MODELS"):
                os.environ.pop(name, None)
            video = tmp / "clip.mp4"
            video.write_bytes(b"x" * 2048)
            logs: list[str] = []
            builder = rp.RecapPlanBuilder(
                runtime_root=str(runtime), gemini_env_path=str(env), ffprobe_path="ffprobe", log=logs.append,
                progress=lambda *_a: None, should_stop=lambda: False, source_language="zh", context_overlap=2, lookahead=2)
            with mock.patch.object(rp, "_probe_video_duration", return_value=60.0), \
                 mock.patch.object(rp, "_probe_audio_duration", return_value=60.0), \
                 mock.patch.object(rp, "_prepare_whisper_audio", return_value=video):
                plan_path, plan = builder.build(source=video, job_dir=tmp / "job", source_title="clip", reuse=False)

            text = "\n".join(logs)
            self.assertEqual(plan["source_language"], "zh")
            self.assertEqual(plan["translation_direction"], "zh_to_mm")
            self.assertEqual(plan["planner_mode"], "timestamp_translation_zh_to_mm_narrator_v1")
            self.assertEqual(len(plan["segments"]), 12)
            self.assertTrue(all(seg["source_text"].endswith("。") and " " not in seg["source_text"]
                                for seg in plan["segments"]), [s["source_text"] for s in plan["segments"]])
            self.assertTrue(all("ဇန်ဝေ့" in seg["narration"] for seg in plan["segments"]))
            # Gemini was tried first (every key/model failed), then Orynx answered everything that followed
            self.assertEqual(CALLS[0]["base_url"], "")
            self.assertEqual(CALLS[0]["key"], "g-key")
            orynx = [c for c in CALLS if c["base_url"]]
            self.assertTrue(orynx)
            self.assertTrue(all(c["key"] == "o-key" and c["base_url"] == "https://api.orynx.dev" for c in orynx))
            self.assertEqual(orynx[0]["model"], "gemini-3.8-flash")
            self.assertIn("Orynx fallback", text)
            self.assertIn("Chinese (Mandarin) → Myanmar", text)
            transcript = json.loads((tmp / "job" / "whisper_transcript.json").read_text(encoding="utf-8"))
            self.assertEqual(transcript["initial_prompt_seen"], "以下是普通话的句子。")
            self.assertEqual(transcript["language"], "zh")

    def test_orynx_only_setup_needs_no_gemini_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            runtime = tmp / "runtime"
            (runtime / "services").mkdir(parents=True)
            (runtime / "services" / "whisper_service.py").write_text(WHISPER_STUB, encoding="utf-8")
            (runtime / "services" / "ai_service.py").write_text(
                (ROOT / "recap_runtime" / "services" / "ai_service.py").read_text(encoding="utf-8"), encoding="utf-8")
            env = tmp / ".env"
            env.write_text("ORYNX_API_KEY=o-key\n", encoding="utf-8")
            for name in ("GEMINI_API_KEY", "ORYNX_API_KEY", "TRANSLATION_PROVIDER_ORDER"):
                os.environ.pop(name, None)
            video = tmp / "clip.mp4"
            video.write_bytes(b"x" * 2048)
            builder = rp.RecapPlanBuilder(
                runtime_root=str(runtime), gemini_env_path=str(env), ffprobe_path="ffprobe", log=lambda _m: None,
                progress=lambda *_a: None, should_stop=lambda: False, source_language="zh")
            with mock.patch.object(rp, "_probe_video_duration", return_value=60.0), \
                 mock.patch.object(rp, "_probe_audio_duration", return_value=60.0), \
                 mock.patch.object(rp, "_prepare_whisper_audio", return_value=video):
                _p, plan = builder.build(source=video, job_dir=tmp / "job", source_title="clip", reuse=False)
            self.assertEqual(len(plan["segments"]), 12)
            self.assertTrue(CALLS and all(c["base_url"] == "https://api.orynx.dev" for c in CALLS))

    def test_no_keys_at_all_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            runtime = tmp / "runtime"
            (runtime / "services").mkdir(parents=True)
            (runtime / "services" / "whisper_service.py").write_text(WHISPER_STUB, encoding="utf-8")
            (runtime / "services" / "ai_service.py").write_text("x = 1\n", encoding="utf-8")
            env = tmp / ".env"
            env.write_text("# nothing\n", encoding="utf-8")
            for name in ("GEMINI_API_KEY", "ORYNX_API_KEY"):
                os.environ.pop(name, None)
            video = tmp / "clip.mp4"
            video.write_bytes(b"x" * 2048)
            builder = rp.RecapPlanBuilder(
                runtime_root=str(runtime), gemini_env_path=str(env), ffprobe_path="ffprobe", log=lambda _m: None,
                progress=lambda *_a: None, should_stop=lambda: False)
            with mock.patch.object(rp, "_probe_video_duration", return_value=60.0), \
                 mock.patch.object(rp, "_probe_audio_duration", return_value=60.0):
                with self.assertRaises(RuntimeError) as caught:
                    builder.build(source=video, job_dir=tmp / "job", source_title="clip", reuse=False)
            self.assertIn("ORYNX_API_KEY", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
