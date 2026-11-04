"""AI refine pass: a second AI pass that polishes the translated Burmese, never making the plan worse."""
from __future__ import annotations

import importlib.util
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

_spec = importlib.util.spec_from_file_location("_zh_stub", ROOT / "tests" / "test_build_orynx_chinese.py")
_zh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_zh)                       # only for its fake Whisper stub (a Chinese video)
WHISPER_STUB = _zh.WHISPER_STUB

PROMPTS: list[str] = []
BEHAVIOUR = {"refine": "ok", "refine_bad_id": None}


class _Types(pytypes.SimpleNamespace):
    class HttpOptions:
        def __init__(self, base_url=None, **kw):
            self.base_url = base_url


_WORDS = ["တောင်ပေါ်ရွာမှာ", "မြစ်ကမ်းဘေးကို", "သစ်သားသေတ္တာတစ်လုံး", "ဓားတစ်လက်ကို", "လင်းလက်တဲ့အလင်းရောင်",
          "နားထဲကို ရောက်လာတဲ့အသံ", "ရွာသားအားလုံးက", "ကံဆိုးမှုတွေ ဖြစ်လာမယ်လို့", "ညဘက်အချိန်မှာ", "အသက်ကြီးတဲ့အဘိုးအိုက",
          "ထူးဆန်းတဲ့စွမ်းအားကို", "ကြောက်လန့်တကြား"]


def first_pass(i: int) -> str:
    return f"ဇန်ဝေ့ {_WORDS[i % 12]} {_WORDS[(i * 5 + 3) % 12]} {_WORDS[(i * 7 + 1) % 12]} ပြောပြတယ်။"


def polished(i: int) -> str:
    return first_pass(i).replace("ပြောပြတယ်။", "ပြောပြပါတယ်။")


class _Models:
    def generate_content(self, model, contents):
        PROMPTS.append(contents)
        if "You are building CONTEXT MEMORY" in contents:
            body = {"characters": ["ဇန်ဝေ့"], "relationships": [], "places": [], "terms": [], "plot_state": [],
                    "name_consistency": ["张伟 → ဇန်ဝေ့"], "unresolved": []}
        elif "TRANSLATION AUDITOR" in contents:
            ids = json.loads(re.search(r"exact required CURRENT ID sequence is: (\[[^\]]*\])", contents).group(1))
            body = {"checks": [{"id": i, "status": "pass"} for i in ids]}
        elif "BURMESE NARRATION POLISHER" in contents:
            if BEHAVIOUR["refine"] == "exhausted":
                raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
            block = contents.split("CURRENT ITEMS — POLISH ALL OF THESE, ONE-FOR-ONE:\n", 1)[1].split("\n\nNEXT CONTEXT", 1)[0]
            ids = [int(i) for i in re.findall(r"\[ID (\d+)\]", block)]
            items = []
            for i in ids:
                text = polished(i)
                if i == BEHAVIOUR["refine_bad_id"]:
                    text = text + " This English sentence should never be kept in the Burmese narration."   # fails the checks
                items.append({"id": i, "translation": text})
            body = {"items": items}
        else:
            ids = json.loads(re.search(
                r"Copy this exact ID sequence without dropping, renumbering, or inventing any ID:\n(\[[^\]]*\])", contents).group(1))
            body = {"items": [{"id": i, "translation": first_pass(i)} for i in ids]}
        return mock.Mock(text=json.dumps(body, ensure_ascii=False))


class _Client:
    def __init__(self, api_key=None, http_options=None):
        self.models = _Models()


def _install_fake_genai():
    google = pytypes.ModuleType("google")
    genai = pytypes.ModuleType("google.genai")
    genai.Client = _Client
    genai.types = _Types()
    google.genai = genai
    sys.modules.update({"google": google, "google.genai": genai, "google.genai.types": genai.types})


