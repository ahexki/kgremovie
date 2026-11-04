"""The HUD dashboard look: readable colours, the styles it registers, and the framing drawn on the preview."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "app"), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class RecordingStyle:
    configured: dict[str, dict] = {}
    mapped: dict[str, dict] = {}

    def __init__(self, *a, **k):
        pass

    def theme_use(self, *a):
        pass

    def configure(self, name, **kw):
        RecordingStyle.configured.setdefault(name, {}).update(kw)

    def map(self, name, **kw):
        RecordingStyle.mapped.setdefault(name, {}).update(kw)


class Canvas:
    """Records what the preview draws."""
    def __init__(self):
        self.lines = []
        self.deleted = []

    def delete(self, tag):
        self.deleted.append(tag)

    def create_line(self, *coords, **kw):
        self.lines.append((coords, kw))
        return 1

    def __getattr__(self, name):
        return lambda *a, **k: 1


class HudTests(unittest.TestCase):
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

    def test_every_text_colour_is_easy_to_read(self):
        c = self.c
        for name in ("FG", "MUTED", "ACCENT", "SUCCESS", "DANGER", "WARN"):
            for bg in ("BG", "PANEL", "FIELD"):
                self.assertGreaterEqual(contrast(getattr(c, name), getattr(c, bg)), 4.5, f"{name} on {bg}")
        self.assertGreaterEqual(contrast(c.ON_ACCENT, c.ACCENT), 7.0)            # the text on the solid cyan button
        self.assertGreaterEqual(contrast("#a9d8ea", "#03060a"), 7.0)             # the log
        self.assertGreater(luminance(c.ACCENT), luminance(c.BORDER))

    def test_the_look_is_dark_with_one_cyan_accent(self):
        c = self.c
        for name in ("BG", "PANEL", "FIELD"):
            self.assertLess(luminance(getattr(c, name)), 0.02, name)
        self.assertEqual(c.ACCENT, "#00e5ff")
        self.assertEqual(c.HUD_FONT, "Consolas")

    def test_the_theme_registers_the_hud_styles(self):
        c = self.c
        RecordingStyle.configured, RecordingStyle.mapped = {}, {}
        real = c.ttk.Style
        c.ttk.Style = RecordingStyle
        try:
            app = c.App.__new__(c.App)
            app._apply_dark_theme()
        finally:
            c.ttk.Style = real
        conf, mapped = RecordingStyle.configured, RecordingStyle.mapped
        self.assertEqual(conf["Accent.TButton"]["background"], c.ACCENT)
        self.assertEqual(conf["Accent.TButton"]["foreground"], c.ON_ACCENT)
        self.assertEqual(conf["TButton"]["foreground"], c.ACCENT)                   # outlined buttons: cyan text on a dark panel
        self.assertEqual(conf["TButton"]["relief"], "flat")
        self.assertEqual(conf["Hud.TLabel"]["font"][0], "Consolas")
        self.assertEqual(conf["Status.TLabel"]["foreground"], c.SUCCESS)
        self.assertEqual(conf["Horizontal.TProgressbar"]["thickness"], 6)
        self.assertEqual(conf["TEntry"]["insertcolor"], c.ACCENT)
        self.assertIn(("focus", c.ACCENT), mapped["TEntry"]["bordercolor"])         # a focused field lights up
        for name in ("TButton", "Compact.TButton", "Accent.TButton", "Danger.TButton", "TCheckbutton", "TScale" if False else "Horizontal.TScale"):
            self.assertIn(name, conf, name)

    def test_the_header_and_the_sections_use_the_hud_form(self):
        source = (ROOT / "app" / "controller.py").read_text(encoding="utf-8")
        self.assertIn('text=APP_HEADER, bg=BG, fg=ACCENT, font=(HUD_FONT, 15, "bold")', source)
        self.assertIn('text=f"▌ {text.upper()}", style=SECTION_STYLE[key]', source)
        self.assertIn('text="▌ LOGO"', source)
        self.assertNotIn("#5b8cff", source)                                          # the old blue accent is gone

    def test_every_menu_title_has_its_own_readable_colour_and_a_bigger_font(self):
        c = self.c
        self.assertEqual(len(set(c.SECTION_COLORS.values())), len(c.SECTION_COLORS))            # one colour per title
        for key, colour in c.SECTION_COLORS.items():
            for bg in ("BG", "PANEL", "FIELD"):
                self.assertGreaterEqual(contrast(colour, getattr(c, bg)), 4.5, f"{key} on {bg}")
        self.assertGreater(c.SECTION_FONT_SIZE, 10)                                              # the body text is 10 pt
        RecordingStyle.configured = {}
        real = c.ttk.Style
        c.ttk.Style = RecordingStyle
        try:
            c.App.__new__(c.App)._apply_dark_theme()
        finally:
            c.ttk.Style = real
        for key, colour in c.SECTION_COLORS.items():
            conf = RecordingStyle.configured[c.SECTION_STYLE[key]]
            self.assertEqual(conf["foreground"], colour)
            self.assertEqual(conf["font"][1], c.SECTION_FONT_SIZE)
        self.assertEqual(RecordingStyle.configured["Hint.TLabel"]["font"][0], "Myanmar Text")   # Burmese descriptions

    def test_layout_order_and_labels(self):
        source = (ROOT / "app" / "controller.py").read_text(encoding="utf-8")
        self.assertLess(source.index("main.add(left"), source.index("main.add(tools_host"))
        self.assertLess(source.index("main.add(tools_host"), source.index("main.add(preview_box"))   # preview far right
        self.assertIn('self.progress.grid(row=0, column=0', source)                                 # progress bar on top
        self.assertIn('source_bar.grid(row=2, column=0', source)
        self.assertIn('main.grid(row=3, column=0, sticky="nsew")', source)                          # panes get their own row
        self.assertIn('outer.rowconfigure(3, weight=1)', source)                                    # ... and it is the stretchy one
        self.assertIn('ttk.Button(btns, text="Output Video"', source)
        self.assertNotIn('text="Open Job Folder"', source)
        self.assertIn('self.header_note.configure(text=f"{name} → Myanmar")', source)

    def test_the_preview_gets_four_corner_brackets(self):
        c = self.c
        c.load_config = lambda: {}
        app = c.App.__new__(c.App)
        c.App.__init__(app)
        canvas = Canvas()
        app.preview_canvas = canvas
        app._redraw_editor_items()
        hud = [kw for _coords, kw in canvas.lines if "hud" in kw.get("tags", ())]
        self.assertEqual(len(hud), 4)
        self.assertTrue(all(kw["fill"] == c.ACCENT for kw in hud))
        coords = [coords for coords, kw in canvas.lines if "hud" in kw.get("tags", ())]
        self.assertTrue(all(len(cs) == 6 for cs in coords))                          # each bracket is an L: three points
        self.assertIn("editor", canvas.deleted)                                      # redrawn from scratch every time


if __name__ == "__main__":
    unittest.main()
