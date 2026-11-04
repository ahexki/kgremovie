"""Version 3.0: male / female dub voices chosen from the original speakers, and the original sound mixed under the dub."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import audio_mix as am  # noqa: E402
import voice_gender as vg  # noqa: E402

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
SR = vg.SR


def voice_signal(f0: float, seconds: float, sr: int = SR, seed: int = 0, vib: float = 0.02) -> np.ndarray:
    """A speech-like buzz: a harmonic series on f0 with a little vibrato and noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(sr * seconds)) / sr
    f = f0 * (1 + vib * np.sin(2 * np.pi * 5 * t))
    phase = 2 * np.pi * np.cumsum(f) / sr
    sig = sum((1.0 / k) * np.sin(k * phase) for k in range(1, 12) if f0 * k < sr / 2 - 200)
    return (sig * 0.3 + rng.normal(0, 0.01, t.size)).astype(np.float32)


class PitchTests(unittest.TestCase):
    def test_f0_is_found_within_a_few_hertz(self):
        for hz in (90, 110, 130, 150, 170, 200, 230, 260):
            f0, _t = vg.estimate_f0(voice_signal(hz, 2.0))
            voiced = f0[f0 > 0]
            self.assertGreater(voiced.size, f0.size * 0.9, hz)
            self.assertAlmostEqual(float(np.median(voiced)), hz, delta=hz * 0.03, msg=str(hz))

    def test_silence_and_noise_are_not_a_voice(self):
        rng = np.random.default_rng(1)
        for sig in (rng.normal(0, 0.002, SR * 2), rng.normal(0, 0.2, SR * 3)):
            f0, _t = vg.estimate_f0(sig.astype(np.float32))
            self.assertLess(float((f0 > 0).mean()), 0.05)
        self.assertEqual(vg.estimate_f0(np.zeros(10, dtype=np.float32))[0].size, 0)

    def test_window_pitch_uses_only_the_window(self):
        sig = np.concatenate([voice_signal(110, 2.0), voice_signal(220, 2.0)])
        f0, t = vg.estimate_f0(sig)
        self.assertAlmostEqual(vg.window_pitch(f0, t, 0.2, 1.8)[0], 110, delta=4)
        self.assertAlmostEqual(vg.window_pitch(f0, t, 2.2, 3.8)[0], 220, delta=7)
        self.assertIsNone(vg.window_pitch(f0, t, 0.0, 0.1)[0])                    # too short to judge
        self.assertIsNone(vg.window_pitch(np.zeros(0), np.zeros(0), 0, 1)[0])