class RefineTests(unittest.TestCase):
    def setUp(self):
        self._saved_modules = {k: sys.modules.get(k) for k in ("google", "google.genai", "google.genai.types")}
        self._saved_env = dict(os.environ)
        _install_fake_genai()
        PROMPTS.clear()
        BEHAVIOUR.update({"refine": "ok", "refine_bad_id": None})
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

    def _build(self, refine: bool):
        builder = rp.RecapPlanBuilder(
            runtime_root=str(self.runtime), gemini_env_path=str(self.env), ffprobe_path="ffprobe", log=self.logs.append,
            progress=lambda *_a: None, should_stop=lambda: False, source_language="zh", context_overlap=2, lookahead=2,
            refine_pass=refine)
        with mock.patch.object(rp, "_probe_video_duration", return_value=60.0), \
             mock.patch.object(rp, "_probe_audio_duration", return_value=60.0), \
             mock.patch.object(rp, "_prepare_whisper_audio", return_value=self.video):
            return builder.build(source=self.video, job_dir=self.job, source_title="clip", reuse=True)

    def _count(self, marker: str) -> int:
        return sum(1 for p in PROMPTS if marker in p)

    def test_off_by_default_changes_nothing(self):
        _p, plan = self._build(False)
        self.assertEqual(self._count("BURMESE NARRATION POLISHER"), 0)
        self.assertEqual([s["narration"] for s in plan["segments"]], [first_pass(i) for i in range(1, 13)])
        self.assertFalse(plan["translation_rules"]["ai_refine_pass"])
        self.assertFalse((self.job / "refine_checkpoint.json").exists())
        self.assertFalse(json.loads((self.job / "planner_checkpoint.json").read_text(encoding="utf-8"))["refined"])

    def test_on_polishes_every_line_and_keeps_the_timing(self):
        _p, first = self._build(False)
        PROMPTS.clear()
        _p, plan = self._build(True)
        self.assertGreaterEqual(self._count("BURMESE NARRATION POLISHER"), 1)
        self.assertEqual(self._count("CONTEXT-AWARE BURMESE NARRATION TRANSLATOR"), 0, "translation must not be redone")
        self.assertEqual([s["narration"] for s in plan["segments"]], [polished(i) for i in range(1, 13)])
        self.assertEqual([(s["video_start"], s["video_end"]) for s in plan["segments"]],
                         [(s["video_start"], s["video_end"]) for s in first["segments"]])
        self.assertEqual([s["source_text"] for s in plan["segments"]], [s["source_text"] for s in first["segments"]])
        self.assertTrue(plan["translation_rules"]["ai_refine_pass"])
        self.assertTrue(json.loads((self.job / "planner_checkpoint.json").read_text(encoding="utf-8"))["refined"])
        self.assertIn("Refine: 12/12 line(s) polished", "\n".join(self.logs))
        # the prompt shows the source as ground truth and the first-pass Burmese to polish
        polish = next(p for p in PROMPTS if "BURMESE NARRATION POLISHER" in p)
        self.assertIn("SOURCE: ", polish)
        self.assertIn("OUTPUT: ", polish)
        self.assertIn("Chinese (Mandarin)", polish)

    def test_toggling_reuses_the_translation_and_the_refine_checkpoint(self):
        self._build(True)
        PROMPTS.clear()
        _p, plan = self._build(False)                                   # back to the first-pass text
        self.assertEqual(PROMPTS, [])
        self.assertEqual([s["narration"] for s in plan["segments"]], [first_pass(i) for i in range(1, 13)])
        _p, plan = self._build(True)                                    # refined again, from the checkpoint
        self.assertEqual(PROMPTS, [], "no new AI request: the refine checkpoint is reused")
        self.assertEqual([s["narration"] for s in plan["segments"]], [polished(i) for i in range(1, 13)])
        self.assertIn("AI refine resume", "\n".join(self.logs))

    def test_a_line_that_fails_a_check_keeps_its_first_pass_text(self):
        BEHAVIOUR["refine_bad_id"] = 5
        _p, plan = self._build(True)
        narrations = [s["narration"] for s in plan["segments"]]
        self.assertEqual(narrations[4], first_pass(5))
        self.assertEqual([n for i, n in enumerate(narrations) if i != 4], [polished(i) for i in range(1, 13) if i != 5])
        self.assertIn("kept as first-pass", "\n".join(self.logs))

    def test_running_out_of_ai_only_skips_the_refine(self):
        BEHAVIOUR["refine"] = "exhausted"
        _p, plan = self._build(True)
        self.assertEqual([s["narration"] for s in plan["segments"]], [first_pass(i) for i in range(1, 13)])
        self.assertFalse(plan["translation_rules"]["ai_refine_pass"])
        self.assertFalse(json.loads((self.job / "planner_checkpoint.json").read_text(encoding="utf-8"))["refined"])
        self.assertIn("AI refine stopped", "\n".join(self.logs))
        # the next START (AI available again) finishes the refine without redoing the translation
        BEHAVIOUR["refine"] = "ok"
        PROMPTS.clear()
        _p, plan = self._build(True)
        self.assertEqual(self._count("CONTEXT-AWARE BURMESE NARRATION TRANSLATOR"), 0)
        self.assertEqual([s["narration"] for s in plan["segments"]], [polished(i) for i in range(1, 13)])


if __name__ == "__main__":
    unittest.main()
