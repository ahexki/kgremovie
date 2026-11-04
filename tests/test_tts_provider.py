"""TTS provider: Edge TTS (default) or Meta MMS (offline) with an automatic Edge TTS fallback."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import core  # noqa: E402
import mms_tts  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _sine_wav(path: Path, seconds: float, hz: int = 300) -> str:
    rate = 24000
    t = np.arange(int(rate * seconds)) / rate
    data = (np.sin(2 * np.pi * hz * t) * 12000).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(data.tobytes())
    return str(path)


class TextPrepTests(unittest.TestCase):
    def test_digits_are_spelt_out_and_punctuation_mapped(self):
        self.assertEqual(mms_tts.prepare_text("၂၀၂၅ ခု၊ ဒီနေ့။"), "နှစ် သုည နှစ် ငါး ခု, ဒီနေ့.")
        self.assertIn("သုံး လေး", mms_tts.prepare_text("34"))
        with self.assertRaises(RuntimeError):
            mms_tts.prepare_text("... !!!")

    def test_chunks_are_short_and_lose_nothing(self):
        long = "။ ".join(["မြန်မာစာ စာကြောင်း " * 6 + "တစ်ကြောင်း"] * 8) + "။"
        chunks = mms_tts.split_chunks(mms_tts.prepare_text(long))
        self.assertTrue(len(chunks) > 3)
        self.assertTrue(all(len(c) <= mms_tts.MAX_CHUNK_CHARS for c in chunks), [len(c) for c in chunks])
        flat = lambda t: "".join(ch for ch in t if ch.isalpha())
        self.assertEqual(flat("".join(chunks)), flat(mms_tts.prepare_text(long)))
        self.assertEqual(mms_tts.split_chunks("တိုတို။"), ["တိုတို။"])
        no_space = "က" * 500
        self.assertTrue(all(len(c) <= mms_tts.MAX_CHUNK_CHARS for c in mms_tts.split_chunks(no_space)))

    def test_speed_maps_to_speaking_rate(self):
        self.assertEqual(mms_tts.rate_to_speaking_rate("+0%"), 1.0)
        self.assertAlmostEqual(mms_tts.rate_to_speaking_rate("+25%"), 1.25)
        self.assertAlmostEqual(mms_tts.rate_to_speaking_rate("-30%"), 0.7)
        self.assertEqual(mms_tts.rate_to_speaking_rate("-90%"), 0.5)
        self.assertEqual(mms_tts.rate_to_speaking_rate("garbage"), 1.0)

    def test_provider_names(self):
        self.assertEqual(core.parse_tts_provider("Meta MMS (offline)"), "mms")
        self.assertEqual(core.parse_tts_provider("mms"), "mms")
        for value in ("Edge TTS", "edge", "", None, "something else"):
            self.assertEqual(core.parse_tts_provider(value), "edge")


class _FakeTensor:
    def __init__(self, array):
        self.array = np.asarray(array)
        self.shape = self.array.shape
    def to(self, _device): return self
    def float(self): return self
    def cpu(self): return self
    def numpy(self): return self.array
    def __getitem__(self, i): return _FakeTensor(self.array[i])


def _install_fake_transformers():
    """torch + transformers stand-ins: the 'voice' is a tone whose length follows the number of letters."""
    seeds: list[int] = []
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch.manual_seed = lambda s: seeds.append(int(s))
    class _NoGrad:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    torch.no_grad = lambda: _NoGrad()
    tf = types.ModuleType("transformers")
    class Tok:
        @classmethod
        def from_pretrained(cls, _id): return cls()
        def __call__(self, text, return_tensors=None):
            ids = [ord(c) for c in text if c.isalpha()]
            return {"input_ids": _FakeTensor(np.array([ids], dtype=np.int64))}
    class Vits:
        speaking_rate = 1.0
        config = types.SimpleNamespace(sampling_rate=16000)
        @classmethod
        def from_pretrained(cls, _id): return cls()
        def to(self, _d): return self
        def eval(self): return self
        def __call__(self, input_ids):
            n = int(input_ids.shape[-1])
            t = np.arange(int(16000 * 0.02 * n)) / 16000
            return types.SimpleNamespace(waveform=_FakeTensor((np.sin(2 * np.pi * 220 * t) * 0.3)[None, :].astype(np.float32)))
    tf.AutoTokenizer, tf.VitsModel = Tok, Vits
    saved = {k: sys.modules.get(k) for k in ("torch", "transformers")}
    sys.modules.update({"torch": torch, "transformers": tf})
    return seeds, saved


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg is not installed")
class EngineTests(unittest.TestCase):
    def setUp(self):
        self.seeds, self._saved = _install_fake_transformers()
        import importlib.util as iu
        self._find = iu.find_spec
        iu.find_spec = lambda name, *a, **k: object() if name in ("torch", "transformers") else self._find(name, *a, **k)

    def tearDown(self):
        import importlib.util as iu
        iu.find_spec = self._find
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_engine_makes_a_24k_mono_wav_that_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = mms_tts.MMSTTSEngine(ffmpeg=FFMPEG, work_dir=Path(tmp), rate="+20%")
            self.assertAlmostEqual(eng.model.speaking_rate, 1.2)
            a = Path(eng.generate_channel99_voice("မင်္ဂလာပါ။ ဒီနေ့ ၂ ခု။"))
            b = Path(eng.generate_channel99_voice("မင်္ဂလာပါ။ ဒီနေ့ ၂ ခု။"))
            with wave.open(str(a)) as w:
                self.assertEqual((w.getnchannels(), w.getframerate(), w.getsampwidth()), (1, 24000, 2))
            self.assertGreater(core.probe_duration(FFPROBE, a), 0.1)
            self.assertEqual(hashlib.sha1(a.read_bytes()).hexdigest(), hashlib.sha1(b.read_bytes()).hexdigest())
            self.assertEqual(len(set(self.seeds)), 1)             # one seed per text: the same text sounds the same
            self.assertFalse(list(Path(tmp).glob("*_raw.wav")))

    def test_long_text_is_spoken_in_chunks_with_pauses(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = mms_tts.MMSTTSEngine(ffmpeg=FFMPEG, work_dir=Path(tmp))
            one = core.probe_duration(FFPROBE, Path(eng.generate_channel99_voice("က" * 100 + "။")))
            text = "။ ".join(["က" * 100] * 4) + "။"
            four = core.probe_duration(FFPROBE, Path(eng.generate_channel99_voice(text)))
            self.assertGreater(four, one * 3.5)

    def test_missing_packages_give_a_clear_message(self):
        import importlib.util as iu
        iu.find_spec = lambda name, *a, **k: None if name == "torch" else (
            object() if name == "transformers" else self._find(name, *a, **k))
        with self.assertRaises(RuntimeError) as caught:
            mms_tts.MMSTTSEngine(ffmpeg=FFMPEG, work_dir=Path(tempfile.gettempdir()) / "x")
        self.assertIn("INSTALL_MMS.bat", str(caught.exception))
        self.assertIn("torch", str(caught.exception))


class _FakeEngine:
    def __init__(self, name, tmp, fail_on=()):
        self.name, self.tmp, self.fail_on, self.calls = name, tmp, set(fail_on), []
    def generate_channel99_voice(self, text, voice=""):
        self.calls.append((text, voice))
        if any(bad in text for bad in self.fail_on):
            raise RuntimeError(f"{self.name} cannot say {text!r}")
        return _sine_wav(Path(self.tmp) / f"{self.name}_{len(self.calls)}.wav", 1.0, 300 if self.name == "mms" else 500)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.logs: list[str] = []

    def tearDown(self):
        self._tmp.cleanup()

    def test_edge_provider_never_touches_mms(self):
        edge = _FakeEngine("edge", self.tmp)
        r = core.TTSRouter(provider="edge", edge_factory=lambda: edge, mms_factory=lambda: self.fail("no MMS"), log=self.logs.append)
        r.generate("မင်္ဂလာပါ", "my-MM-ThihaNeural")
        self.assertEqual((r.last_provider, edge.calls[0][1]), ("edge", "my-MM-ThihaNeural"))

    def test_mms_provider_uses_mms_and_edge_is_never_built(self):
        mms = _FakeEngine("mms", self.tmp)
        r = core.TTSRouter(provider="mms", edge_factory=lambda: self.fail("Edge must not be built"), mms_factory=lambda: mms)
        r.generate("မင်္ဂလာပါ", "my-MM-ThihaNeural")
        self.assertEqual(r.last_provider, "mms")

    def test_a_line_mms_fails_on_goes_to_edge_the_rest_stay_mms(self):
        mms, edge = _FakeEngine("mms", self.tmp, fail_on=("ဆိုး",)), _FakeEngine("edge", self.tmp)
        r = core.TTSRouter(provider="mms", edge_factory=lambda: edge, mms_factory=lambda: mms, log=self.logs.append)
        r.generate("ကောင်း", "my-MM-NilarNeural"); self.assertEqual(r.last_provider, "mms")
        r.generate("ဆိုး", "my-MM-NilarNeural"); self.assertEqual(r.last_provider, "edge_fallback")
        r.generate("ကောင်းပြန်", "my-MM-NilarNeural"); self.assertEqual(r.last_provider, "mms")
        self.assertEqual(edge.calls, [("ဆိုး", "my-MM-NilarNeural")])
        self.assertEqual(r.fallback_lines, 1)
        self.assertTrue(any("Edge TTS" in line and "speaks it" in line for line in self.logs))

    def test_mms_that_cannot_load_means_edge_for_everything(self):
        edge = _FakeEngine("edge", self.tmp)
        def broken():
            raise RuntimeError("torch မရှိသေးပါ")
        r = core.TTSRouter(provider="mms", edge_factory=lambda: edge, mms_factory=broken, log=self.logs.append)
        self.assertTrue(r.mms_broken)
        r.generate("a", "v"); r.generate("b", "v")
        self.assertEqual((r.last_provider, len(edge.calls)), ("edge_fallback", 2))
        self.assertTrue(any("Edge TTS နဲ့ ဆက်လုပ်မယ်" in line for line in self.logs))


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg is not installed")
class SmartSyncTests(unittest.TestCase):
    """The real EdgeSmartSync.run() with fake voices: provider choice, fallback, checkpoint and re-run."""

    def _job(self, tmp: Path):
        src = tmp / "clip.mp4"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=12",
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", str(src)], check=True)
        job = tmp / "job"
        job.mkdir()
        plan = {"segments": [
            {"video_start": 0.0, "video_end": 4.0, "narration": "ပထမစာကြောင်း"},
            {"video_start": 4.0, "video_end": 8.0, "narration": "ဆိုးသောစာကြောင်း"},
            {"video_start": 8.0, "video_end": 12.0, "narration": "တတိယစာကြောင်း"},
        ]}
        (job / "smart_sync_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return src, job

    def _run(self, tmp, src, job, provider, mms_fail=("ဆိုး",), mms_ok=True):
        made = {"mms": [], "edge": []}
        real_edge, real_mms_mod = core.EdgeTTSEngine, sys.modules.get("mms_tts")

        class FakeEdge(_FakeEngine):
            def __init__(s, **kw): super().__init__("edge", tmp / "edge_out"); made["edge"].append(s)
        class FakeMms(_FakeEngine):
            def __init__(s, **kw):
                if not mms_ok:
                    raise RuntimeError("torch missing")
                super().__init__("mms", tmp / "mms_out", fail_on=mms_fail); made["mms"].append(s)
        (tmp / "edge_out").mkdir(exist_ok=True); (tmp / "mms_out").mkdir(exist_ok=True)
        core.EdgeTTSEngine = FakeEdge
        fake_mod = types.ModuleType("mms_tts"); fake_mod.MMSTTSEngine = FakeMms
        sys.modules["mms_tts"] = fake_mod
        logs: list[str] = []
        try:
            runner = core.EdgeSmartSync(job_dir=str(job), source_path=str(src), plan_path=str(job / "smart_sync_plan.json"),
                                        voice="my-MM-ThihaNeural", ffmpeg_path=FFMPEG, ffprobe_path=FFPROBE,
                                        tts_provider=provider, render_final_video=False, log=logs.append)
            result = runner.run()
        finally:
            core.EdgeTTSEngine = real_edge
            sys.modules["mms_tts"] = real_mms_mod
            if real_mms_mod is None:
                sys.modules.pop("mms_tts", None)
        ck = json.loads((job / "edge_tts_smart_sync" / "checkpoint.json").read_text(encoding="utf-8"))
        return result, ck, made, "\n".join(logs)

    def test_edge_is_the_default_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); src, job = self._job(tmp)
            result, ck, made, _ = self._run(tmp, src, job, "edge")
            self.assertEqual(ck["tts_provider"], "edge_tts")
            self.assertEqual((len(made["edge"]), len(made["mms"])), (1, 0))
            self.assertEqual({r["provider"] for r in ck["audio"].values()}, {"edge"})
            plan = json.loads(Path(result["plan"]).read_text(encoding="utf-8"))
            self.assertEqual((plan["tts_provider"], plan["tts_voice"]), ("edge_tts", "my-MM-ThihaNeural"))

    def test_mms_with_edge_fallback_for_the_failed_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); src, job = self._job(tmp)
            result, ck, made, text = self._run(tmp, src, job, "mms")
            self.assertEqual(ck["tts_provider"], "mms_tts")
            self.assertEqual(sorted(r["provider"] for r in ck["audio"].values()), ["edge_fallback", "mms", "mms"])
            self.assertEqual(len(made["edge"][0].calls), 1)             # Edge spoke only the line MMS could not
            self.assertEqual(made["edge"][0].calls[0][1], "my-MM-ThihaNeural")
            self.assertIn("1 line(s) were spoken by Edge TTS", text)
            plan = json.loads(Path(result["plan"]).read_text(encoding="utf-8"))
            self.assertEqual(plan["tts_provider"], "mms_tts")
            self.assertGreater(plan["actual_audio_duration"], 2.5)

    def test_rerun_asks_mms_again_for_the_fallback_line_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); src, job = self._job(tmp)
            self._run(tmp, src, job, "mms")
            _r, ck, made, text = self._run(tmp, src, job, "mms", mms_fail=())      # MMS works now
            self.assertEqual(sorted(r["provider"] for r in ck["audio"].values()), ["mms", "mms", "mms"])
            self.assertEqual(len(made["mms"][0].calls), 1)               # only the earlier fallback line was redone
            self.assertEqual(len(made["edge"]), 0)

    def test_mms_not_installed_runs_everything_on_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp); src, job = self._job(tmp)
            _r, ck, made, text = self._run(tmp, src, job, "mms", mms_ok=False)
            self.assertEqual({r["provider"] for r in ck["audio"].values()}, {"edge_fallback"})
            self.assertEqual(len(made["edge"][0].calls), 3)
            self.assertIn("Meta MMS ကို မသုံးနိုင်ပါ", text)
            # installing MMS later: the next run (MMS fine) redoes all three lines
            _r, ck, made, _t = self._run(tmp, src, job, "mms", mms_fail=())
            self.assertEqual({r["provider"] for r in ck["audio"].values()}, {"mms"})


if __name__ == "__main__":
    unittest.main()