class LabelTests(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(vg.label_windows([110, 140, 200, 240]), ["male", "male", "female", "female"])

    def test_in_between_goes_to_the_nearer_speaker_type(self):
        self.assertEqual(vg.label_windows([115, 230, 150, 175, 118]), ["male", "female", "male", "female", "male"])

    def test_unknown_windows_take_the_nearest_known_one(self):
        self.assertEqual(vg.label_windows([None, 120, None, None, 230, None]),
                         ["male", "male", "male", "female", "female", "female"])
        self.assertEqual(vg.label_windows([None, None], default="female"), ["female", "female"])
        self.assertEqual(vg.label_windows([]), [])

    def test_only_in_between_windows_use_the_middle(self):
        self.assertEqual(vg.label_windows([160, 175]), ["male", "female"])

    def test_modes_and_voice_names(self):
        self.assertEqual(vg.normalize_voice_mode("Auto — by speaker"), "auto")
        self.assertEqual(vg.normalize_voice_mode("FEMALE"), "female")
        self.assertEqual(vg.normalize_voice_mode("???"), "selected")
        sel = "my-MM-NilarNeural"
        self.assertEqual(vg.voice_for("selected", sel), sel)
        self.assertEqual(vg.voice_for("male", sel), vg.VOICE_MALE)
        self.assertEqual(vg.voice_for("female", "x"), vg.VOICE_FEMALE)
        self.assertEqual(vg.voice_for("auto", sel, "male"), vg.VOICE_MALE)
        self.assertEqual(vg.voice_for("auto", sel, "female"), vg.VOICE_FEMALE)
        self.assertEqual(vg.voice_for("auto", sel, None), sel)
        self.assertEqual(len(vg.VOICE_MODES), 4)


class MixHelpersTests(unittest.TestCase):
    def test_settings_and_tempo_chain(self):
        self.assertEqual(am.normalize_audio_mix({}), {"original_percent": 0, "duck": True})
        self.assertEqual(am.normalize_audio_mix({"original_percent": 250, "duck": 0}), {"original_percent": 100, "duck": False})
        self.assertEqual(am.normalize_audio_mix({"original_percent": "x"})["original_percent"], 0)
        self.assertEqual(am.atempo_chain(1.0), "atempo=1.00000")
        self.assertEqual(am.atempo_chain(3.0), "atempo=2.00000,atempo=1.50000")
        self.assertEqual(am.atempo_chain(0.3), "atempo=0.50000,atempo=0.60000")


def _write_wav(path: Path, x: np.ndarray, sr: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def _band(path: Path, a: float, b: float, hz: float) -> float:
    out = subprocess.run([FFMPEG, "-loglevel", "error", "-ss", str(a), "-t", str(b - a), "-i", str(path), "-vn", "-f", "s16le",
                          "-ac", "1", "-ar", "48000", "-"], capture_output=True).stdout
    x = np.frombuffer(out, dtype="<i2").astype(float) / 32768
    sp = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    f = np.fft.rfftfreq(x.size, 1 / 48000)
    return float(sp[(f > hz - 40) & (f < hz + 40)].sum() / x.size)


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg is not installed")
class MixRenderTests(unittest.TestCase):
    def test_ducking_lowers_the_original_only_while_the_dub_speaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sr = 48000
            t = np.arange(sr * 6) / sr
            dub = np.sin(2 * np.pi * 300 * t) * 0.5
            dub[:2 * sr] = 0
            dub[4 * sr:] = 0
            orig = np.sin(2 * np.pi * 1000 * t) * 0.4
            _write_wav(tmp / "dub.wav", dub, sr)                      # the dub is mono, like Edge TTS / MMS
            with wave.open(str(tmp / "orig.wav"), "wb") as w:         # the original track is stereo (what build_original_track makes)
                w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
                w.writeframes((np.repeat(orig[:, None], 2, axis=1) * 32767).astype("<i2").tobytes())
            levels = {}
            for label, kw in (("steady", dict(original_percent=100, duck=False)), ("ducked", dict(original_percent=100, duck=True)),
                              ("half", dict(original_percent=50, duck=True)), ("off", dict(original_percent=0, duck=True))):
                out = am.mix_tracks(FFMPEG, tmp / "dub.wav", tmp / "orig.wav", tmp / f"{label}.wav", dub_percent=100, **kw)
                levels[label] = (_band(out, 0.2, 1.8, 1000), _band(out, 2.4, 3.8, 1000), _band(out, 4.2, 5.8, 1000), _band(out, 2.4, 3.8, 300))
            before, during, after, dubtone = levels["steady"]
            self.assertAlmostEqual(before, during, delta=before * 0.1)                       # no ducking: constant
            self.assertLess(levels["ducked"][1], levels["ducked"][0] * 0.15)                 # lowered under the dub ...
            self.assertGreater(levels["ducked"][2], levels["ducked"][0] * 0.9)               # ... and back afterwards
            self.assertAlmostEqual(levels["half"][0], levels["ducked"][0] / 2, delta=levels["ducked"][0] * 0.1)
            self.assertLess(levels["off"][0], 0.001)                                         # 0 % = dub only
            self.assertAlmostEqual(dubtone, 0.25, delta=0.02)                                # the dub keeps its level (no -3 dB)
            self.assertAlmostEqual(levels["ducked"][3], dubtone, delta=dubtone * 0.1)
            loud = am.mix_tracks(FFMPEG, tmp / "dub.wav", tmp / "orig.wav", tmp / "loud.wav", original_percent=0, dub_percent=150, duck=True)
            self.assertAlmostEqual(_band(loud, 2.4, 3.8, 300), dubtone * 1.5, delta=dubtone * 0.2)


class _Edge:
    """Edge TTS stand-in that records the voice of every line."""
    calls: list[tuple[str, str]] = []

    def __init__(self, **kw):
        self.n = 0
        self.dir = Path(kw["work_dir"])
        self.dir.mkdir(parents=True, exist_ok=True)

    def generate_channel99_voice(self, text, voice=""):
        _Edge.calls.append((text, voice))
        self.n += 1
        sr = 24000
        t = np.arange(sr * 4) / sr
        x = np.sin(2 * np.pi * 300 * t) * 0.3
        path = self.dir / f"t{self.n}.wav"
        _write_wav(path, x, sr)
        return str(path)


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg is not installed")
class PipelineTests(unittest.TestCase):
    def _source(self, tmp: Path, parts: list[np.ndarray], name="clip.mp4") -> Path:
        audio = np.concatenate(parts)
        wav = tmp / "src.wav"
        _write_wav(wav, audio, SR)
        out = tmp / name
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=0x303030:s=320x180:r=30:d={audio.size / SR:.2f}",
                        "-i", str(wav), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out)], check=True)
        return out

    def _rerun(self, tmp: Path, src: Path, name: str, **kw):
        return self._run(tmp, src, name, reuse_job=True, **kw)

    def _run(self, tmp: Path, src: Path, name: str, reuse_job: bool = False, **kw):
        import core
        job = tmp / name
        job.mkdir(exist_ok=reuse_job)
        narration = ["စာကြောင်း တစ်", "စာကြောင်း နှစ်", "စာကြောင်း သုံး"]
        plan = {"segments": [{"video_start": i * 4.0, "video_end": i * 4.0 + 4.0, "narration": narration[i]} for i in range(3)]}
        (job / "smart_sync_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        logs: list[str] = []
        _Edge.calls = []
        real = core.EdgeTTSEngine
        core.EdgeTTSEngine = _Edge
        try:
            runner = core.EdgeSmartSync(job_dir=str(job), source_path=str(src), plan_path=str(job / "smart_sync_plan.json"),
                                        voice=kw.pop("voice", "my-MM-ThihaNeural"), ffmpeg_path=FFMPEG, ffprobe_path=FFPROBE,
                                        output_ratio="16:9", log=logs.append, **kw)
            result = runner.run()
        finally:
            core.EdgeTTSEngine = real
        return result, "\n".join(logs), list(_Edge.calls)

    def test_voice_follows_the_original_speaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._source(tmp, [voice_signal(110, 4.0), voice_signal(225, 4.0, seed=1), voice_signal(120, 4.0, seed=2)])
            result, text, calls = self._run(tmp, src, "auto", voice_mode="auto", render_final_video=False)
            self.assertEqual([v for _t, v in calls], [vg.VOICE_MALE, vg.VOICE_FEMALE, vg.VOICE_MALE])
            self.assertIn("Auto — 2 line(s) male (Thiha), 1 line(s) female (Nilar)", text)
            plan = json.loads(Path(result["plan"]).read_text(encoding="utf-8"))
            self.assertEqual([x["voice"] for x in plan["tts_timing_segments"]], [vg.VOICE_MALE, vg.VOICE_FEMALE, vg.VOICE_MALE])
            self.assertEqual(plan["voice_mode"], "auto")
            # the same job again: the pitch detection and every line's audio are reused, nothing is spoken again
            result2, text2, calls2 = self._rerun(tmp, src, "auto", voice_mode="auto", render_final_video=False)
            self.assertIn("Voice gender detection reuse", text2)
            self.assertEqual(calls2, [])

    def test_the_other_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = self._source(tmp, [voice_signal(110, 4.0), voice_signal(225, 4.0, seed=1), voice_signal(120, 4.0, seed=2)])
            for mode, expect in (("male", vg.VOICE_MALE), ("female", vg.VOICE_FEMALE)):
                _r, _t, calls = self._run(tmp, src, mode, voice_mode=mode, voice="my-MM-ThihaNeural", render_final_video=False)
                self.assertEqual({v for _x, v in calls}, {expect}, mode)
            _r, _t, calls = self._run(tmp, src, "sel", voice_mode="selected", voice="my-MM-NilarNeural", render_final_video=False)
            self.assertEqual({v for _x, v in calls}, {"my-MM-NilarNeural"})
            _r, _t, calls = self._run(tmp, src, "def", render_final_video=False)                 # nothing chosen = the old behaviour
            self.assertEqual({v for _x, v in calls}, {"my-MM-ThihaNeural"})

    def test_a_video_without_sound_falls_back_to_the_selected_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "mute.mp4"
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x303030:s=320x180:r=30:d=12",
                            "-pix_fmt", "yuv420p", "-c:v", "libx264", str(src)], check=True)
            _r, text, calls = self._run(tmp, src, "mute", voice_mode="auto", voice="my-MM-NilarNeural", render_final_video=False)
            self.assertEqual({v for _x, v in calls}, {vg.VOICE_FEMALE})
            self.assertIn("no audio to listen to", text)

    def test_original_sound_mixed_under_the_dub_in_the_final_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sr = SR
            tone = (np.sin(2 * np.pi * 1000 * np.arange(sr * 12) / sr) * 0.4).astype(np.float32)
            src = self._source(tmp, [tone])
            plain, _t, _c = self._run(tmp, src, "plain")
            mixed, text, _c = self._run(tmp, src, "mixed", audio_mix={"original_percent": 80, "duck": False})
            self.assertIn("Audio mix: original 80% (steady) + dub 100%", text)
            self.assertAlmostEqual(plain["duration"], mixed["duration"], delta=0.1)
            self.assertLess(_band(Path(plain["final"]), 2, 8, 1000), 0.001)                  # the old output: dub only
            self.assertGreater(_band(Path(mixed["final"]), 2, 8, 1000), 0.05)                # the original is there now
            self.assertGreater(_band(Path(mixed["final"]), 2, 8, 300), 0.1)                  # and so is the dub
            ducked, text, _c = self._run(tmp, src, "ducked", audio_mix={"original_percent": 80, "duck": True})
            self.assertIn("ducked under the dub", text)
            self.assertLess(_band(Path(ducked["final"]), 2, 8, 1000), _band(Path(mixed["final"]), 2, 8, 1000) * 0.5)

    def test_dub_volume_is_applied_inside_the_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tone = (np.sin(2 * np.pi * 1000 * np.arange(SR * 12) / SR) * 0.4).astype(np.float32)
            src = self._source(tmp, [tone])
            import core
            job = tmp / "vol"
            job.mkdir()
            plan = {"segments": [{"video_start": i * 4.0, "video_end": i * 4.0 + 4.0, "narration": f"စာ {i}"} for i in range(3)]}
            (job / "smart_sync_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            real = core.EdgeTTSEngine
            core.EdgeTTSEngine = _Edge
            try:
                runner = core.EdgeSmartSync(job_dir=str(job), source_path=str(src), plan_path=str(job / "smart_sync_plan.json"),
                                            voice="my-MM-ThihaNeural", ffmpeg_path=FFMPEG, ffprobe_path=FFPROBE, output_ratio="16:9",
                                            log=lambda _m: None, audio_mix={"original_percent": 50, "duck": False})
                runner.voice_volume_percent = 200
                result = runner.run()
            finally:
                core.EdgeTTSEngine = real
            base_job = tmp / "vol100"
            base_job.mkdir()
            (base_job / "smart_sync_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            core.EdgeTTSEngine = _Edge
            try:
                runner = core.EdgeSmartSync(job_dir=str(base_job), source_path=str(src), plan_path=str(base_job / "smart_sync_plan.json"),
                                            voice="my-MM-ThihaNeural", ffmpeg_path=FFMPEG, ffprobe_path=FFPROBE, output_ratio="16:9",
                                            log=lambda _m: None, audio_mix={"original_percent": 50, "duck": False})
                result100 = runner.run()
            finally:
                core.EdgeTTSEngine = real
            loud, normal = _band(Path(result["final"]), 2, 8, 300), _band(Path(result100["final"]), 2, 8, 300)
            self.assertAlmostEqual(loud / normal, 2.0, delta=0.4)


if __name__ == "__main__":
    unittest.main()
