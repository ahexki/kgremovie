"""Version 2.0 effects inside the real Smart Sync render: look + slow motion / auto edit, then overlays, then the audio."""
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

import core  # noqa: E402

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


class _Edge:
    """Edge TTS stand-in: a 4 s tone per line (so the video keeps its length)."""
    def __init__(self, **kw):
        self.n = 0
        self.dir = Path(kw["work_dir"])
        self.dir.mkdir(parents=True, exist_ok=True)

    def generate_channel99_voice(self, text, voice=""):
        self.n += 1
        path = self.dir / f"t{self.n}.wav"
        t = np.arange(24000 * 4) / 24000
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes((np.sin(2 * np.pi * 300 * t) * 9000).astype("<i2").tobytes())
        return str(path)


def _frames(path: Path, w: int, h: int) -> list[np.ndarray]:
    # the final video is a full-size canvas (e.g. 1920x1080): look at it at w x h
    out = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(path), "-vf", f"scale={w}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    n = w * h
    return [np.frombuffer(out[i:i + n], dtype=np.uint8).astype(float).reshape(h, w) for i in range(0, len(out), n)]


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg is not installed")
class PipelineTests(unittest.TestCase):
    def _run(self, tmp: Path, name: str, **fx_settings):
        src = tmp / "clip.mp4"
        if not src.exists():
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=0x909090:s=320x180:r=30:d=12", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-g", "30", str(src)],
                           check=True)
        job = tmp / name
        job.mkdir()
        plan = {"segments": [{"video_start": i * 4.0, "video_end": i * 4.0 + 4.0, "narration": f"စာကြောင်း {i}"} for i in range(3)]}
        (job / "smart_sync_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        logs: list[str] = []
        real = core.EdgeTTSEngine
        core.EdgeTTSEngine = _Edge
        try:
            runner = core.EdgeSmartSync(job_dir=str(job), source_path=str(src), plan_path=str(job / "smart_sync_plan.json"),
                                        voice="my-MM-ThihaNeural", ffmpeg_path=FFMPEG, ffprobe_path=FFPROBE,
                                        output_ratio="16:9", log=logs.append, **fx_settings)
            result = runner.run()
        finally:
            core.EdgeTTSEngine = real
        return result, "\n".join(logs)

    def test_vignette_and_slow_motion_in_the_final_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plain, _ = self._run(tmp, "plain")
            fx_result, text = self._run(tmp, "fx", video_look={"preset": "Off", "vignette": 100},
                                        slow_motion={"enabled": True, "gap_seconds": 10, "slow_seconds": 5, "speed": 0.5})
            a, b = Path(plain["final"]), Path(fx_result["final"])
            self.assertAlmostEqual(plain["duration"], fx_result["duration"], delta=0.2)      # the length never changes
            self.assertIn("Slow motion: play 10s → slow 5s", text)
            self.assertIn("Video look: filter Off 60% | vignette 100%", text)
            self.assertLess(text.index("Slow motion pass"), text.index("Video look:"))        # slow motion first, the look on top
            pa, pb = _frames(a, 320, 180), _frames(b, 320, 180)
            self.assertEqual(len(pa), len(pb))
            mid = len(pb) // 2
            corner = lambda f: f[:8, :8].mean() / f[86:94, 156:164].mean()
            self.assertGreater(corner(pa[mid]), 0.9)
            self.assertLess(corner(pb[mid]), 0.4)

    def test_auto_edit_replaces_freeze_and_slow(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            result, text = self._run(tmp, "auto", auto_edit={"enabled": True, "effects": ["flip", "vignette"], "intensity": "High", "seed": 5},
                                     freeze_rhythm={"enabled": True}, slow_motion={"enabled": True})
            self.assertIn("Freeze rhythm and Slow motion are skipped", text)
            self.assertIn("Auto edit (High, seed 5)", text)
            self.assertNotIn("Freeze rhythm pass", text)
            self.assertNotIn("Slow motion pass", text)
            self.assertTrue(Path(result["final"]).is_file())

    def test_everything_off_is_the_old_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, text = self._run(Path(tmp), "off")
            for word in ("Auto edit", "Slow motion", "Video look", "Freeze rhythm"):
                self.assertNotIn(word, text)
            self.assertTrue(Path(result["final"]).is_file())


if __name__ == "__main__":
    unittest.main()
