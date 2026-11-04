"""The Version 3.0 controls of the window: voice mode, original audio, language and slow-motion speed."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "app"), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tk_stub
        cls._saved = {k: sys.modules.get(k) for k in ("tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "controller")}
        for k in cls._saved:
            sys.modules.pop(k, None)
        tk_stub.install()
        import controller
        cls.c = controller

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def _app(self, cfg=None):
        c = self.c
        c.load_config = lambda: dict(cfg or {})
        app = c.App.__new__(c.App)
        c.App.__init__(app)
        tmp = Path(tempfile.mkdtemp())
        vid, env = tmp / "a.mp4", tmp / ".env"
        vid.write_bytes(b"x")
        env.write_text("GEMINI_API_KEY=x\n")
        app.source.set(str(vid))
        app.gemini_env.set(str(env))
        c._tool_path = lambda cfg, tool: shutil.which(tool)
        return app

    def test_defaults_are_the_old_behaviour(self):
        s = self._app()._capture_settings()
        self.assertEqual(s["voice_mode"], "selected")
        self.assertEqual(s["audio_mix"], {"original_percent": 0, "duck": True})

    def test_voice_mode_and_mix_are_captured_saved_and_restored(self):
        app = self._app()
        app.voice_mode.set("Auto — by speaker")
        app.orig_percent.set(35)
        app.orig_duck.set(False)
        settings = app._capture_settings()
        self.assertEqual(settings["voice_mode"], "auto")
        self.assertEqual(settings["audio_mix"], {"original_percent": 35, "duck": False})
        saved = {}
        self.c.save_config = lambda cfg: saved.update(cfg)
        app._save_cfg(settings)
        self.assertEqual((saved["voice_mode"], saved["audio_mix"]), ("auto", {"original_percent": 35, "duck": False}))
        app2 = self._app(saved)
        self.assertEqual(app2.voice_mode.get(), "Auto — by speaker")
        self.assertEqual((app2.orig_percent.get(), app2.orig_duck.get()), (35, False))

    def test_the_modes_in_the_dropdown(self):
        import voice_gender as vg
        app = self._app()
        self.assertEqual(list(vg.VOICE_MODES), ["Selected voice", "Male voice (Thiha)", "Female voice (Nilar)", "Auto — by speaker"])
        for label, mode in vg.VOICE_MODES.items():
            app.voice_mode.set(label)
            self.assertEqual(app._capture_settings()["voice_mode"], mode)
        app.voice_mode.set("???")
        self.assertEqual(app._capture_settings()["voice_mode"], "selected")

    def test_the_slower_slow_motion_speeds(self):
        import video_fx as fx
        app = self._app()
        self.assertEqual(fx.SLOW_SPEEDS, (0.25, 0.35, 0.5, 0.7))
        app.slow_enabled.set(True)
        for label, speed in (("0.25×", 0.25), ("0.35×", 0.35), ("0.5×", 0.5), ("0.7×", 0.7)):
            app.slow_speed.set(label)
            self.assertEqual(app._capture_settings()["slow_motion"]["speed"], speed)

    def test_everything_reaches_the_render_worker_settings(self):
        app = self._app()
        app.voice_mode.set("Female voice (Nilar)")
        app.orig_percent.set(20)
        s = app._capture_settings()
        source = (ROOT / "app" / "controller.py").read_text(encoding="utf-8")
        self.assertIn('"voice_mode": settings.get("voice_mode", "selected")', source)
        self.assertIn('"audio_mix": settings.get("audio_mix") or {}', source)
        worker = (ROOT / "app" / "render_worker.py").read_text(encoding="utf-8")
        self.assertIn('voice_mode=str(cfg.get("voice_mode", "selected"))', worker)
        self.assertIn('audio_mix=cfg.get("audio_mix") or {}', worker)
        self.assertEqual((s["voice_mode"], s["audio_mix"]["original_percent"]), ("female", 20))


if __name__ == "__main__":
    unittest.main()
