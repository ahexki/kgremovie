"""Freeze rhythm: play N s, hold M s (zooming in), repeat. The planning is pure Python; the render test uses ffmpeg."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import core  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


class PlanTests(unittest.TestCase):
    def test_parts_always_add_up_to_the_video(self):
        for total in (1, 29, 30, 31, 299, 900, 1800, 2701, 9999):
            for play in (5, 8, 10):
                for hold in (2, 4):
                    parts = core.plan_freeze_rhythm(total, play_seconds=play, hold_seconds=hold, seed=3)
                    self.assertEqual(sum(p["frames"] for p in parts), total, (total, play, hold))
                    pos = 0
                    for p in parts:                       # contiguous, play first, never two holds in a row
                        if p["kind"] == "play":
                            self.assertEqual(p["start"], pos)
                        pos += p["frames"]
                    kinds = [p["kind"] for p in parts]
                    self.assertEqual(kinds[0], "play")
                    self.assertNotIn(("hold", "hold"), list(zip(kinds, kinds[1:])))

    def test_the_rhythm_is_play_then_hold(self):
        parts = core.plan_freeze_rhythm(30 * 40, play_seconds=8, hold_seconds=2, seed=1)
        self.assertEqual([(p["kind"], p["frames"]) for p in parts[:4]],
                         [("play", 240), ("hold", 60), ("play", 240), ("hold", 60)])
        self.assertEqual(parts[1]["at"], 239)             # the last frame that played is the one held

    def test_a_short_tail_is_not_a_flicker(self):
        parts = core.plan_freeze_rhythm(30 * 8 + 10, play_seconds=8, hold_seconds=2, seed=1)
        self.assertEqual([p["kind"] for p in parts], ["play"])           # 10 frames left: joined to the play
        self.assertEqual(parts[0]["frames"], 250)

    def test_zoom_is_random_but_repeatable_and_inside_the_range(self):
        a = core.plan_freeze_rhythm(30 * 200, play_seconds=5, hold_seconds=2, zoom_range=(1.10, 1.20), seed=42)
        b = core.plan_freeze_rhythm(30 * 200, play_seconds=5, hold_seconds=2, zoom_range=(1.10, 1.20), seed=42)
        c = core.plan_freeze_rhythm(30 * 200, play_seconds=5, hold_seconds=2, zoom_range=(1.10, 1.20), seed=43)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        zooms = [p["zoom"] for p in a if p["kind"] == "hold"]
        self.assertTrue(len(set(zooms)) > 5)
        self.assertTrue(all(1.10 <= z <= 1.20 for z in zooms))
        self.assertTrue(all(0.30 <= p["fx"] <= 0.70 and 0.30 <= p["fy"] <= 0.70 for p in a if p["kind"] == "hold"))
        off = core.plan_freeze_rhythm(30 * 60, play_seconds=5, hold_seconds=2, zoom_range=(1.0, 1.0), seed=1)
        self.assertTrue(all(p["zoom"] == 1.0 for p in off if p["kind"] == "hold"))

    def test_settings_are_cleaned(self):
        cfg = core.normalize_freeze_rhythm({"enabled": 1, "play_seconds": "9", "hold_seconds": 3, "zoom_level": "large"})
        self.assertEqual((cfg["enabled"], cfg["play_seconds"], cfg["hold_seconds"], cfg["zoom_level"]),
                         (True, 8, 2, "Large"))
        bad = core.normalize_freeze_rhythm({"play_seconds": "x", "zoom_level": "huge", "seed": "q"})
        self.assertEqual((bad["enabled"], bad["play_seconds"], bad["hold_seconds"], bad["zoom_level"], bad["seed"]),
                         (False, 8, 2, "Medium", None))


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg is not installed")
class RenderTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path, seconds: int = 20) -> None:
        # a moving picture with a running frame counter: every frame is different
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        f"testsrc2=size=320x180:rate=30:duration={seconds}", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                        "-g", "30", str(path)], check=True)

    @staticmethod
    def _diff(a: bytes, b: bytes) -> float:
        return sum(abs(x - y) for x, y in zip(a, b)) / len(a)

    @staticmethod
    def _frames(path: Path) -> list[bytes]:
        out = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True, check=True).stdout
        size = 320 * 180
        return [out[i:i + size] for i in range(0, len(out), size)]

    def _run(self, tmp: Path, **settings):
        src, dst = tmp / "in.mp4", tmp / "out.mp4"
        self._source(src)
        cfg = {"enabled": True, "play_seconds": 5, "hold_seconds": 2, "zoom_level": "Medium", "seed": 7, **settings}
        logs: list[str] = []
        core.apply_freeze_rhythm(FFMPEG, FFPROBE, src, dst, cfg, "libx264", tmp / "work", log=logs.append)
        return src, dst, logs

    def test_length_is_kept_and_holds_are_still_without_zoom(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src, dst, _logs = self._run(tmp, zoom_level="Off")
            before, after = self._frames(src), self._frames(dst)
            self.assertEqual(len(before), 600)
            self.assertEqual(len(after), 600)                       # same length: the narration stays in step
            # 20 s = play 5 | hold 2 | play 5 | hold 2 | play 5 | tail (1 s joins the last play)
            self.assertLess(max(self._diff(after[150], f) for f in after[150:210]), 0.05)   # one still picture
            self.assertLess(max(self._diff(after[360], f) for f in after[360:420]), 0.05)
            self.assertGreater(self._diff(after[50], after[80]), 3.0)                       # the play parts keep moving
            self.assertGreater(self._diff(after[250], after[280]), 3.0)
            self.assertGreater(self._diff(after[210], after[209]), 3.0)                     # after a hold the picture has moved on

    def test_the_held_frame_zooms_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _src, dst, logs = self._run(tmp, zoom_level="Large")
            frames = self._frames(dst)
            self.assertEqual(len(frames), 600)
            hold = frames[150:210]
            self.assertGreater(self._diff(hold[0], hold[-1]), 3.0)  # it changes: the push-in is moving
            self.assertTrue(any("Freeze rhythm: play 5s → hold 2s" in line for line in logs))
            # first held frame is the frame that played last (no zoom yet): nearly identical to frame 149
            diff = sum(abs(a - b) for a, b in zip(hold[0], frames[149])) / len(hold[0])
            self.assertLess(diff, 6.0)
            # the end of the hold is clearly a zoomed version of it
            end = sum(abs(a - b) for a, b in zip(hold[-1], frames[149])) / len(hold[-1])
            self.assertGreater(end, diff * 2)

    def test_order_in_the_pipeline_rhythm_then_overlays_then_audio(self):
        """The same order EdgeSmartSync.run() uses: the blur box stays still on top of the freeze, audio length rules."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "synced.mp4"
            self._source(src)
            rhythm = core.apply_freeze_rhythm(FFMPEG, FFPROBE, src, tmp / "rhythm.mp4",
                                              {"enabled": True, "play_seconds": 5, "hold_seconds": 2, "seed": 1},
                                              "libx264", tmp / "work")
            deco = core.apply_production_overlays(
                FFMPEG, rhythm, tmp / "deco.mp4", {"blur_boxes": [{"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}], "logo_enabled": False},
                "libx264", tmp / "work", frame_size=(320, 180))
            audio = tmp / "voice.wav"
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=20", str(audio)], check=True)
            final = tmp / "final.mp4"
            core.mux_audio(FFMPEG, deco, audio, final)
            self.assertAlmostEqual(core.probe_duration(FFPROBE, final), 20.0, delta=0.3)
            self.assertEqual(len(self._frames(final)), 600)

    def test_stopping_keeps_finished_parts_and_resume_reuses_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "in.mp4"
            self._source(src)
            calls = {"n": 0}

            def stop():
                calls["n"] += 1
                return calls["n"] > 3                      # stop before the 4th part
            cfg = {"enabled": True, "play_seconds": 5, "hold_seconds": 2, "seed": 1}
            with self.assertRaises(InterruptedError):
                core.apply_freeze_rhythm(FFMPEG, FFPROBE, src, tmp / "out.mp4", cfg, "libx264", tmp / "work", should_stop=stop)
            kept = list((tmp / "work").glob("freeze_rhythm_*/part_*.mp4"))
            self.assertEqual(len(kept), 3)
            stamps = {p.name: p.stat().st_mtime_ns for p in kept}
            core.apply_freeze_rhythm(FFMPEG, FFPROBE, src, tmp / "out.mp4", cfg, "libx264", tmp / "work")
            self.assertEqual(len(self._frames(tmp / "out.mp4")), 600)
            self.assertEqual(stamps and len(stamps), 3)

    def test_a_video_shorter_than_one_play_block_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src, dst = tmp / "in.mp4", tmp / "out.mp4"
            self._source(src, 4)
            result = core.apply_freeze_rhythm(FFMPEG, FFPROBE, src, dst, {"enabled": True, "play_seconds": 5},
                                              "libx264", tmp / "work")
            self.assertEqual(result, src)


if __name__ == "__main__":
    unittest.main()
