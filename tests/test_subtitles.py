"""Burned-in Myanmar subtitles: size 9 / 12 / 14 and four styles (yellow + black stroke and three more)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
for p in (str(APP), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import subtitles as subs  # noqa: E402

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
UNIFONT = Path("/usr/share/fonts/opentype/unifont/unifont.otf")      # the only Myanmar-capable font of the test sandbox


def _browser_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        return True
    except Exception:
        return False


HAVE_BROWSER = UNIFONT.is_file() and _browser_ok()
TEXT_1 = "မင်္ဂလာပါ ဒီနေ့ ရာသီဥတု ကောင်းပါတယ်။"
TEXT_2 = ("အဘိုးအိုက စူးစမ်းချင်စိတ်နဲ့ သေတ္တာကို ဖွင့်ကြည့်လိုက်ပါတယ်။ အထဲမှာ ရှေးဟောင်းဓားတစ်လက် ရှိနေပါတယ်။ "
          "ရွာသားတွေက ဒီဓားဟာ ဘေးအန္တရာယ် ယူလာမယ်လို့ ပြောကြပါတယ်။ ဒါပေမဲ့ အဘိုးအိုက မယုံပါဘူး။")


class SettingsTests(unittest.TestCase):
    def test_four_styles_and_three_sizes(self):
        self.assertEqual(subs.SUB_SIZES, (9, 12, 14))
        self.assertEqual(len(subs.SUB_STYLES), 4)
        self.assertEqual(next(iter(subs.SUB_STYLES.items())), ("Yellow · black stroke", "yellow_black"))   # the default
        self.assertEqual(subs.normalize_subtitles({})["style"], "yellow_black")

    def test_settings_are_cleaned(self):
        self.assertEqual(subs.normalize_subtitles({"enabled": 1, "size": "13.6", "style": "White on black box"}),
                         {"enabled": True, "size": 14, "style": "white_box", "position": [0.5, 0.945]})
        self.assertEqual(subs.normalize_subtitles({"size": 10})["size"], 9)
        self.assertEqual(subs.normalize_subtitles({"size": 13})["size"], 12)          # exactly between: the smaller one
        self.assertEqual(subs.normalize_subtitles({"size": "x", "style": "nonsense"}),
                         {"enabled": False, "size": 12, "style": "yellow_black", "position": [0.5, 0.945]})
        self.assertEqual(subs.normalize_subtitles({"style": "black_yellow"})["style"], "black_yellow")

    def test_pixel_size_follows_the_canvas(self):
        self.assertEqual([subs.subtitle_px(n, 1920, 1080) for n in (9, 12, 14)], [36, 48, 56])
        self.assertEqual([subs.subtitle_px(n, 1080, 1920) for n in (9, 12, 14)], [36, 48, 56])    # 9:16 looks the same
        self.assertEqual(subs.subtitle_px(12, 1280, 720), 32)
        h, bottom, w = subs.strip_geometry(48, 1920, 1080)
        self.assertEqual(w, 1920)
        self.assertGreater(h, 48 * 2.7 + bottom)                                                   # room for two lines

    def test_position_defaults_to_the_old_bottom_centre_and_is_repaired(self):
        self.assertEqual(subs.normalize_subtitles({})["position"], [0.5, 0.945])
        self.assertEqual(subs.normalize_subtitles({"position": [0.3, 0.4]})["position"], [0.3, 0.4])
        self.assertEqual(subs.normalize_subtitles({"position": [0.1, 0.5]})["position"], [0.15, 0.5])    # x stays 15-85 %
        self.assertEqual(subs.normalize_subtitles({"position": "x"})["position"], [0.5, 0.945])
        self.assertEqual(subs.normalize_subtitles({"position": [2, 2]})["position"], [0.5, 0.945])

    def test_layout_keeps_the_subtitle_inside_the_picture(self):
        x, y, w = subs.subtitle_layout({"size": 12}, 1920, 1080)
        self.assertEqual((x, y), (0.5, 0.945))
        self.assertAlmostEqual(w, subs.TEXT_WIDTH_FRACTION)
        x, y, w = subs.subtitle_layout({"size": 12, "position": [0.15, 0.01]}, 1920, 1080)
        self.assertAlmostEqual(y, 2 * subs.text_half_height(12, 1920, 1080))                 # the top of the text is the picture's top
        self.assertAlmostEqual(w, 2 * 0.15 - 0.04)                                           # narrower near a side
        self.assertAlmostEqual(subs.subtitle_layout({"size": 12, "position": [0.8, 0.5]}, 1920, 1080)[2], 2 * 0.2 - 0.04)
        self.assertGreater(subs.text_half_height(14, 1920, 1080), subs.text_half_height(9, 1920, 1080))


class CueTests(unittest.TestCase):
    def test_a_short_line_is_one_subtitle(self):
        cues = subs.split_cues(TEXT_1, 2.0, 5.0, max_em=40)
        self.assertEqual(cues, [{"text": TEXT_1, "start": 2.0, "end": 5.0}])
        self.assertEqual(subs.split_cues("", 0, 3, max_em=40), [])
        self.assertEqual(subs.split_cues("စာ", 3, 3, max_em=40), [])

    def test_a_long_line_is_cut_at_sentence_ends_and_shares_the_time(self):
        cues = subs.split_cues(TEXT_2, 10.0, 22.0, max_em=40)
        self.assertGreaterEqual(len(cues), 2)
        self.assertTrue(all(c["text"].rstrip().endswith("။") for c in cues[:-1]))
        self.assertEqual(cues[0]["start"], 10.0)
        self.assertEqual(cues[-1]["end"], 22.0)
        for a, b in zip(cues, cues[1:]):                                     # contiguous, nothing lost
            self.assertAlmostEqual(a["end"], b["start"], places=2)
        strip = lambda t: "".join(ch for ch in t if not ch.isspace())
        self.assertEqual(strip("".join(c["text"] for c in cues)), strip(TEXT_2))
        self.assertTrue(all(subs.est_em(c["text"]) <= 40 for c in cues))

    def test_text_without_any_space_or_punctuation_is_still_cut(self):
        cues = subs.split_cues("က" * 400, 0, 20, max_em=30)
        self.assertGreater(len(cues), 5)
        self.assertEqual("".join(c["text"] for c in cues).replace(" ", ""), "က" * 400)
        self.assertTrue(all(subs.est_em(c["text"]) <= 30.5 for c in cues))

    def test_a_cue_is_never_flashed_for_a_blink(self):
        cues = subs.split_cues("က။ ခ။ ဂ။ ဃ။ င။", 0, 1.0, max_em=3)
        self.assertTrue(all(c["end"] - c["start"] >= subs.MIN_CUE_SECONDS - 0.01 for c in cues), cues)

    def test_cue_budget_follows_the_size(self):
        timeline = [{"start": 0.0, "end": 10.0, "text": TEXT_2}]
        small = subs.build_cues(timeline, canvas_w=1920, px=36)
        large = subs.build_cues(timeline, canvas_w=1920, px=56)
        self.assertLessEqual(len(small), len(large))
        self.assertEqual(subs.build_cues([{"start": 0, "end": 3, "text": "   "}], canvas_w=1920, px=48), [])


class ListTests(unittest.TestCase):
    def test_concat_list_has_gaps_cues_and_a_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            gap, a, b = tmp / "gap.png", tmp / "it's a.png", tmp / "b.png"
            cues = [{"text": "A", "start": 1.0, "end": 2.5}, {"text": "B", "start": 3.0, "end": 4.2}]
            path = subs.write_concat_list(cues, {"A": a, "B": b}.__getitem__, gap, 6.0, tmp / "l.txt")
            lines = path.read_text(encoding="utf-8").splitlines()
            files = [l for l in lines if l.startswith("file ")]
            durations = [float(l.split()[1]) for l in lines if l.startswith("duration ")]
            self.assertEqual([Path(f[6:-1].replace("'\\''", "'")).name for f in files],
                             ["gap.png", "it's a.png", "gap.png", "b.png", "gap.png", "gap.png"])   # last file repeated
            self.assertEqual(len(durations), len(files) - 1)
            self.assertAlmostEqual(sum(durations[:4]), 4.2, places=2)             # up to the end of the last cue
            self.assertAlmostEqual(sum(durations), 6.0 + subs.TAIL_SECONDS, places=2)
            self.assertIn("it'\\''s a.png", lines[2])                                # a quote in a path is escaped

    def test_overlapping_cues_never_run_backwards(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            cues = [{"text": "A", "start": 0.0, "end": 3.0}, {"text": "B", "start": 2.0, "end": 5.0}]
            path = subs.write_concat_list(cues, lambda t: tmp / f"{t}.png", tmp / "gap.png", 5.0, tmp / "l.txt")
            durations = [float(l.split()[1]) for l in path.read_text().splitlines() if l.startswith("duration ")]
            self.assertTrue(all(d > 0 for d in durations))
            self.assertAlmostEqual(sum(durations[:2]), 5.0, places=2)


class PrepareTests(unittest.TestCase):
    def _fake_renderer(self, calls):
        from PIL import Image
        def render(texts, out_dir, cfg):
            calls.append((list(texts), dict(cfg)))
            out = []
            for i, _t in enumerate(texts, 1):
                p = out_dir / f"sub_{i:05d}.png"
                Image.new("RGBA", (cfg["width"], cfg["height"]), (255, 0, 0, 120)).save(p)
                out.append(p)
            return out
        return render

    def test_disabled_does_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            self.assertIsNone(subs.prepare_subtitles([{"start": 0, "end": 3, "text": "စာ"}], 3, (1920, 1080), {"enabled": False},
                                                     Path(tmp), renderer=self._fake_renderer(calls)))
            self.assertEqual(calls, [])

    def test_settings_reach_the_renderer_and_the_result_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            timeline = [{"start": 0, "end": 3, "text": TEXT_1}, {"start": 3, "end": 9, "text": TEXT_2}]
            calls: list = []
            cfg = {"enabled": True, "size": 14, "style": "White on black box"}
            first = subs.prepare_subtitles(timeline, 9, (1920, 1080), cfg, tmp, renderer=self._fake_renderer(calls))
            self.assertTrue(first.is_file())
            sent = calls[0][1]
            self.assertEqual((sent["font_size"], sent["style"], sent["width"]), (56, "white_box", 1920))
            self.assertGreater(sent["height"], 56 * 2.7)
            self.assertEqual(len(calls[0][0]), len(set(calls[0][0])))                      # identical lines render once
            again = subs.prepare_subtitles(timeline, 9, (1920, 1080), cfg, tmp, renderer=self._fake_renderer(calls))
            self.assertEqual(again, first)
            self.assertEqual(len(calls), 1, "same text, size and style: the PNGs are reused (START / RESUME)")
            subs.prepare_subtitles(timeline, 9, (1920, 1080), {**cfg, "style": "yellow_black"}, tmp,
                                   renderer=self._fake_renderer(calls))
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(list(tmp.glob("subtitles_*"))), 1, "the PNGs of the old settings are removed")

    def test_a_side_position_gives_narrower_text_and_new_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            timeline = [{"start": 0, "end": 9, "text": TEXT_2}]
            calls: list = []
            subs.prepare_subtitles(timeline, 9, (1920, 1080), {"enabled": True, "size": 12}, tmp,
                                   renderer=self._fake_renderer(calls))
            subs.prepare_subtitles(timeline, 9, (1920, 1080), {"enabled": True, "size": 12, "position": [0.2, 0.5]}, tmp,
                                   renderer=self._fake_renderer(calls))
            self.assertEqual(len(calls), 2, "a different text width cannot reuse the old PNGs")
            self.assertAlmostEqual(calls[0][1]["max_width_pct"], 86.0)
            self.assertAlmostEqual(calls[1][1]["max_width_pct"], 36.0)
            self.assertGreater(len(calls[1][0]), len(calls[0][0]), "narrower text is split into more subtitles")

    def test_moving_the_subtitle_up_or_down_reuses_the_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            timeline = [{"start": 0, "end": 9, "text": TEXT_2}]
            calls: list = []
            for pos in ([0.5, 0.945], [0.5, 0.4]):
                subs.prepare_subtitles(timeline, 9, (1920, 1080), {"enabled": True, "size": 12, "position": pos}, tmp,
                                       renderer=self._fake_renderer(calls))
            self.assertEqual(len(calls), 1, "only the overlay position changes, the pictures stay the same")

    def test_no_text_means_no_track(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(subs.prepare_subtitles([{"start": 0, "end": 3, "text": " "}], 3, (1920, 1080), {"enabled": True},
                                                     Path(tmp), renderer=self._fake_renderer([])))


@unittest.skipUnless(HAVE_BROWSER, "needs Playwright Chromium and a Myanmar-capable font")
class ChromiumTests(unittest.TestCase):
    def setUp(self):
        self._font = os.environ.get("RECAP_MM_FONT")
        os.environ["RECAP_MM_FONT"] = str(UNIFONT)

    def tearDown(self):
        if self._font is None:
            os.environ.pop("RECAP_MM_FONT", None)
        else:
            os.environ["RECAP_MM_FONT"] = self._font

    def _render(self, tmp, style, size_px=48, texts=(TEXT_1, TEXT_2)):
        from services.text_overlay_service import make_subtitle_pngs
        return make_subtitle_pngs(list(texts), tmp / style, {"width": 1280, "height": 230, "font_size": size_px, "style": style,
                                                             "bottom_margin": 40})

    @staticmethod
    def _rgba(path):
        from PIL import Image
        return np.asarray(Image.open(path).convert("RGBA")).astype(int)

    @staticmethod
    def _ink_box(rgba):
        ys, xs = np.nonzero(rgba[..., 3] > 40)
        return (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else None

    def test_every_png_has_the_same_size_and_a_transparent_background(self):
        cues = [c["text"] for c in subs.split_cues(TEXT_2, 0, 20, max_em=30)][:2] + [TEXT_1]   # what the pipeline really sends
        with tempfile.TemporaryDirectory() as tmp:
            for style in subs.SUB_STYLE_LABELS:
                for p in self._render(Path(tmp), style, texts=cues):
                    img = self._rgba(p)
                    self.assertEqual(img.shape, (230, 1280, 4), style)
                    self.assertEqual(int(img[0, 0, 3]), 0, style)            # corners are see-through
                    self.assertEqual(int(img[0, -1, 3]), 0, style)
                    x0, y0, x1, y1 = self._ink_box(img)
                    self.assertGreater(y0, 20, style)                         # the text sits in the lower part of the strip
                    self.assertLess(y1, 230 - 40 + 6, style)                  # ... above the bottom margin
                    self.assertTrue(0 < x0 and x1 < 1279, style)

    def test_yellow_with_black_stroke(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = self._rgba(self._render(Path(tmp), "yellow_black")[0])
            solid = img[img[..., 3] > 250]
            yellow = ((solid[:, 0] > 230) & (solid[:, 1] > 180) & (solid[:, 2] < 60)).sum()
            black = ((solid[:, 0] < 30) & (solid[:, 1] < 30) & (solid[:, 2] < 30)).sum()
            self.assertGreater(yellow, 300)                                   # yellow letters ...
            self.assertGreater(black, 300)                                    # ... with a black outline around them
            white = ((solid[:, 0] > 240) & (solid[:, 1] > 240) & (solid[:, 2] > 240)).sum()
            self.assertEqual(white, 0)

    def test_white_with_black_stroke(self):
        with tempfile.TemporaryDirectory() as tmp:
            solid = self._rgba(self._render(Path(tmp), "white_black")[0])
            solid = solid[solid[..., 3] > 250]
            self.assertGreater(((solid[:, 0] > 240) & (solid[:, 1] > 240) & (solid[:, 2] > 240)).sum(), 300)
            self.assertGreater(((solid[:, 0] < 30) & (solid[:, 1] < 30) & (solid[:, 2] < 30)).sum(), 300)

    def test_the_two_box_styles_have_a_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            dark = self._rgba(self._render(Path(tmp), "white_box")[0])
            ys, xs = np.nonzero(dark[..., 3] > 100)
            box_pixel = dark[ys.min() + 3, (xs.min() + xs.max()) // 2]              # inside the box, above the letters
            self.assertTrue(box_pixel[0] < 20 and 120 < box_pixel[3] < 200, box_pixel)   # translucent black
            yellow = self._rgba(self._render(Path(tmp), "black_yellow")[0])
            ys, xs = np.nonzero(yellow[..., 3] > 100)
            box_pixel = yellow[ys.min() + 3, (xs.min() + xs.max()) // 2]
            self.assertTrue(box_pixel[0] > 230 and box_pixel[1] > 180 and box_pixel[2] < 40 and box_pixel[3] > 230, box_pixel)

    def test_a_bigger_size_makes_bigger_letters(self):
        with tempfile.TemporaryDirectory() as tmp:
            heights = {}
            for n in (9, 12, 14):
                px = subs.subtitle_px(n, 1920, 1080)
                path = self._render(Path(tmp) / str(n), "white_black", px, texts=(TEXT_1,))[0]
                x0, y0, x1, y1 = self._ink_box(self._rgba(path))
                heights[n] = (y1 - y0, x1 - x0)
            self.assertLess(heights[9][0], heights[12][0])
            self.assertLess(heights[12][0], heights[14][0])
            self.assertLess(heights[9][1], heights[12][1])
            self.assertLess(heights[12][1], heights[14][1])

    def test_a_line_that_is_too_long_still_fits_in_two_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            long = " ".join(TEXT_2.split("။")[:2]) + "။"       # two sentences: a full-size cue; it must shrink, not be cut off
            x0, y0, x1, y1 = self._ink_box(self._rgba(self._render(Path(tmp), "white_black", 56, texts=(long,))[0]))
            self.assertGreater(y0, 0, "the text was shrunk instead of being cut off at the top")
            self.assertLessEqual(y1, 230 - 40 + 6)
            self.assertTrue(x0 > 0 and x1 < 1279)


def _tone(path: Path, seconds: float) -> str:
    t = np.arange(int(24000 * seconds)) / 24000
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes((np.sin(2 * np.pi * 300 * t) * 9000).astype("<i2").tobytes())
    return str(path)


class _Edge:
    def __init__(self, **kw):
        self.n = 0
        self.dir = Path(kw["work_dir"])
        self.dir.mkdir(parents=True, exist_ok=True)

    def generate_channel99_voice(self, text, voice=""):
        self.n += 1
        return _tone(self.dir / f"t{self.n}.wav", 4.0)


@unittest.skipUnless(FFMPEG and FFPROBE and HAVE_BROWSER, "needs ffmpeg, Chromium and a Myanmar-capable font")
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self._font = os.environ.get("RECAP_MM_FONT")
        os.environ["RECAP_MM_FONT"] = str(UNIFONT)

    def tearDown(self):
        if self._font is None:
            os.environ.pop("RECAP_MM_FONT", None)
        else:
            os.environ["RECAP_MM_FONT"] = self._font

    def _run(self, tmp: Path, name: str, **kw):
        import core
        src = tmp / "clip.mp4"
        if not src.exists():
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x303030:s=320x180:r=30:d=12",
                            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-g", "30", str(src)], check=True)
        job = tmp / name
        job.mkdir()
        narration = ["မင်္ဂလာပါ ဒီနေ့ ရာသီဥတု ကောင်းပါတယ်။", "အဘိုးအိုက သေတ္တာကို ဖွင့်ကြည့်လိုက်ပါတယ်။", "ရွာသားတွေက ဘေးအန္တရာယ် ယူလာမယ်လို့ ပြောကြပါတယ်။"]
        plan = {"segments": [{"video_start": i * 4.0, "video_end": i * 4.0 + 4.0, "narration": narration[i]} for i in range(3)]}
        (job / "smart_sync_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        logs: list[str] = []
        real = core.EdgeTTSEngine
        core.EdgeTTSEngine = _Edge
        try:
            runner = core.EdgeSmartSync(job_dir=str(job), source_path=str(src), plan_path=str(job / "smart_sync_plan.json"),
                                        voice="my-MM-ThihaNeural", ffmpeg_path=FFMPEG, ffprobe_path=FFPROBE, output_ratio="16:9",
                                        log=logs.append, **kw)
            result = runner.run()
        finally:
            core.EdgeTTSEngine = real
        return result, "\n".join(logs)

    @staticmethod
    def _frames(path: Path):
        out = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(path), "-vf", "scale=640:360", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        n = 640 * 360 * 3
        return [np.frombuffer(out[i:i + n], dtype=np.uint8).reshape(360, 640, 3) for i in range(0, len(out), n)]

    def test_subtitles_appear_with_the_voice_and_do_not_change_the_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            plain, _ = self._run(tmp, "plain")
            result, text = self._run(tmp, "subs", subtitles={"enabled": True, "size": 14, "style": "Yellow · black stroke"})
            self.assertAlmostEqual(plain["duration"], result["duration"], delta=0.1)
            self.assertIn("Subtitles: 3 line(s) | size 14 (56px) | Yellow · black stroke", text)
            a, b = self._frames(Path(plain["final"])), self._frames(Path(result["final"]))
            self.assertEqual(len(a), len(b))
            yellow = lambda f: int(((f[..., 0] > 200) & (f[..., 1] > 160) & (f[..., 2] < 90)).sum())
            bottom = lambda f: f[200:, :, :]
            for t in (2.0, 6.0, 10.0):                                       # the middle of each narration line
                i = int(t * 30)
                self.assertEqual(yellow(bottom(a[i])), 0, t)
                self.assertGreater(yellow(bottom(b[i])), 80, t)
                self.assertEqual(yellow(b[i][:150]), 0, "nothing above the bottom strip")
            # a different line is a different picture
            self.assertGreater(float(np.abs(bottom(b[60]).astype(int) - bottom(b[180]).astype(int)).mean()), 1.0)

    def test_subtitles_alone_are_enough_to_run_the_overlay_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, text = self._run(Path(tmp), "only", subtitles={"enabled": True, "size": 9, "style": "white_box"})
            self.assertIn("Production overlay pass", text)
            self.assertTrue(Path(result["final"]).is_file())

    def test_off_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            _r, text = self._run(Path(tmp), "off")
            self.assertNotIn("Subtitles", text)
            self.assertNotIn("Production overlay pass", text)


@unittest.skipUnless(FFMPEG, "needs ffmpeg")
class OverlayPlacementTests(unittest.TestCase):
    """core.apply_production_overlays puts the bottom centre of the subtitle text on subtitle_position."""
    W, H, STRIP_H, BOTTOM, TEXT_H = 320, 180, 62, 12, 50

    def _white_box(self, tmp: Path, position):
        import core
        from PIL import Image
        src = tmp / "base.mp4"
        if not src.exists():
            # dark noise: a flat clip encodes to ~2 KB and the overlay pass rejects outputs under 5000 bytes
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"color=c=black:s={self.W}x{self.H}:r=10:d=2,noise=alls=20:allf=t",
                            "-pix_fmt", "yuv420p", "-c:v", "libx264", str(src)], check=True)
        strip = Image.new("RGBA", (self.W, self.STRIP_H), (0, 0, 0, 0))
        strip.paste((255, 255, 255, 255), (140, 0, 180, self.TEXT_H))          # the "text": 40 px wide, centred in the strip
        png = tmp / "strip.png"
        strip.save(png)
        lst = tmp / "strip.txt"
        lst.write_text(f"file '{png.as_posix()}'\nduration 2.0\nfile '{png.as_posix()}'\n", encoding="utf-8")
        (tmp / "work").mkdir(exist_ok=True)
        out = core.apply_production_overlays(
            FFMPEG, src, tmp / f"out_{position[0]}_{position[1]}.mp4",
            {"logo_enabled": False, "subtitle_list": str(lst), "subtitle_position": position, "subtitle_bottom": self.BOTTOM},
            "libx264", tmp / "work", frame_size=(self.W, self.H))
        raw = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(out), "-frames:v", "1", "-vf", "format=gray",
                              "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.H, self.W)
        ys, xs = np.where(frame > 128)
        self.assertGreater(len(ys), 0, "the subtitle must be visible")
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    def test_the_text_lands_on_the_chosen_bottom_centre(self):
        with tempfile.TemporaryDirectory() as tmp:
            x1, y1, x2, y2 = self._white_box(Path(tmp), [0.25, 0.5])
            self.assertAlmostEqual((x1 + x2) / 2, self.W * 0.25, delta=2)                  # centred on x = 25 %
            self.assertAlmostEqual(y2, self.H * 0.5, delta=2)                              # bottom of the text on y = 50 %
            self.assertAlmostEqual(y2 - y1, self.TEXT_H, delta=2)

    def test_the_old_default_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            x1, y1, x2, y2 = self._white_box(Path(tmp), [0.5, 0.945])
            self.assertAlmostEqual((x1 + x2) / 2, self.W / 2, delta=2)
            self.assertAlmostEqual(y2, self.H * 0.945, delta=2)


if __name__ == "__main__":
    unittest.main()
