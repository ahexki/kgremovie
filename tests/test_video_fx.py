"""Version 2.0 picture effects: video look, vignette, slow motion and the random auto edit."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import video_fx as fx  # noqa: E402

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
W, H = 320, 180


class PlanTests(unittest.TestCase):
    def test_slow_motion_parts_add_up_and_alternate(self):
        for total in (1, 59, 600, 1799, 5000):
            for gap in fx.SLOW_GAPS:
                for slow in (5, 10):
                    parts = fx.plan_slow_motion(total, gap_seconds=gap, slow_seconds=slow, speed=0.5)
                    self.assertEqual(sum(p["frames"] for p in parts), total)
                    kinds = [p["kind"] for p in parts]
                    self.assertEqual(kinds[0], "play")
                    self.assertNotIn(("slow", "slow"), list(zip(kinds, kinds[1:])))
        parts = fx.plan_slow_motion(30 * 100, gap_seconds=20, slow_seconds=5, speed=0.5)
        self.assertEqual([(p["kind"], p["frames"]) for p in parts[:3]], [("play", 600), ("slow", 150), ("play", 600)])

    def test_auto_edit_parts_add_up_and_are_repeatable(self):
        kw = dict(effects=list(fx.AUTO_EFFECTS), intensity="High", slow_seconds=5, hold_seconds=2)
        for total in (1, 100, 899, 3000, 20000):
            parts = fx.plan_auto_edit(total, seed=4, **kw)
            self.assertEqual(sum(p["frames"] for p in parts), total, total)
            pos = 0
            for p in parts:
                self.assertEqual(p["start"], pos)
                pos += p["frames"]
        a = fx.plan_auto_edit(9000, seed=4, **kw)
        self.assertEqual(a, fx.plan_auto_edit(9000, seed=4, **kw))
        self.assertNotEqual(a, fx.plan_auto_edit(9000, seed=5, **kw))

    def test_only_the_allowed_effects_are_used(self):
        parts = fx.plan_auto_edit(30 * 600, effects=["flip"], intensity="High", seed=1)
        self.assertTrue(any(p["flip"] for p in parts))
        self.assertTrue(all(p["kind"] == "play" and not p["zoom"] and not p["vignette"] for p in parts))
        parts = fx.plan_auto_edit(30 * 600, effects=["slow"], intensity="High", slow_seconds=10, seed=1)
        slows = [p for p in parts if p["kind"] == "slow"]
        self.assertTrue(slows)
        self.assertTrue(all(p["frames"] == 300 for p in slows[:-1]))
        self.assertTrue(all(p["speed"] in (0.35, 0.5, 0.6, 0.7) and not p["flip"] for p in slows))
        self.assertIn(0.35, {p["speed"] for p in slows}, "the slower speed is really chosen sometimes")
        parts = fx.plan_auto_edit(30 * 600, effects=["freeze"], intensity="High", hold_seconds=4, seed=1)
        holds = [p for p in parts if p["kind"] == "hold"]
        self.assertTrue(holds)
        index = {id(p): i for i, p in enumerate(parts)}
        for h in holds:
            before = parts[index[id(h)] - 1]
            self.assertEqual(h["at"], before["start"] + before["frames"] - 1)     # freezes the last frame that played
            self.assertTrue(h["zoom"])                                           # a freeze always breathes a little
        self.assertEqual(fx.plan_auto_edit(900, effects=[], intensity="High", seed=1)[0]["kind"], "play")

    def test_intensity_changes_how_much_is_edited(self):
        def edited(intensity):
            parts = fx.plan_auto_edit(30 * 3000, effects=list(fx.AUTO_EFFECTS), intensity=intensity, seed=9)
            return sum(1 for p in parts if p["kind"] != "play" or p["flip"] or p["zoom"] or p["vignette"]) / len(parts)
        low, med, high = edited("Low"), edited("Medium"), edited("High")
        self.assertLess(low, med)
        self.assertLess(med, high)

    def test_settings_are_cleaned(self):
        self.assertEqual(fx.normalize_look({"preset": "warm", "strength": 250, "vignette": "x"}),
                         {"preset": "Warm", "strength": 100, "vignette": 0})
        self.assertEqual(fx.normalize_look({"preset": "nonsense"})["preset"], "Off")
        self.assertFalse(fx.look_enabled({"preset": "Off", "vignette": 0}))
        self.assertTrue(fx.look_enabled({"preset": "Off", "vignette": 5}))
        self.assertFalse(fx.look_enabled({"preset": "Warm", "strength": 0}))
        slow = fx.normalize_slow_motion({"enabled": 1, "slow_seconds": 9, "gap_seconds": 28, "speed": 0.55})
        self.assertEqual((slow["slow_seconds"], slow["gap_seconds"], slow["speed"]), (10, 30, 0.5))
        self.assertEqual(fx.normalize_slow_motion({"gap_seconds": 6})["gap_seconds"], 10)
        auto = fx.normalize_auto_edit({"enabled": True, "effects": ["flip", "bogus", "slow"], "intensity": "high", "seed": "7"})
        self.assertEqual((auto["effects"], auto["intensity"], auto["seed"]), (["flip", "slow"], "High", 7))
        self.assertEqual(fx.normalize_auto_edit({})["effects"], list(fx.AUTO_EFFECTS))

    def test_vignette_gets_stronger_with_the_percentage(self):
        angles = [fx.vignette_angle(p) for p in (0, 10, 25, 50, 75, 100)]
        self.assertEqual(angles, sorted(angles))
        self.assertAlmostEqual(angles[0], 0.18, places=2)
        self.assertAlmostEqual(angles[-1], 0.80, places=2)
        self.assertEqual(fx.vignette_angle(-5), fx.vignette_angle(0))
        self.assertEqual(fx.vignette_angle(500), fx.vignette_angle(100))

    def test_look_filter_text(self):
        self.assertEqual(fx.look_filter("Off", 80), "")
        self.assertEqual(fx.look_filter("Warm", 0), "")
        for preset in fx.LOOK_PRESETS[1:]:
            self.assertTrue(fx.look_filter(preset, 60), preset)
        self.assertEqual(fx.look_vf({"preset": "Off", "vignette": 0}), "")
        self.assertIn("vignette=angle=", fx.look_vf({"preset": "Warm", "strength": 50, "vignette": 40}))
        self.assertNotEqual(fx.look_filter("Vivid", 30), fx.look_filter("Vivid", 90))


def _source(path: Path, seconds: int = 20, flat: bool = False) -> None:
    src = (f"color=c=0x909090:s={W}x{H}:r=30:d={seconds}" if flat else f"testsrc2=size={W}x{H}:rate=30:duration={seconds}")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", src, "-pix_fmt", "yuv420p", "-c:v", "libx264",
                    "-g", "30", str(path)], check=True)


def _frames(path: Path, pix: str = "gray") -> list[np.ndarray]:
    out = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", pix, "-"],
                         capture_output=True, check=True).stdout
    c = 1 if pix == "gray" else 3
    size = W * H * c
    return [np.frombuffer(out[i:i + size], dtype=np.uint8).astype(float) for i in range(0, len(out), size)]


def _d(a, b) -> float:
    return float(np.abs(a - b).mean())


@unittest.skipUnless(FFMPEG and FFPROBE, "ffmpeg is not installed")
class RenderTests(unittest.TestCase):
    def test_every_preset_renders_and_changes_the_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "in.mp4"
            _source(src, 2)
            base = _frames(src, "rgb24")
            for preset in fx.LOOK_PRESETS[1:]:
                out = fx.apply_video_look(FFMPEG, FFPROBE, src, tmp / f"{preset[:3]}.mp4",
                                          {"preset": preset, "strength": 80, "vignette": 0}, "libx264")
                got = _frames(out, "rgb24")
                self.assertEqual(len(got), len(base), preset)
                self.assertGreater(_d(got[10], base[10]), 2.0, preset)
            weak = fx.apply_video_look(FFMPEG, FFPROBE, src, tmp / "weak.mp4", {"preset": "Vivid", "strength": 10}, "libx264")
            strong = fx.apply_video_look(FFMPEG, FFPROBE, src, tmp / "strong.mp4", {"preset": "Vivid", "strength": 100}, "libx264")
            self.assertLess(_d(_frames(weak, "rgb24")[10], base[10]), _d(_frames(strong, "rgb24")[10], base[10]))
            self.assertEqual(fx.apply_video_look(FFMPEG, FFPROBE, src, tmp / "x.mp4", {"preset": "Off", "vignette": 0}, "libx264"), src)

    def test_black_and_white_removes_the_colour(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "in.mp4"
            _source(src, 2)
            out = fx.apply_video_look(FFMPEG, FFPROBE, src, tmp / "bw.mp4", {"preset": "Black & White", "strength": 100}, "libx264")
            f = _frames(out, "rgb24")[5].reshape(H, W, 3)
            self.assertLess(float(np.abs(f[..., 0] - f[..., 1]).mean()), 3.0)
            self.assertLess(float(np.abs(f[..., 1] - f[..., 2]).mean()), 3.0)

    def test_vignette_darkens_the_corners_by_the_percentage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "flat.mp4"
            _source(src, 2, flat=True)
            ratios = {}
            for pct in (25, 50, 100):
                out = fx.apply_video_look(FFMPEG, FFPROBE, src, tmp / f"v{pct}.mp4", {"preset": "Off", "vignette": pct}, "libx264")
                f = _frames(out)[5].reshape(H, W)
                ratios[pct] = f[:10, :10].mean() / f[H // 2 - 5:H // 2 + 5, W // 2 - 5:W // 2 + 5].mean()
            self.assertGreater(ratios[25], ratios[50])
            self.assertGreater(ratios[50], ratios[100])
            self.assertLess(ratios[100], 0.30)
            self.assertGreater(ratios[25], 0.65)

    def test_slow_motion_keeps_the_length_and_is_smooth_and_slower(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src, dst = tmp / "in.mp4", tmp / "slow.mp4"
            _source(src, 20)
            out = fx.apply_slow_motion(FFMPEG, FFPROBE, src, dst, {"enabled": True, "gap_seconds": 20, "slow_seconds": 5}, "libx264",
                                       tmp / "work")
            self.assertEqual(out, src)                                        # 20 s is one play block: nothing to slow
            _source(src, 30)
            out = fx.apply_slow_motion(FFMPEG, FFPROBE, src, dst, {"enabled": True, "gap_seconds": 10, "slow_seconds": 5, "speed": 0.5},
                                       "libx264", tmp / "work")
            f, ref = _frames(out), _frames(src)
            self.assertEqual(len(f), 900)
            # 10 s play | 5 s slow | 10 s play | 5 s slow
            best = lambda k, lo, hi: int(np.argmin([_d(f[k], ref[j]) for j in range(lo, hi)])) + lo
            self.assertEqual(best(100, 90, 110), 100)                        # the play part is the source, frame for frame
            self.assertEqual(best(300, 295, 305), 300)                       # the slow part starts where the play part ended
            self.assertAlmostEqual(best(380, 330, 400), 340, delta=2)        # 80 slow frames in = 40 source frames in
            self.assertAlmostEqual(best(440, 350, 400), 370, delta=2)
            step = lambda a, b: float(np.mean([_d(f[i], f[i + 1]) for i in range(a, b)]))
            normal, slow = step(10, 140), step(320, 440)
            self.assertLess(slow, normal * 0.7)                              # about half the motion per frame
            self.assertGreater(slow, normal * 0.3)
            self.assertEqual(sum(1 for i in range(320, 440) if _d(f[i], f[i + 1]) < 0.05), 0)   # no stuttering duplicate frames

    def test_auto_edit_flip_is_a_real_mirror_and_the_length_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "in.mp4"
            _source(src, 40)
            cfg = {"enabled": True, "effects": ["flip"], "intensity": "High", "seed": 3}
            parts = fx.plan_auto_edit(1200, effects=["flip"], intensity="High", seed=3)
            flipped = [p for p in parts if p["flip"]]
            plain = [p for p in parts if not p["flip"]]
            self.assertTrue(flipped and plain)
            out = fx.apply_auto_edit(FFMPEG, FFPROBE, src, tmp / "auto.mp4", cfg, "libx264", tmp / "work")
            got, ref = _frames(out), _frames(src)
            self.assertEqual(len(got), 1200)
            f = flipped[0]; mid = f["start"] + f["frames"] // 2
            self.assertLess(_d(got[mid], ref[mid].reshape(H, W)[:, ::-1].reshape(-1)), 6.0)
            self.assertGreater(_d(got[mid], ref[mid]), 12.0)
            p = plain[0]; mid = p["start"] + p["frames"] // 2
            self.assertLess(_d(got[mid], ref[mid]), 6.0)

    def test_auto_edit_with_every_effect_renders_and_keeps_the_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "in.mp4"
            _source(src, 45)
            logs: list[str] = []
            cfg = {"enabled": True, "effects": list(fx.AUTO_EFFECTS), "intensity": "High", "slow_seconds": 5, "hold_seconds": 2, "seed": 11}
            out = fx.apply_auto_edit(FFMPEG, FFPROBE, src, tmp / "auto.mp4", cfg, "libx264", tmp / "work", log=logs.append)
            self.assertEqual(len(_frames(out)), 1350)
            self.assertEqual(fx.probe_frames(FFPROBE, out), 1350)
            text = "\n".join(logs)
            self.assertIn("Auto edit (High, seed 11)", text)
            self.assertIn("Auto edit done", text)
            self.assertEqual([d.name for d in (tmp / "work").glob("fx_auto_*")], [])      # temp parts cleaned up

    def test_auto_edit_that_chooses_nothing_leaves_the_video_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "in.mp4"
            _source(src, 3)
            self.assertEqual(fx.apply_auto_edit(FFMPEG, FFPROBE, src, tmp / "o.mp4", {"enabled": True, "effects": []}, "libx264", tmp / "w"), src)

    def test_stop_keeps_the_finished_parts_and_resume_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "in.mp4"
            _source(src, 40)
            cfg = {"enabled": True, "gap_seconds": 10, "slow_seconds": 5}
            calls = {"n": 0}
            def stop():
                calls["n"] += 1
                return calls["n"] > 2
            with self.assertRaises(InterruptedError):
                fx.apply_slow_motion(FFMPEG, FFPROBE, src, tmp / "o.mp4", cfg, "libx264", tmp / "work", should_stop=stop)
            self.assertEqual(len(list((tmp / "work").glob("fx_slow_*/part_*.mp4"))), 2)
            out = fx.apply_slow_motion(FFMPEG, FFPROBE, src, tmp / "o.mp4", cfg, "libx264", tmp / "work")
            self.assertEqual(fx.probe_frames(FFPROBE, out), 1200)
            self.assertNotEqual(out, src)


if __name__ == "__main__":
    unittest.main()
