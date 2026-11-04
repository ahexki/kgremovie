"""Moving the Extra text box: pure geometry, and the App's drag / slider / button logic (with a tkinter stand-in)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "app"), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

import layout_math as lm  # noqa: E402


class GeometryTests(unittest.TestCase):
    def test_the_box_never_leaves_the_picture(self):
        half = (0.2, 0.05)
        self.assertEqual(lm.clamp_center((0.0, 0.0), half), [0.2 + lm.EDGE_MARGIN, 0.05 + lm.EDGE_MARGIN])
        self.assertEqual(lm.clamp_center((1.0, 1.0), half), [1 - 0.2 - lm.EDGE_MARGIN, 1 - 0.05 - lm.EDGE_MARGIN])
        self.assertEqual(lm.clamp_center((0.5, 0.5), half), [0.5, 0.5])
        self.assertEqual(lm.clamp_center((0.1, 0.9), (0.6, 0.0)), [0.5, 0.9])      # wider than the picture: centred

    def test_dragging_keeps_the_grab_point(self):
        # picture 800x450 at (80, 20); box centre at (0.5, 0.84); the user grabs 30 px right of and 10 px above the centre
        origin, size = (80, 20), (800, 450)
        centre_px = (80 + 0.5 * 800, 20 + 0.84 * 450)
        grab = (30.0, -10.0)
        mouse = (centre_px[0] + grab[0], centre_px[1] + grab[1])
        self.assertEqual([round(v, 4) for v in lm.drag_position(mouse, grab, origin, size)], [0.5, 0.84])   # no jump on a click
        moved = lm.drag_position((mouse[0] + 80, mouse[1] - 45), grab, origin, size)
        self.assertEqual([round(v, 4) for v in moved], [0.6, 0.74])
        out = lm.drag_position((-500, 5000), grab, origin, size, (0.1, 0.05))
        self.assertEqual(out, [0.1 + lm.EDGE_MARGIN, 1 - 0.05 - lm.EDGE_MARGIN])

    def test_snapping_to_the_middle(self):
        self.assertEqual(lm.snap_center((0.505, 0.84)), ([0.5, 0.84], (True, False)))
        self.assertEqual(lm.snap_center((0.52, 0.495)), ([0.52, 0.5], (False, True)))
        self.assertEqual(lm.snap_center((0.3, 0.2)), ([0.3, 0.2], (False, False)))

    def test_slider_conversion_round_trips(self):
        self.assertEqual(lm.slider_to_pos(50, 84), [0.5, 0.84])
        self.assertEqual(lm.pos_to_slider([0.25, 0.7]), (25.0, 70.0))
        self.assertEqual(lm.slider_to_pos(0, 100, (0.1, 0.1)), [0.11, 0.89])

    def test_saved_positions_are_repaired(self):
        self.assertEqual(lm.normalize_pos([0.3, 0.4]), [0.3, 0.4])
        for bad in (None, [], [2, 0.5], ["a", "b"], "xy", [0.5]):
            self.assertEqual(lm.normalize_pos(bad), [0.5, 0.84], bad)
        self.assertEqual(lm.normalize_pos(None, (0.2, 0.3)), [0.2, 0.3])


class FakeCanvas:
    """What the app asks the preview canvas for while dragging."""
    def __init__(self):
        self.box = (300.0, 380.0, 500.0, 420.0)

    def bbox(self, tag):
        return self.box if tag == "extra_text" else None

    def find_overlapping(self, *a):
        return (1,)

    def gettags(self, item):
        return ("editor", "extra_text")

    def __getattr__(self, name):
        return lambda *a, **k: 0


class Event:
    def __init__(self, x, y):
        self.x, self.y = x, y


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tk_stub
        cls._saved = {k: sys.modules.get(k) for k in ("tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "controller")}
        for k in cls._saved:
            sys.modules.pop(k, None)
        tk_stub.install()
        import controller
        cls.controller = controller

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def _app(self):
        c = self.controller
        c.load_config = lambda: {}
        app = c.App.__new__(c.App)
        c.App.__init__(app)
        app.preview_canvas = FakeCanvas()
        app.extra_text.set("မင်္ဂလာပါ")
        app._draw_blur_mode = False
        return app

    def test_default_position_and_sliders(self):
        app = self._app()
        self.assertEqual(app.extra_text_pos, [0.5, 0.84])
        self.assertEqual((app.extra_x_var.get(), app.extra_y_var.get()), (50.0, 84.0))

    def test_sliders_move_the_box(self):
        app = self._app()
        app.extra_x_var.set(20)
        app.extra_y_var.set(10)
        app._extra_pos_slider_changed()
        self.assertEqual(app.extra_text_pos, [0.2, 0.1])
        app._extra_half = (0.15, 0.04)
        app.extra_x_var.set(0)
        app._extra_pos_slider_changed()
        self.assertEqual(app.extra_text_pos[0], 0.15 + 0.01)                           # not out of the picture

    def test_buttons(self):
        app = self._app()
        app._set_extra_pos(0.2, 0.3)
        app._set_extra_pos(0.5, app.extra_text_pos[1])                                 # Center
        self.assertEqual(app.extra_text_pos, [0.5, 0.3])
        self.assertEqual((app.extra_x_var.get(), app.extra_y_var.get()), (50.0, 30.0))
        app._set_extra_pos(*self.controller.lm.DEFAULT_EXTRA_POS)                       # Bottom
        self.assertEqual(app.extra_text_pos, [0.5, 0.84])

    def test_dragging_with_the_mouse(self):
        app = self._app()
        ox, oy, pw, ph = app._preview_bounds()
        start = (ox + 0.5 * pw + 25, oy + 0.84 * ph + 6)                                 # the user grabs next to the centre
        app._preview_press(Event(*start))
        self.assertEqual(app._drag_kind, "extra_text")
        self.assertEqual(app.extra_text_pos, [0.5, 0.84], "a click alone does not move the box")
        app._preview_motion(Event(start[0] + 0.1 * pw, start[1] - 0.2 * ph))
        self.assertAlmostEqual(app.extra_text_pos[0], 0.6, places=3)
        self.assertAlmostEqual(app.extra_text_pos[1], 0.64, places=3)
        self.assertEqual((round(app.extra_x_var.get()), round(app.extra_y_var.get())), (60, 64))   # the sliders follow
        app._preview_motion(Event(start[0] + 0.005 * pw, start[1] - 0.2 * ph))                    # near the middle: snap
        self.assertEqual(app.extra_text_pos[0], 0.5)
        self.assertTrue(app._extra_snap[0])
        app._preview_release(Event(start[0], start[1]))
        self.assertEqual(app._extra_snap, (False, False))
        self.assertIsNone(app._drag_kind)

    def test_dragging_far_outside_stops_at_the_edge(self):
        app = self._app()
        ox, oy, pw, ph = app._preview_bounds()
        app._preview_press(Event(ox + 0.5 * pw, oy + 0.84 * ph))
        app._extra_half = (0.1, 0.03)
        app._preview_motion(Event(ox - 400, oy - 400))
        self.assertEqual(app.extra_text_pos, [0.1 + 0.01, 0.03 + 0.01])

    def test_the_position_is_saved_and_restored(self):
        app = self._app()
        app._set_extra_pos(0.3, 0.2)
        saved = {}
        c = self.controller
        c.save_config = lambda cfg: saved.update(cfg)
        c.load_config = lambda: dict(saved)
        import shutil, tempfile
        from pathlib import Path as P
        tmp = P(tempfile.mkdtemp())
        vid, env = tmp / "a.mp4", tmp / ".env"
        vid.write_bytes(b"x")
        env.write_text("GEMINI_API_KEY=x\n")
        app.source.set(str(vid))
        app.gemini_env.set(str(env))
        c._tool_path = lambda cfg, tool: shutil.which(tool)
        app._save_cfg(app._capture_settings())
        self.assertEqual(saved["extra_text_position"], [0.3, 0.2])
        app2 = c.App.__new__(c.App)
        c.App.__init__(app2)
        self.assertEqual(app2.extra_text_pos, [0.3, 0.2])
        self.assertEqual((app2.extra_x_var.get(), app2.extra_y_var.get()), (30.0, 20.0))


if __name__ == "__main__":
    unittest.main()
