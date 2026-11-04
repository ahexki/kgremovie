"""Moving the Myanmar subtitle: pure geometry, and the App's drag / slider / button / save logic (with a tkinter stand-in)."""
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
    def test_the_subtitle_never_leaves_the_picture(self):
        half = 0.06                                                   # half the height of a two-line subtitle
        self.assertEqual(lm.clamp_sub_pos((0.0, 0.0), half), [lm.SUB_X_RANGE[0], 2 * half + lm.EDGE_MARGIN])
        self.assertEqual(lm.clamp_sub_pos((1.0, 1.0), half), [lm.SUB_X_RANGE[1], 1 - lm.EDGE_MARGIN])
        self.assertEqual(lm.clamp_sub_pos((0.4, 0.7), half), [0.4, 0.7])
        self.assertEqual(lm.clamp_sub_pos((0.4, 0.7), 0.7), [0.4, 0.5])        # taller than the picture: centred

    def test_dragging_keeps_the_grab_point(self):
        origin, size = (80, 20), (800, 450)
        bottom_px = (80 + 0.5 * 800, 20 + 0.945 * 450)
        grab = (30.0, -10.0)
        mouse = (bottom_px[0] + grab[0], bottom_px[1] + grab[1])
        self.assertEqual([round(v, 4) for v in lm.drag_sub_position(mouse, grab, origin, size)], [0.5, 0.945])
        moved = lm.drag_sub_position((mouse[0] - 80, mouse[1] - 90), grab, origin, size)
        self.assertEqual([round(v, 4) for v in moved], [0.4, 0.745])

    def test_snapping_to_the_middle(self):
        self.assertEqual(lm.snap_x((0.505, 0.6)), ([0.5, 0.6], True))
        self.assertEqual(lm.snap_x((0.3, 0.6)), ([0.3, 0.6], False))


class FakeCanvas:
    """What the app asks the preview canvas for while dragging."""
    def find_overlapping(self, *a):
        return (1,)

    def gettags(self, item):
        return ("editor", "sub_text")

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
        app.sub_enabled.set(True)
        app._draw_blur_mode = False
        return app

    def test_default_position_and_sliders(self):
        app = self._app()
        self.assertEqual(app.sub_pos, [0.5, 0.945])
        self.assertEqual((app.sub_x_var.get(), app.sub_y_var.get()), (50.0, 94.5))

    def test_sliders_move_the_subtitle(self):
        app = self._app()
        app.sub_x_var.set(30)
        app.sub_y_var.set(40)
        app._sub_pos_slider_changed()
        self.assertEqual(app.sub_pos, [0.3, 0.4])
        app.sub_y_var.set(0)
        app._sub_pos_slider_changed()
        self.assertAlmostEqual(app.sub_pos[1], 2 * app._sub_half_h() + lm.EDGE_MARGIN)       # not out of the picture

    def test_buttons(self):
        app = self._app()
        app._set_sub_pos(0.2, 0.3)
        app._set_sub_pos(0.5, app.sub_pos[1])                                                 # Center
        self.assertEqual(app.sub_pos, [0.5, 0.3])
        app._set_sub_pos(*lm.DEFAULT_SUB_POS)                                                 # Bottom
        self.assertEqual(app.sub_pos, [0.5, 0.945])
        self.assertEqual((app.sub_x_var.get(), app.sub_y_var.get()), (50.0, 94.5))

    def test_dragging_with_the_mouse(self):
        app = self._app()
        ox, oy, pw, ph = app._preview_bounds()
        start = (ox + 0.5 * pw + 25, oy + 0.945 * ph - 8)                                     # grabbed inside the box
        app._preview_press(Event(*start))
        self.assertEqual(app._drag_kind, "sub_text")
        self.assertEqual(app.sub_pos, [0.5, 0.945], "a click alone does not move the subtitle")
        app._preview_motion(Event(start[0] - 0.2 * pw, start[1] - 0.3 * ph))
        self.assertAlmostEqual(app.sub_pos[0], 0.3, places=3)
        self.assertAlmostEqual(app.sub_pos[1], 0.645, places=3)
        self.assertEqual((round(app.sub_x_var.get()), round(app.sub_y_var.get())), (30, 64))  # the sliders follow
        app._preview_motion(Event(start[0] + 0.005 * pw, start[1] - 0.3 * ph))                 # near the middle: snap
        self.assertEqual(app.sub_pos[0], 0.5)
        self.assertTrue(app._sub_snap)
        app._preview_release(Event(start[0], start[1]))
        self.assertFalse(app._sub_snap)
        self.assertIsNone(app._drag_kind)

    def test_dragging_far_outside_stops_at_the_edge(self):
        app = self._app()
        ox, oy, pw, ph = app._preview_bounds()
        app._preview_press(Event(ox + 0.5 * pw, oy + 0.945 * ph))
        app._preview_motion(Event(ox - 400, oy - 400))
        self.assertEqual(app.sub_pos, [lm.SUB_X_RANGE[0], 2 * app._sub_half_h() + lm.EDGE_MARGIN])

    def test_the_box_is_narrower_near_a_side_and_bottom_centred_on_the_position(self):
        app = self._app()
        ox, oy, pw, ph = app._preview_bounds()
        x1, y1, x2, y2 = app._sub_box()
        self.assertAlmostEqual((x1 + x2) / 2, ox + 0.5 * pw, delta=1)
        self.assertAlmostEqual(y2, oy + 0.945 * ph, delta=1)
        wide = x2 - x1
        app._set_sub_pos(0.2, 0.5)
        x1, y1, x2, y2 = app._sub_box()
        self.assertLess(x2 - x1, wide)
        self.assertAlmostEqual(y2, oy + 0.5 * ph, delta=1)

    def test_the_position_is_saved_with_the_settings_and_restored(self):
        app = self._app()
        app._set_sub_pos(0.3, 0.6)
        saved = {}
        c = self.controller
        c.save_config = lambda cfg: saved.update(cfg)
        c.load_config = lambda: dict(saved)
        import shutil, tempfile
        tmp = Path(tempfile.mkdtemp())
        vid, env = tmp / "a.mp4", tmp / ".env"
        vid.write_bytes(b"x")
        env.write_text("GEMINI_API_KEY=x\n")
        app.source.set(str(vid))
        app.gemini_env.set(str(env))
        c._tool_path = lambda cfg, tool: shutil.which(tool)
        settings = app._capture_settings()
        self.assertEqual(settings["subtitles"]["position"], [0.3, 0.6])                      # reaches the render worker
        app._save_cfg(settings)
        self.assertEqual(saved["subtitles"]["position"], [0.3, 0.6])
        app2 = c.App.__new__(c.App)
        c.App.__init__(app2)
        self.assertEqual(app2.sub_pos, [0.3, 0.6])
        self.assertEqual((app2.sub_x_var.get(), app2.sub_y_var.get()), (30.0, 60.0))


if __name__ == "__main__":
    unittest.main()
