from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from version import APP_HEADER, APP_TITLE
import video_fx as fx
import subtitles as subs
import layout_math as lm
import languages
import voice_gender as vg
import audio_mix as amix
from core import (FRAME_FILLS, FREEZE_HOLD_CHOICES, FREEZE_PLAY_CHOICES, FREEZE_ZOOM_LEVELS, OUTPUT_RATIOS,
                  TTS_PROVIDERS, normalize_freeze_rhythm, normalize_segments, output_canvas, parse_tts_provider,
                  probe_video_size)
from preview_tools import probe_duration as preview_probe_duration, extract_preview_frame, scale_logo_preview
from narration_editor import NarrationEditor, failed_segment_from_error

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config.json"
JOBS_DIR = ROOT_DIR / "jobs"
LOGS_DIR = ROOT_DIR / "logs"
ICON_DIR = ROOT_DIR / "app" / "assets"          # icon.ico / icon.png, drawn by app/make_icon.py
JOBS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
EVENT_PREFIX = "@@VRS_EVENT@@"

# Minimalist futuristic HUD: near-black navy, hairline cyan-navy borders, one cyan accent, monospace for headings / values.
BG = "#05080d"
PANEL = "#0a121c"
FIELD = "#060b12"
BORDER = "#173a52"
FG = "#d8e8f4"
MUTED = "#7f9bb3"
ACCENT = "#00e5ff"
ACCENT_HOVER = "#62efff"
ACCENT_DIM = "#0b3a47"
ON_ACCENT = "#021016"            # text on a cyan button
DANGER = "#ff5d7a"
WARN = "#ffb454"
SUCCESS = "#2bff9a"
HUD_FONT = "Consolas"
BODY_FONT = "Segoe UI"
# One colour per menu title; every colour must stay readable on BG / PANEL / FIELD (tests/test_hud_theme.py checks it).
SECTION_COLORS = {"language": "#00e5ff", "voice": "#2bff9a", "video": "#ffb454", "blur": "#ff7ad9", "title": "#b794ff",
                  "logo": "#6cb8ff", "extra": "#ff8a5c", "look": "#ffe066", "subtitle": "#c3f26b"}
SECTION_STYLE = {key: f"Sec{key.capitalize()}.TLabel" for key in SECTION_COLORS}
SECTION_FONT_SIZE = 12                 # menu titles are a little bigger than the 10 pt body text
MYANMAR_FONT = "Myanmar Text"          # the Burmese descriptions under the menus
PREVIEW_W = 640
PREVIEW_H = 360

EDGE_VOICES = ("my-MM-ThihaNeural", "my-MM-NilarNeural")
# Source language of the video; the output is always Burmese. Chinese jobs get their own job folder.
SOURCE_LANGS = languages.dropdown_labels()       # "English → Myanmar": "en", "Japanese 日本語 → Myanmar": "ja", ...
SOURCE_LANG_LABELS = {code: label for label, code in SOURCE_LANGS.items()}
SOURCE_LANG_NAMES = {code: info["name"] for code, info in languages.LANGS.items()}
ASR_CHECK_SECONDS = 60


class TranscriptPreview(Exception):
    """The quick transcript check finished: show the text, do not render anything."""
FILL_LABELS = {"blur": "Blur background", "black": "Black bars", "crop": "Crop to fill"}


def _tool_path(cfg: dict, name: str) -> str:
    """ffmpeg / ffprobe: config.json path, the tool's own ffmpeg folder, PATH, then C:\\ffmpeg\\bin."""
    for candidate in (str(cfg.get(f"{name}_path") or ""), str(ROOT_DIR / "ffmpeg" / f"{name}.exe"),
                      str(ROOT_DIR / "ffmpeg" / "bin" / f"{name}.exe"), shutil.which(name) or "",
                      rf"C:\ffmpeg\bin\{name}.exe"):
        if candidate and Path(candidate).is_file():
            return candidate
    return name


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_edge_rate_percent(value: object) -> int:
    text = str(value or "+0%").strip()
    match = re.fullmatch(r"([+-]?\d{1,3})%", text)
    percent = int(match.group(1)) if match else 0
    return max(-50, min(percent, 100))


def _format_edge_rate(percent: object) -> str:
    value = max(-50, min(int(round(float(percent))), 100))
    return f"{value:+d}%"


def _safe_name(text: str) -> str:
    text = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return text[:80] or "recap_test"


def _job_dir_for(source: Path, lang: str = "en") -> Path:
    raw = str(source.resolve()).encode("utf-8")
    sig = hashlib.sha1(raw).hexdigest()[:8]
    suffix = "" if lang == "en" else f"_{lang}"      # English job folders keep their old names
    return JOBS_DIR / f"{_safe_name(source.stem)}_{sig}{suffix}"


BATCH_VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi"}


def _natural_key(path: Path) -> list:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", path.name)]


def _list_batch_videos(folder: Path) -> list[Path]:
    """Videos directly inside folder (not subfolders), in natural filename order."""
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in BATCH_VIDEO_EXTS),
        key=_natural_key,
    )


def _job_final_output(job_dir: Path) -> Path | None:
    final = job_dir / "edge_tts_smart_sync" / "final_edge_tts_smart_sync.mp4"
    return final if final.is_file() and final.stat().st_size > 10000 else None


def _native_crash_message(code: int) -> str:
    unsigned = code & 0xFFFFFFFF
    if code == -1073740791 or unsigned == 0xC0000409:
        return (
            "Child process native crash (0xC0000409).\n\n"
            "ဒီ native crash ထပ်ပေါ်ရင် jobs/<job>/run.log ကိုစစ်ပါ။"
        )
    return f"Child process closed with exit code {code}. run.log ကိုစစ်ပါ။"


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} — English / Chinese → Myanmar")
        self._set_app_icon()
        self.geometry("1580x900")
        self.minsize(1100, 660)
        try:
            self.state("zoomed")  # start maximised so all three panes get real space
        except tk.TclError:
            pass
        self.configure(bg=BG)
        self.cfg = load_config()
        self.msgq: queue.Queue[tuple[str, object]] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.current_proc: subprocess.Popen | None = None
        self.current_job: Path | None = None
        self.run_log_path: Path | None = None
        self.proc_lock = threading.Lock()

        self.gemini_env = tk.StringVar(value=self.cfg.get("gemini_env_path") or str(ROOT_DIR / ".env"))
        saved_lang = str(self.cfg.get("source_language") or "en")
        self.source_lang = tk.StringVar(value=SOURCE_LANG_LABELS.get(saved_lang, SOURCE_LANG_LABELS["en"]))
        self.asr_check = tk.BooleanVar(value=False)
        self.refine_pass = tk.BooleanVar(value=bool(self.cfg.get("refine_pass", False)))
        self.source = tk.StringVar(value="")
        self.source_title = tk.StringVar(value="")
        saved_voice = str(self.cfg.get("edge_tts_voice_mm") or self.cfg.get("edge_tts_voice") or EDGE_VOICES[0])
        self.edge_voice = tk.StringVar(value=saved_voice if saved_voice in EDGE_VOICES else EDGE_VOICES[0])
        self.tts_provider = tk.StringVar(value=TTS_PROVIDERS[parse_tts_provider(self.cfg.get("tts_provider"))])
        self.edge_rate_percent = tk.DoubleVar(value=float(_parse_edge_rate_percent(self.cfg.get("edge_tts_rate", "+0%"))))
        self.max_speed = tk.StringVar(value=str(self.cfg.get("max_video_speed", 1.25)))
        self.max_slow = tk.StringVar(value=str(self.cfg.get("max_video_slow", 1.35)))
        self.mirror_video = tk.BooleanVar(value=bool(self.cfg.get("mirror_video", True)))
        self.voice_volume = tk.IntVar(value=int(self.cfg.get("voice_volume_percent", 100) or 100))
        self.short_pauses = tk.BooleanVar(value=bool(self.cfg.get("short_pauses", True)))
        self.zoom_factor = tk.DoubleVar(value=float(self.cfg.get("zoom_factor", 1.05)))
        self.voice_mode = tk.StringVar(value=vg.VOICE_MODE_LABELS[vg.normalize_voice_mode(self.cfg.get("voice_mode"))])
        mix = amix.normalize_audio_mix(self.cfg.get("audio_mix"))
        self.orig_percent = tk.DoubleVar(value=mix["original_percent"])
        self.orig_duck = tk.BooleanVar(value=mix["duck"])
        sub = subs.normalize_subtitles(self.cfg.get("subtitles"))
        self.sub_enabled = tk.BooleanVar(value=sub["enabled"])
        self.sub_size = tk.StringVar(value=self._sub_size_label(sub["size"]))
        self.sub_style = tk.StringVar(value=subs.SUB_STYLE_LABELS[sub["style"]])
        self.sub_pos = list(sub["position"])                       # bottom centre of the subtitle, fractions of the picture
        self.sub_x_var = tk.DoubleVar(value=lm.pos_to_slider(self.sub_pos)[0])
        self.sub_y_var = tk.DoubleVar(value=lm.pos_to_slider(self.sub_pos)[1])
        self._sub_grab = (0.0, 0.0)              # where inside the subtitle it was grabbed (pixels from its bottom centre)
        self._sub_snap = False
        self._syncing_sub = False
        look = fx.normalize_look(self.cfg.get("video_look"))
        self.look_preset = tk.StringVar(value=look["preset"])
        self.look_strength = tk.DoubleVar(value=look["strength"])
        self.look_vignette = tk.DoubleVar(value=look["vignette"])
        slow = fx.normalize_slow_motion(self.cfg.get("slow_motion"))
        self.slow_enabled = tk.BooleanVar(value=slow["enabled"])
        self.slow_len = tk.StringVar(value=f"{slow['slow_seconds']} s")
        self.slow_speed = tk.StringVar(value=f"{slow['speed']:g}×")
        self.slow_gap = tk.StringVar(value=f"{slow['gap_seconds']} s")
        auto = fx.normalize_auto_edit(self.cfg.get("auto_edit"))
        self.auto_enabled = tk.BooleanVar(value=auto["enabled"])
        self.auto_effect_vars = {name: tk.BooleanVar(value=name in auto["effects"]) for name in fx.AUTO_EFFECTS}
        self.auto_intensity = tk.StringVar(value=auto["intensity"])
        self.auto_seed = tk.StringVar(value="" if auto["seed"] is None else str(auto["seed"]))
        rhythm = normalize_freeze_rhythm(self.cfg.get("freeze_rhythm"))
        self.freeze_enabled = tk.BooleanVar(value=rhythm["enabled"])
        self.freeze_play = tk.StringVar(value=f"{rhythm['play_seconds']} s")
        self.freeze_hold = tk.StringVar(value=f"{rhythm['hold_seconds']} s")
        self.freeze_zoom = tk.StringVar(value=rhythm["zoom_level"])
        saved_ratio = str(self.cfg.get("output_ratio") or "16:9")
        self.output_ratio = tk.StringVar(value=saved_ratio if saved_ratio in OUTPUT_RATIOS else "16:9")
        self.frame_fill = tk.StringVar(value=FILL_LABELS.get(str(self.cfg.get("frame_fill") or "blur"), FILL_LABELS["blur"]))
        self.source_size = (0, 0)
        self.smooth_freeze = tk.BooleanVar(value=bool(self.cfg.get("smooth_freeze_fallback", False)))
        self.max_freeze_hold = tk.StringVar(value=str(self.cfg.get("max_freeze_hold", 0.75)))
        self.render_final = tk.BooleanVar(value=bool(self.cfg.get("render_final_video", True)))
        self.reuse_plan = tk.BooleanVar(value=bool(self.cfg.get("reuse_transcript_and_plan", self.cfg.get("reuse_whisper_and_plan", True))))
        self.status = tk.StringVar(value="READY")
        self.stage = tk.StringVar(value="Idle")
        self.job_display = tk.StringVar(value="Job output: not selected")
        # Folder batch: when non-empty, START processes these files one by one.
        self.batch_files: list[Path] = []
        self.batch_folder: Path | None = None

        # Minimal production editor state. V0.3 sync/mirror/freeze behavior remains hidden/fixed.
        self.title_text = tk.StringVar(value="")
        self.title_size = tk.IntVar(value=int(self.cfg.get("title_font_size", 54)))
        self.logo_path = tk.StringVar(value=str(self.cfg.get("logo_path", "")))
        self.logo_enabled = tk.BooleanVar(value=bool(self.cfg.get("logo_enabled", False)))
        self.logo_width_frac = tk.DoubleVar(value=float(self.cfg.get("logo_width_fraction", 0.16)))
        self.logo_opacity = tk.DoubleVar(value=float(self.cfg.get("logo_opacity", 0.65)))
        self.extra_text = tk.StringVar(value="")
        self.extra_text_size = tk.IntVar(value=int(self.cfg.get("extra_text_font_size", 42)))
        self.extra_text_opacity = tk.DoubleVar(value=float(self.cfg.get("extra_text_opacity", 0.65)))
        self.preview_time = tk.DoubleVar(value=float(self.cfg.get("preview_seek_seconds", 1.0)))
        self.preview_duration = 0.0
        self.blur_boxes: list[dict[str, float]] = []
        self.selected_blur: int | None = None
        self.title_pos = list(self.cfg.get("title_position", [0.50, 0.12]))
        self.logo_pos = list(self.cfg.get("logo_position", [0.80, 0.06]))
        self.extra_text_pos = lm.normalize_pos(self.cfg.get("extra_text_position"))
        self.extra_x_var = tk.DoubleVar(value=lm.pos_to_slider(self.extra_text_pos)[0])
        self.extra_y_var = tk.DoubleVar(value=lm.pos_to_slider(self.extra_text_pos)[1])
        self._extra_half = (0.0, 0.0)            # half the size of the box on the preview, as fractions of the picture
        self._extra_grab = (0.0, 0.0)            # where inside the box it was grabbed (pixels from its centre)
        self._extra_snap = (False, False)
        self._syncing_extra = False
        self._preview_photo = None
        self._logo_photo = None
        self._draw_blur_mode = False
        self._draw_start: tuple[float, float] | None = None
        self._temp_rect = None
        self._drag_kind: str | None = None
        self._drag_index: int | None = None
        self._drag_start: tuple[float, float] | None = None
        self._drag_original = None

        self._apply_dark_theme()
        self._build()
        self.after(150, self._pump)

    def _apply_dark_theme(self) -> None:
        """HUD dashboard look: flat dark panels, hairline borders, cyan accent, monospace headings."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        mono = (HUD_FONT, 9)
        style.configure(".", background=BG, foreground=FG, font=(BODY_FONT, 10), bordercolor=BORDER, focuscolor=BG)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(BODY_FONT, 9))
        style.configure("Hint.TLabel", background=BG, foreground=MUTED, font=(MYANMAR_FONT, 10))     # Burmese descriptions
        style.configure("Hud.TLabel", background=BG, foreground=ACCENT, font=(HUD_FONT, 10, "bold"))
        for key, color in SECTION_COLORS.items():
            style.configure(SECTION_STYLE[key], background=BG, foreground=color, font=(HUD_FONT, SECTION_FONT_SIZE, "bold"))
        style.configure("Value.TLabel", background=BG, foreground=ACCENT, font=mono)
        style.configure("Status.TLabel", background=BG, foreground=SUCCESS, font=(HUD_FONT, 10, "bold"))
        style.configure("TLabelframe", background=BG, foreground=FG, bordercolor=BORDER, relief="solid")
        style.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=(HUD_FONT, 10, "bold"))
        style.configure("TSeparator", background=BORDER)
        style.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=ACCENT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, padding=(4, 3))
        style.map("TEntry", fieldbackground=[("disabled", PANEL)], foreground=[("disabled", MUTED)],
                  bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])
        style.configure("TCombobox", fieldbackground=FIELD, foreground=FG, background=PANEL, arrowcolor=ACCENT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, padding=(4, 3))
        style.map("TCombobox", fieldbackground=[("readonly", FIELD), ("disabled", PANEL)], foreground=[("readonly", FG), ("disabled", MUTED)],
                  selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)],
                  bordercolor=[("focus", ACCENT)], arrowcolor=[("disabled", MUTED)])
        # outlined buttons: the accent shows on hover; the primary button is solid cyan
        style.configure("TButton", background=PANEL, foreground=ACCENT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        padding=(10, 6), relief="flat", font=(HUD_FONT, 9, "bold"))
        style.map("TButton", background=[("active", ACCENT_DIM), ("disabled", PANEL)], foreground=[("disabled", "#4b6479")],
                  bordercolor=[("active", ACCENT), ("disabled", BORDER)])
        style.configure("Compact.TButton", background=PANEL, foreground=ACCENT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        padding=(6, 2), relief="flat", font=(HUD_FONT, 9))
        style.map("Compact.TButton", background=[("active", ACCENT_DIM), ("disabled", PANEL)], foreground=[("disabled", "#4b6479")],
                  bordercolor=[("active", ACCENT)])
        style.configure("Accent.TButton", background=ACCENT, foreground=ON_ACCENT, bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                        padding=(12, 7), relief="flat", font=(HUD_FONT, 10, "bold"))
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#0f3340")], foreground=[("disabled", "#5d8296")])
        style.configure("Danger.TButton", background="#16080d", foreground=DANGER, bordercolor="#5a1a2a", lightcolor="#5a1a2a",
                        darkcolor="#5a1a2a", padding=(10, 6), relief="flat", font=(HUD_FONT, 9, "bold"))
        style.map("Danger.TButton", background=[("active", "#3a121c")], bordercolor=[("active", DANGER)])
        style.configure("TCheckbutton", background=BG, foreground=FG, indicatorcolor=FIELD, indicatorbackground=FIELD)
        style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", ACCENT)],
                  indicatorcolor=[("selected", ACCENT)], indicatorbackground=[("selected", ACCENT)])
        style.configure("Horizontal.TScale", background=PANEL, troughcolor="#0d2433", bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)
        style.map("Horizontal.TScale", background=[("active", ACCENT_HOVER)])
        style.configure("Horizontal.TProgressbar", troughcolor=FIELD, background=ACCENT, bordercolor=BORDER, lightcolor=ACCENT,
                        darkcolor=ACCENT, thickness=6)
        style.configure("TNotebook", background=BG, bordercolor=BORDER)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(10, 4), font=(HUD_FONT, 9))
        style.map("TNotebook.Tab", background=[("selected", ACCENT_DIM)], foreground=[("selected", ACCENT)])
        style.configure("Vertical.TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BG, arrowcolor=ACCENT)
        self.option_add("*TCombobox*Listbox.background", FIELD)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)

    def _build(self) -> None:
        # Layout V34: progress bar, one-line header, compact source bar, then three resizable panes
        # (Settings+Logs | Tools | Preview). The preview sits at the far right, follows its pane size and always
        # shows the whole 16:9 frame; the long settings list scrolls inside its own pane.
        outer = ttk.Frame(self, padding=(12, 8, 12, 8))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        # progress bar on top (rows: 0 progress, 1 header, 2 source bar, 3 panes, 4 buttons)
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        header = tk.Frame(outer, bg=BG)
        header.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        tk.Frame(header, bg=ACCENT, height=1).pack(side="bottom", fill="x", pady=(6, 0))        # the HUD hairline
        tk.Label(header, text="◢", bg=BG, fg=ACCENT, font=(HUD_FONT, 15, "bold")).pack(side="left", padx=(0, 6))
        tk.Label(header, text=APP_HEADER, bg=BG, fg=ACCENT, font=(HUD_FONT, 15, "bold")).pack(side="left")
        self.header_note = tk.Label(header, bg=BG, fg=MUTED, font=(HUD_FONT, 9))
        self.header_note.pack(side="left", padx=(14, 0), pady=(5, 0))
        self._language_changed(initial=True)

        source_bar = ttk.Frame(outer)
        source_bar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        source_bar.columnconfigure(1, weight=3)
        source_bar.columnconfigure(4, weight=1)
        ttk.Label(source_bar, text="Source Video").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.source_entry = ttk.Entry(source_bar, textvariable=self.source)
        self.source_entry.grid(row=0, column=1, sticky="ew")
        self.source_entry.bind("<KeyRelease>", lambda _event: self._clear_batch())
        source_buttons = ttk.Frame(source_bar)
        source_buttons.grid(row=0, column=2, padx=(6, 18), sticky="w")
        ttk.Button(source_buttons, text="Browse", style="Compact.TButton", command=self._browse_source).pack(side="left")
        ttk.Button(source_buttons, text="Folder", style="Compact.TButton", command=self._browse_folder).pack(side="left", padx=(6, 0))
        ttk.Label(source_bar, text="API keys .env").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Entry(source_bar, textvariable=self.gemini_env).grid(row=0, column=4, sticky="ew")
        ttk.Button(source_bar, text="Browse", style="Compact.TButton", command=self._browse_env).grid(row=0, column=5, padx=(6, 0))

        main = ttk.PanedWindow(outer, orient="horizontal")
        main.grid(row=3, column=0, sticky="nsew")

        # ---------------- left: scrollable settings (top) + Run Logs (bottom)
        left = ttk.PanedWindow(main, orient="vertical")
        settings_host = ttk.LabelFrame(left, text="Translation / Voice Settings", padding=3)
        settings_host.rowconfigure(0, weight=1)
        settings_host.columnconfigure(0, weight=1)
        settings_canvas = tk.Canvas(settings_host, bg=BG, highlightthickness=0, height=340)
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scroll = ttk.Scrollbar(settings_host, orient="vertical", command=settings_canvas.yview)
        settings_scroll.grid(row=0, column=1, sticky="ns")
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        source_box = ttk.Frame(settings_canvas, padding=(6, 4, 8, 4))
        settings_window = settings_canvas.create_window((0, 0), window=source_box, anchor="nw")
        source_box.bind("<Configure>", lambda _e: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")))
        settings_canvas.bind("<Configure>", lambda e: settings_canvas.itemconfigure(settings_window, width=e.width))
        self._bind_wheel(settings_canvas, settings_canvas)
        source_box.columnconfigure(1, weight=1)
        hint_wrap = 220

        def hint(row: int, text: str) -> ttk.Label:
            label = ttk.Label(source_box, text=text, style="Hint.TLabel", wraplength=hint_wrap, justify="left")
            label.grid(row=row, column=2, sticky="w", padx=(8, 0))
            return label

        def settings_title(row: int, text: str, key: str, pady=(0, 4)) -> None:
            ttk.Label(source_box, text=f"▌ {text.upper()}", style=SECTION_STYLE[key]).grid(
                row=row, column=0, columnspan=3, sticky="w", pady=pady)

        settings_title(0, "Language & Transcript", "language")
        ttk.Label(source_box, text="Source language").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        self.source_lang_combo = ttk.Combobox(source_box, textvariable=self.source_lang, state="readonly",
                                              values=tuple(SOURCE_LANGS))
        self.source_lang_combo.grid(row=1, column=1, sticky="ew", pady=3)
        self.source_lang_combo.bind("<<ComboboxSelected>>", lambda _e: self._language_changed())
        self.source_lang_hint = hint(1, "")

        self.asr_check_box = ttk.Checkbutton(source_box, text=f"Check transcript first (first {ASR_CHECK_SECONDS} s only)",
                                             variable=self.asr_check)
        self.asr_check_box.grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
        self.asr_check_hint = hint(3, "Whisper စာသားကိုပဲ စစ်မယ် — AI မသုံးပါ၊ video မထုတ်ပါ")

        self.refine_box = ttk.Checkbutton(source_box, text="AI refine pass (polish the Burmese)", variable=self.refine_pass)
        self.refine_box.grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        self.refine_hint = hint(4, "AI ကို ဒုတိယအကြိမ် ထပ်သုံးပြီး စကားလုံးတွေကို သဘာဝကျအောင် ပြင်မယ် (အဓိပ္ပါယ် မပြောင်းပါ)။ AI call ပိုသုံးပါမယ်")
        self._language_changed(initial=True)      # hints + enabled state for the saved language

        settings_title(9, "Voice (TTS)", "voice", pady=(12, 4))
        ttk.Label(source_box, text="TTS provider").grid(row=10, column=0, sticky="w", padx=(0, 8), pady=3)
        self.tts_provider_combo = ttk.Combobox(source_box, textvariable=self.tts_provider, state="readonly",
                                               values=tuple(TTS_PROVIDERS.values()))
        self.tts_provider_combo.grid(row=10, column=1, sticky="ew", pady=3)
        self.tts_provider_combo.bind("<<ComboboxSelected>>", lambda _e: self._tts_provider_changed())
        self.tts_provider_hint = hint(10, "")

        self.edge_voice_label = ttk.Label(source_box, text="Edge TTS Voice")
        self.edge_voice_label.grid(row=11, column=0, sticky="w", padx=(0, 8), pady=3)
        self.edge_voice_combo = ttk.Combobox(source_box, textvariable=self.edge_voice, state="readonly", values=EDGE_VOICES)
        self.edge_voice_combo.grid(row=11, column=1, sticky="ew", pady=3)
        self.edge_voice_hint = hint(11, "စက်ထဲက Edge TTS အသံ")

        self.edge_speed_label = ttk.Label(source_box, text="Edge TTS Speed")
        self.edge_speed_label.grid(row=12, column=0, sticky="w", padx=(0, 8), pady=3)
        self.edge_speed_frame = ttk.Frame(source_box)
        self.edge_speed_frame.grid(row=12, column=1, sticky="ew", pady=3)
        self.edge_speed_frame.columnconfigure(0, weight=1)
        self.edge_speed_slider = ttk.Scale(
            self.edge_speed_frame, from_=-50, to=100, orient="horizontal",
            variable=self.edge_rate_percent, command=self._edge_rate_changed,
        )
        self.edge_speed_slider.grid(row=0, column=0, sticky="ew")
        self.edge_speed_value = ttk.Label(self.edge_speed_frame, text=_format_edge_rate(self.edge_rate_percent.get()), width=7)
        self.edge_speed_value.grid(row=0, column=1, padx=(8, 0))
        self.edge_speed_hint = hint(12, "-50% ပိုနှေး · 0% ပုံမှန် · +100% ပိုမြန်")

        # who speaks each line: the selected voice, always male / female, or by the original speaker's pitch
        ttk.Label(source_box, text="Voice mode").grid(row=13, column=0, sticky="w", padx=(0, 8), pady=3)
        self.voice_mode_combo = ttk.Combobox(source_box, textvariable=self.voice_mode, state="readonly", values=tuple(vg.VOICE_MODES))
        self.voice_mode_combo.grid(row=13, column=1, sticky="ew", pady=3)
        self.voice_mode_hint = hint(13, "Auto: ယောက်ျားအသံဆို Thiha၊ မိန်းမအသံဆို Nilar (မူရင်းအသံရဲ့ pitch အရ ရွေးပေးမယ်)")

        # the original sound under the dub
        ttk.Label(source_box, text="Original audio").grid(row=14, column=0, sticky="w", padx=(0, 8), pady=3)
        orig_frame = ttk.Frame(source_box)
        orig_frame.grid(row=14, column=1, sticky="ew", pady=3)
        orig_frame.columnconfigure(0, weight=1)
        ttk.Scale(orig_frame, from_=0, to=100, orient="horizontal", variable=self.orig_percent,
                  command=lambda _v: self.orig_value.configure(text=f"{int(float(self.orig_percent.get()))}%")
                  ).grid(row=0, column=0, sticky="ew")
        self.orig_value = ttk.Label(orig_frame, text=f"{int(float(self.orig_percent.get()))}%", width=5, anchor="e")
        self.orig_value.grid(row=0, column=1, padx=(8, 0))
        self.orig_hint = hint(14, "0% = dub အသံသက်သက် · ပိုများရင် မူရင်းအသံကို dub အောက်မှာ ဆက်ကြားရမယ်")
        ttk.Checkbutton(source_box, text="Duck the original while the dub speaks", variable=self.orig_duck
                        ).grid(row=15, column=0, columnspan=2, sticky="w", pady=(0, 3))
        self._tts_provider_changed()

        self._bind_wheel_recursive(source_box, settings_canvas)
        self._settings_canvas = settings_canvas

        log_panel = ttk.LabelFrame(left, text="Run Logs", padding=5)
        log_panel.rowconfigure(0, weight=1)
        log_panel.columnconfigure(0, weight=1)
        self.log_notebook = ttk.Notebook(log_panel)
        self.log_notebook.grid(row=0, column=0, sticky="nsew")
        self.logbox = self._create_log_tab("Main Log")
        left.add(settings_host, weight=3)
        left.add(log_panel, weight=2)

        # ---------------- center: preview that fills its pane
        preview_box = ttk.LabelFrame(main, text="Preview — drag Title / Logo, draw Blur box", padding=7)
        preview_box.columnconfigure(0, weight=1)
        preview_box.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(preview_box, width=PREVIEW_W, height=PREVIEW_H, bg="#03060a", highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, cursor="crosshair")
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<ButtonPress-1>", self._preview_press)
        self.preview_canvas.bind("<B1-Motion>", self._preview_motion)
        self.preview_canvas.bind("<ButtonRelease-1>", self._preview_release)
        self.preview_canvas.bind("<Configure>", self._preview_resized)
        self._preview_resize_job = None
        self._preview_canvas_size = (PREVIEW_W, PREVIEW_H)

        seek_row = ttk.Frame(preview_box)
        seek_row.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        seek_row.columnconfigure(1, weight=1)
        ttk.Button(seek_row, text="◀ 5s", width=5, style="Compact.TButton", command=lambda: self._seek_preview(-5)).grid(row=0, column=0, padx=(0, 6))
        self.preview_slider = ttk.Scale(seek_row, from_=0.0, to=1.0, orient="horizontal", variable=self.preview_time,
                                        command=lambda _v: self._update_preview_time_label())
        self.preview_slider.grid(row=0, column=1, sticky="ew")
        self.preview_slider.bind("<ButtonRelease-1>", lambda _e: self._refresh_preview())
        ttk.Button(seek_row, text="5s ▶", width=5, style="Compact.TButton", command=lambda: self._seek_preview(5)).grid(row=0, column=2, padx=(6, 8))
        self.preview_time_label = ttk.Label(seek_row, text="00:00 / 00:00", style="Muted.TLabel", width=15)
        self.preview_time_label.grid(row=0, column=3)
        ttk.Button(seek_row, text="Refresh Frame", command=self._refresh_preview).grid(row=0, column=4, padx=(6, 0))

        # ---------------- right: scrollable production tools
        tools_host = ttk.LabelFrame(main, text="Production Tools", padding=3)
        tools_host.rowconfigure(0, weight=1)
        tools_host.columnconfigure(0, weight=1)
        tools_canvas = tk.Canvas(tools_host, bg=BG, highlightthickness=0, width=320)
        tools_canvas.grid(row=0, column=0, sticky="nsew")
        tools_scroll = ttk.Scrollbar(tools_host, orient="vertical", command=tools_canvas.yview)
        tools_scroll.grid(row=0, column=1, sticky="ns")
        tools_canvas.configure(yscrollcommand=tools_scroll.set)
        tools = ttk.Frame(tools_canvas, padding=(8, 6, 10, 6))
        tools_window = tools_canvas.create_window((0, 0), window=tools, anchor="nw")
        tools.bind("<Configure>", lambda _e: tools_canvas.configure(scrollregion=tools_canvas.bbox("all")))
        tools_canvas.bind("<Configure>", lambda e: tools_canvas.itemconfigure(tools_window, width=e.width))
        self._bind_wheel(tools_canvas, tools_canvas)
        tools.columnconfigure(0, weight=1)

        def section(row: int, text: str, key: str) -> None:
            if row:
                ttk.Separator(tools).grid(row=row - 1, column=0, sticky="ew", pady=(2, 10))
            ttk.Label(tools, text=f"▌ {text.upper()}", style=SECTION_STYLE[key]).grid(row=row, column=0, sticky="w")

        def slider_row(row: int, label: str, from_: float, to: float, variable, on_change, value_label_attr: str,
                       text: str, pady=(3, 10)) -> ttk.Scale:
            frame = ttk.Frame(tools)
            frame.grid(row=row, column=0, sticky="ew", pady=pady)
            frame.columnconfigure(1, weight=1)
            ttk.Label(frame, text=label, width=9).grid(row=0, column=0, sticky="w")
            scale = ttk.Scale(frame, from_=from_, to=to, orient="horizontal", variable=variable, command=on_change)
            scale.grid(row=0, column=1, sticky="ew")
            value = ttk.Label(frame, text=text, width=6, anchor="e")
            value.grid(row=0, column=2, padx=(8, 0))
            setattr(self, value_label_attr, value)
            return scale

        section(0, "Video", "video")
        self.zoom_slider = slider_row(1, "Zoom", 1.00, 1.25, self.zoom_factor, self._zoom_changed,
                                      "zoom_value_label", f"{float(self.zoom_factor.get()):.2f}x")
        self.zoom_slider.bind("<ButtonRelease-1>", lambda _e: self._refresh_preview())
        ttk.Checkbutton(self.zoom_slider.master, text="Flip (mirror left ↔ right)", variable=self.mirror_video,
                        command=self._mirror_changed).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._voice_volume_scale_var = tk.DoubleVar(value=float(self.voice_volume.get()))
        volume_frame = ttk.Frame(self.zoom_slider.master)
        volume_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        volume_frame.columnconfigure(1, weight=1)
        ttk.Label(volume_frame, text="Voice vol", width=9).grid(row=0, column=0, sticky="w")
        ttk.Scale(volume_frame, from_=50, to=300, orient="horizontal", variable=self._voice_volume_scale_var,
                  command=self._voice_volume_changed).grid(row=0, column=1, sticky="ew")
        self.voice_volume_label = ttk.Label(volume_frame, text="", width=13, anchor="e")
        self.voice_volume_label.grid(row=0, column=2, padx=(8, 0))
        self._voice_volume_changed(self.voice_volume.get())
        ttk.Checkbutton(self.zoom_slider.master, text="Short pauses (~0.25 s between lines)",
                        variable=self.short_pauses).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        frame_row = ttk.Frame(self.zoom_slider.master)
        frame_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        frame_row.columnconfigure(3, weight=1)
        ttk.Label(frame_row, text="Ratio", width=9).grid(row=0, column=0, sticky="w")
        ratio_combo = ttk.Combobox(frame_row, textvariable=self.output_ratio, values=OUTPUT_RATIOS, state="readonly", width=9)
        ratio_combo.grid(row=0, column=1, sticky="w")
        ttk.Label(frame_row, text="Fill").grid(row=0, column=2, sticky="e", padx=(10, 6))
        fill_combo = ttk.Combobox(frame_row, textvariable=self.frame_fill, values=tuple(FILL_LABELS.values()),
                                  state="readonly", width=15)
        fill_combo.grid(row=0, column=3, sticky="ew")
        for combo in (ratio_combo, fill_combo):
            combo.bind("<<ComboboxSelected>>", lambda _e: self._frame_changed())
        # Freeze rhythm: play N s, hold one frame M s while it zooms in, repeat (picture only, narration untouched).
        ttk.Checkbutton(self.zoom_slider.master, text="Freeze rhythm  (play → freeze frame → zoom-in)",
                        variable=self.freeze_enabled).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        rhythm_row = ttk.Frame(self.zoom_slider.master)
        rhythm_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        ttk.Label(rhythm_row, text="Play", width=9).grid(row=0, column=0, sticky="w")
        ttk.Combobox(rhythm_row, textvariable=self.freeze_play, values=tuple(f"{n} s" for n in FREEZE_PLAY_CHOICES),
                     state="readonly", width=6).grid(row=0, column=1, sticky="w")
        ttk.Label(rhythm_row, text="Freeze").grid(row=0, column=2, sticky="e", padx=(10, 6))
        ttk.Combobox(rhythm_row, textvariable=self.freeze_hold, values=tuple(f"{n} s" for n in FREEZE_HOLD_CHOICES),
                     state="readonly", width=6).grid(row=0, column=3, sticky="w")
        ttk.Label(rhythm_row, text="Zoom-in").grid(row=0, column=4, sticky="e", padx=(10, 6))
        ttk.Combobox(rhythm_row, textvariable=self.freeze_zoom, values=tuple(FREEZE_ZOOM_LEVELS),
                     state="readonly", width=8).grid(row=0, column=5, sticky="w")
        ttk.Label(self.zoom_slider.master, text="Freeze တစ်ခုချင်းစီက ကျပန်းနေရာတစ်ခုဆီကို ကျပန်းပမာဏနဲ့ zoom-in ဝင်သွားမယ်။",
                  style="Hint.TLabel", wraplength=300, justify="left").grid(row=7, column=0, columnspan=3, sticky="w", pady=(2, 0))

        section(3, "Blur Watermark Area", "blur")
        blur_row = ttk.Frame(tools)
        blur_row.grid(row=4, column=0, sticky="ew", pady=(5, 10))
        ttk.Button(blur_row, text="+ Draw Blur Box", style="Compact.TButton", command=self._begin_blur_box).pack(side="left")
        ttk.Button(blur_row, text="Delete Selected", style="Compact.TButton", command=self._delete_selected_blur).pack(side="left", padx=6)
        self.blur_count_label = ttk.Label(blur_row, text="0 box", style="Muted.TLabel")
        self.blur_count_label.pack(side="left", padx=(4, 0))

        section(6, "Title", "title")
        self.title_entry = ttk.Entry(tools, textvariable=self.title_text, font=("Myanmar Text", 10))
        self.title_entry.grid(row=7, column=0, sticky="ew", pady=(5, 4))
        self.title_entry.bind("<KeyRelease>", lambda _e: self._redraw_editor_items())
        self._title_size_scale_var = tk.DoubleVar(value=float(self.title_size.get()))
        title_scale = slider_row(8, "Size", 24, 96, self._title_size_scale_var,
                                 lambda v: self._int_slider_changed(v, self.title_size, "title_size_label"),
                                 "title_size_label", str(int(self.title_size.get())), pady=(0, 2))
        title_scale.bind("<ButtonRelease-1>", lambda _e: self._redraw_editor_items())
        ttk.Label(tools, text="Preview ပေါ်မှာ Title ကို ဆွဲရွှေ့ပြီး နေရာချနိုင်တယ်", style="Hint.TLabel", wraplength=300,
                  justify="left").grid(row=9, column=0, sticky="w", pady=(0, 10))

        ttk.Separator(tools).grid(row=10, column=0, sticky="ew", pady=(2, 10))
        logo_header = ttk.Frame(tools)
        logo_header.grid(row=11, column=0, sticky="ew")
        logo_header.columnconfigure(0, weight=1)
        ttk.Label(logo_header, text="▌ LOGO", style=SECTION_STYLE["logo"]).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(logo_header, text="Enable Logo", variable=self.logo_enabled, command=self._logo_enabled_changed).grid(row=0, column=1, sticky="e")
        logo_row = ttk.Frame(tools)
        logo_row.grid(row=12, column=0, sticky="ew", pady=(5, 4))
        logo_row.columnconfigure(0, weight=1)
        ttk.Entry(logo_row, textvariable=self.logo_path).grid(row=0, column=0, sticky="ew")
        ttk.Button(logo_row, text="Browse", width=7, style="Compact.TButton", command=self._browse_logo).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(logo_row, text="Remove", width=7, style="Compact.TButton", command=self._remove_logo).grid(row=0, column=2, padx=(6, 0))
        self.logo_size_slider = slider_row(13, "Size", 0.06, 0.35, self.logo_width_frac, lambda _v: self._redraw_editor_items(),
                                           "logo_size_label", f"{self.logo_width_frac.get()*100:.0f}%", pady=(2, 2))
        self.logo_size_slider.bind("<ButtonRelease-1>", lambda _e: self._redraw_editor_items())
        self.logo_opacity_slider = slider_row(14, "Opacity", 0.10, 1.00, self.logo_opacity, lambda _v: self._logo_opacity_changed(),
                                              "logo_opacity_label", f"{self.logo_opacity.get()*100:.0f}%", pady=(2, 10))
        self.logo_opacity_slider.bind("<ButtonRelease-1>", lambda _e: self._redraw_editor_items())

        section(16, "Extra Text Box", "extra")
        self.extra_text_entry = ttk.Entry(tools, textvariable=self.extra_text, font=("Myanmar Text", 10))
        self.extra_text_entry.grid(row=17, column=0, sticky="ew", pady=(5, 4))
        self.extra_text_entry.bind("<KeyRelease>", lambda _e: self._redraw_editor_items())
        self._extra_size_scale_var = tk.DoubleVar(value=float(self.extra_text_size.get()))
        extra_scale = slider_row(18, "Size", 18, 84, self._extra_size_scale_var,
                                 lambda v: self._int_slider_changed(v, self.extra_text_size, "extra_size_label"),
                                 "extra_size_label", str(int(self.extra_text_size.get())), pady=(0, 2))
        extra_scale.bind("<ButtonRelease-1>", lambda _e: self._redraw_editor_items())
        self.extra_opacity_slider = slider_row(19, "Opacity", 0.10, 1.00, self.extra_text_opacity, lambda _v: self._extra_opacity_changed(),
                                               "extra_opacity_label", f"{self.extra_text_opacity.get()*100:.0f}%", pady=(2, 2))
        self.extra_opacity_slider.bind("<ButtonRelease-1>", lambda _e: self._redraw_editor_items())
        pos_box = ttk.Frame(tools)
        pos_box.grid(row=20, column=0, sticky="ew", pady=(2, 10))
        pos_box.columnconfigure(1, weight=1)
        for r, (label, var, attr) in enumerate((("X", self.extra_x_var, "extra_x_label"), ("Y", self.extra_y_var, "extra_y_label"))):
            ttk.Label(pos_box, text=label, width=3).grid(row=r, column=0, sticky="w")
            ttk.Scale(pos_box, from_=0, to=100, orient="horizontal", variable=var,
                      command=lambda _v: self._extra_pos_slider_changed()).grid(row=r, column=1, sticky="ew")
            value = ttk.Label(pos_box, text=f"{var.get():.0f}%", width=5, anchor="e")
            value.grid(row=r, column=2, padx=(8, 0))
            setattr(self, attr, value)
        btn_row = ttk.Frame(pos_box)
        btn_row.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(btn_row, text="Center", width=8, style="Compact.TButton",
                   command=lambda: self._set_extra_pos(0.5, self.extra_text_pos[1])).grid(row=0, column=0)
        ttk.Button(btn_row, text="Top", width=6, style="Compact.TButton",
                   command=lambda: self._set_extra_pos(self.extra_text_pos[0], 0.12)).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(btn_row, text="Bottom", width=8, style="Compact.TButton",
                   command=lambda: self._set_extra_pos(*lm.DEFAULT_EXTRA_POS)).grid(row=0, column=2, padx=(6, 0))
        ttk.Label(pos_box, text="Preview ပေါ်က မျဉ်းပြတ်ကွက်ကို ဆွဲရွှေ့ပါ၊ မဟုတ်ရင် X / Y သုံးပါ။ အလယ်ကို ကပ်သွားမယ်။",
                  style="Hint.TLabel", wraplength=300, justify="left").grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        # ---- Version 2.0: whole-video look, slow motion, random auto edit (picture only) ----
        section(22, "Video Look & Auto Edit", "look")
        fxbox = ttk.Frame(tools)
        fxbox.grid(row=23, column=0, sticky="ew", pady=(4, 10))
        fxbox.columnconfigure(1, weight=1)
        ttk.Label(fxbox, text="Filter", width=9).grid(row=0, column=0, sticky="w")
        ttk.Combobox(fxbox, textvariable=self.look_preset, values=fx.LOOK_PRESETS, state="readonly",
                     width=14).grid(row=0, column=1, columnspan=2, sticky="w")
        def fx_slider(row: int, label: str, variable, attr: str) -> None:
            ttk.Label(fxbox, text=label, width=9).grid(row=row, column=0, sticky="w", pady=(4, 0))
            ttk.Scale(fxbox, from_=0, to=100, orient="horizontal", variable=variable,
                      command=lambda _v, a=attr, v=variable: getattr(self, a).configure(text=f"{int(float(v.get()))}%")
                      ).grid(row=row, column=1, sticky="ew", pady=(4, 0))
            value = ttk.Label(fxbox, text=f"{int(float(variable.get()))}%", width=5, anchor="e")
            value.grid(row=row, column=2, padx=(8, 0), pady=(4, 0))
            setattr(self, attr, value)
        fx_slider(1, "Strength", self.look_strength, "look_strength_label")
        fx_slider(2, "Vignette", self.look_vignette, "look_vignette_label")
        ttk.Label(fxbox, text="ဗီဒီယိုတစ်ပုဒ်လုံးကို colour filter နဲ့ vignette ထည့်မယ် (0% = ပိတ်)။",
                  style="Hint.TLabel", wraplength=300, justify="left").grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 8))

        ttk.Checkbutton(fxbox, text="Slow motion  (play → slow → play …)", variable=self.slow_enabled
                        ).grid(row=4, column=0, columnspan=3, sticky="w")
        slow_row = ttk.Frame(fxbox)
        slow_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(3, 0))
        ttk.Label(slow_row, text="Slow").grid(row=0, column=0, sticky="w")
        ttk.Combobox(slow_row, textvariable=self.slow_len, values=tuple(f"{n} s" for n in fx.SLOW_LENGTHS),
                     state="readonly", width=5).grid(row=0, column=1, padx=(4, 8))
        ttk.Label(slow_row, text="Speed").grid(row=0, column=2, sticky="w")
        ttk.Combobox(slow_row, textvariable=self.slow_speed, values=tuple(f"{n:g}×" for n in fx.SLOW_SPEEDS),
                     state="readonly", width=5).grid(row=0, column=3, padx=(4, 8))
        ttk.Label(slow_row, text="Every").grid(row=0, column=4, sticky="w")
        ttk.Combobox(slow_row, textvariable=self.slow_gap, values=tuple(f"{n} s" for n in fx.SLOW_GAPS),
                     state="readonly", width=5).grid(row=0, column=5, padx=(4, 0))

        ttk.Checkbutton(fxbox, text="Auto edit  (random mix)", variable=self.auto_enabled
                        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        effects_row = ttk.Frame(fxbox)
        effects_row.grid(row=7, column=0, columnspan=3, sticky="w", pady=(3, 0))
        for i, name in enumerate(fx.AUTO_EFFECTS):
            ttk.Checkbutton(effects_row, text=name.capitalize(), variable=self.auto_effect_vars[name]
                            ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 8))
        auto_row = ttk.Frame(fxbox)
        auto_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(3, 0))
        ttk.Label(auto_row, text="Intensity").grid(row=0, column=0, sticky="w")
        ttk.Combobox(auto_row, textvariable=self.auto_intensity, values=tuple(fx.AUTO_INTENSITY), state="readonly",
                     width=8).grid(row=0, column=1, padx=(4, 8))
        ttk.Label(auto_row, text="Seed").grid(row=0, column=2, sticky="w")
        ttk.Entry(auto_row, textvariable=self.auto_seed, width=8).grid(row=0, column=3, padx=(4, 0))
        ttk.Label(fxbox, text="ကျပန်းအပိုင်းတွေကို ရွေးထားတဲ့ effect တွေ ရောနှောပြီး ထည့်မယ်။ Seed တူရင် edit တူမယ် "
                              "(ဗလာဆိုရင် video တစ်ပုဒ်ချင်းစီအတွက် ပုံသေ)။ Slow / Freeze ကြာချိန်က Slow နဲ့ Freeze အကွက်တွေအတိုင်းပဲ။ "
                              "ဖွင့်ထားရင် Freeze rhythm နဲ့ Slow motion ကို အစားထိုးမယ်။",
                  style="Hint.TLabel", wraplength=300, justify="left").grid(row=9, column=0, columnspan=3, sticky="w", pady=(4, 0))
        # ---- Myanmar subtitles: the narration burned into the bottom of the picture, timed with the voice ----
        section(25, "Myanmar Subtitle", "subtitle")
        subbox = ttk.Frame(tools)
        subbox.grid(row=26, column=0, sticky="ew", pady=(4, 10))
        subbox.columnconfigure(1, weight=1)
        ttk.Checkbutton(subbox, text="Burn in Myanmar subtitle", variable=self.sub_enabled,
                        command=self._redraw_editor_items).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(subbox, text="Size", width=9).grid(row=1, column=0, sticky="w", pady=(4, 0))
        sub_size_combo = ttk.Combobox(subbox, textvariable=self.sub_size,
                                      values=tuple(self._sub_size_label(n) for n in subs.SUB_SIZES), state="readonly", width=14)
        sub_size_combo.grid(row=1, column=1, sticky="w", pady=(4, 0))
        sub_size_combo.bind("<<ComboboxSelected>>", lambda _e: self._sub_size_changed())
        ttk.Label(subbox, text="Style", width=9).grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Combobox(subbox, textvariable=self.sub_style, values=tuple(subs.SUB_STYLES), state="readonly",
                     width=22).grid(row=2, column=1, sticky="w", pady=(4, 0))
        # position: X / Y sliders, three buttons, or drag the sample box on the preview
        for r, (label, var, attr, lo, hi) in enumerate((
                ("X", self.sub_x_var, "sub_x_label", lm.SUB_X_RANGE[0] * 100, lm.SUB_X_RANGE[1] * 100),
                ("Y", self.sub_y_var, "sub_y_label", 0, 100))):
            ttk.Label(subbox, text=label, width=9).grid(row=3 + r, column=0, sticky="w", pady=(4, 0))
            ttk.Scale(subbox, from_=lo, to=hi, orient="horizontal", variable=var,
                      command=lambda _v: self._sub_pos_slider_changed()).grid(row=3 + r, column=1, sticky="ew", pady=(4, 0))
            value = ttk.Label(subbox, text=f"{var.get():.0f}%", width=5, anchor="e")
            value.grid(row=3 + r, column=2, padx=(8, 0), pady=(4, 0))
            setattr(self, attr, value)
        sub_btns = ttk.Frame(subbox)
        sub_btns.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(sub_btns, text="Center", width=8, style="Compact.TButton",
                   command=lambda: self._set_sub_pos(0.5, self.sub_pos[1])).grid(row=0, column=0)
        ttk.Button(sub_btns, text="Top", width=6, style="Compact.TButton",
                   command=lambda: self._set_sub_pos(self.sub_pos[0], 0.20)).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(sub_btns, text="Bottom", width=8, style="Compact.TButton",
                   command=lambda: self._set_sub_pos(*lm.DEFAULT_SUB_POS)).grid(row=0, column=2, padx=(6, 0))
        ttk.Label(subbox, text="မြန်မာ narration စာကို အသံနဲ့ ကိုက်အောင် ပြမယ်။ Preview ပေါ်က စာတန်းကွက်ကို ဆွဲရွှေ့ပါ၊ "
                               "မဟုတ်ရင် X / Y သုံးပါ။ ဘေးဘက်ကို ရွှေ့လေ စာကြောင်း ကျဉ်းလေပါ။ "
                               "Size က နှိုင်းရပါ: 9 / 12 / 14 = 1080 px canvas မှာ 36 / 48 / 56 px။",
                  style="Hint.TLabel", wraplength=300, justify="left").grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self._bind_wheel_recursive(tools, tools_canvas)
        # Job resume / config loads set the IntVars directly; keep the sliders in step.
        self.title_size.trace_add("write", lambda *_a: self._sync_int_slider(self.title_size, self._title_size_scale_var, "title_size_label"))
        self.extra_text_size.trace_add("write", lambda *_a: self._sync_int_slider(self.extra_text_size, self._extra_size_scale_var, "extra_size_label"))

        main.add(left, weight=3)           # menus on the left: settings + logs, then the production tools
        main.add(tools_host, weight=3)
        main.add(preview_box, weight=6)    # preview on the far right
        self._main_pane, self._left_pane = main, left
        self.after(250, self._apply_pane_layout)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        controls = ttk.Frame(outer)
        controls.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        controls.columnconfigure(0, weight=1)
        btns = ttk.Frame(controls)
        btns.grid(row=0, column=0, sticky="ew")
        self.start_btn = ttk.Button(btns, text="START / RESUME", style="Accent.TButton", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btns, text="STOP SAFELY", style="Danger.TButton", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        ttk.Button(btns, text="Output Video", command=self._open_output).pack(side="left")
        ttk.Button(btns, text="Edit Text", command=self._open_text_editor).pack(side="left", padx=(8, 0))
        ttk.Label(btns, textvariable=self.job_display, style="Muted.TLabel").pack(side="left", padx=(12, 0))
        ttk.Label(btns, textvariable=self.stage, style="Muted.TLabel").pack(side="right", padx=(8, 0))
        ttk.Label(btns, textvariable=self.status, style="Status.TLabel").pack(side="right")

    # ---------------------------------------------------------------- layout helpers
    UI_LAYOUT_FILE = LOGS_DIR / "ui_layout.json"

    @staticmethod
    def _bind_wheel(widget: tk.Misc, canvas: tk.Canvas) -> None:
        widget.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"), add="+")

    def _bind_wheel_recursive(self, widget: tk.Misc, canvas: tk.Canvas) -> None:
        # Sliders and combo/spin boxes keep their own wheel behaviour.
        if not isinstance(widget, (ttk.Scale, ttk.Combobox, ttk.Spinbox)):
            self._bind_wheel(widget, canvas)
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child, canvas)

    def _apply_pane_layout(self) -> None:
        """Default sashes (settings pane ~27%, tools ~25%, preview the rest); a layout dragged last time wins."""
        try:
            self.update_idletasks()
            width = self._main_pane.winfo_width()
            height = self._left_pane.winfo_height()
            if width < 400 or height < 200:
                self.after(250, self._apply_pane_layout)
                return
            try:
                saved = json.loads(self.UI_LAYOUT_FILE.read_text(encoding="utf-8"))
            except Exception:
                saved = {}
            # panes, left to right: menus (settings + logs) | production tools | preview (far right)
            left_w = int(saved.get("menu_left_fraction", 0.27) * width)
            tools_w = int(saved.get("menu_tools_fraction", 0.25) * width)
            left_w = max(380, min(left_w, width - tools_w - 420))
            tools_w = max(420, min(tools_w, width - left_w - 420))
            self._main_pane.sashpos(0, left_w)
            self._main_pane.sashpos(1, left_w + tools_w)
            setup_h = int(saved.get("setup_fraction", 0) * height) or int(height * 0.62)
            self._left_pane.sashpos(0, max(160, min(setup_h, height - 120)))
        except Exception as exc:
            self._log(f"⚠️ Layout restore skipped: {exc}")

    def _save_pane_layout(self) -> None:
        try:
            width = max(1, self._main_pane.winfo_width())
            height = max(1, self._left_pane.winfo_height())
            data = {
                "menu_left_fraction": round(self._main_pane.sashpos(0) / width, 4),
                "menu_tools_fraction": round((self._main_pane.sashpos(1) - self._main_pane.sashpos(0)) / width, 4),
                "setup_fraction": round(self._left_pane.sashpos(0) / height, 4),
            }
            self.UI_LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.UI_LAYOUT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _set_app_icon(self) -> None:
        """Window / taskbar icon from app/assets. A missing or unreadable icon must never stop the app from starting."""
        try:
            png, ico = ICON_DIR / "icon.png", ICON_DIR / "icon.ico"
            if os.name == "nt":
                try:
                    import ctypes     # own AppUserModelID so the taskbar shows this icon, not the python.exe one
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KG.beta.version.3.0")
                except Exception:
                    pass
                if ico.is_file():
                    self.iconbitmap(default=str(ico))
            if png.is_file():
                self._app_icon = tk.PhotoImage(file=str(png))     # keep a reference, Tk drops the icon otherwise
                self.iconphoto(True, self._app_icon)
        except Exception:
            pass

    def _on_close(self) -> None:
        self._save_pane_layout()
        self.destroy()

    def _voice_volume_changed(self, value) -> None:
        import math
        percent = int(round(float(value) / 5.0) * 5)  # 5% steps
        self.voice_volume.set(percent)
        self.voice_volume_label.configure(text=f"{percent}% ({20 * math.log10(percent / 100.0):+.1f}dB)")

    def _mirror_changed(self) -> None:
        # Persist right away so the choice survives a restart even before START.
        self.cfg["mirror_video"] = bool(self.mirror_video.get())
        save_config(self.cfg)
        self._log(f"🔁 Flip / mirror {'ON' if self.mirror_video.get() else 'OFF'} — video parts re-render on next run; TTS is reused.")
        self._refresh_preview()

    def _sync_int_slider(self, source: tk.IntVar, scale_var: tk.DoubleVar, label_attr: str) -> None:
        try:
            number = int(source.get())
        except (tk.TclError, ValueError):
            return
        scale_var.set(float(number))
        getattr(self, label_attr).configure(text=str(number))

    def _int_slider_changed(self, value: str, target: tk.IntVar, label_attr: str) -> None:
        number = int(round(float(value)))
        target.set(number)
        getattr(self, label_attr).configure(text=str(number))
        self._redraw_editor_items()

    def _preview_resized(self, event) -> None:
        size = (max(160, int(event.width) - 2), max(90, int(event.height) - 2))
        if size == self._preview_canvas_size:
            return
        self._preview_canvas_size = size
        self._redraw_editor_items()
        # Re-extract the frame only after the user stops resizing.
        if self._preview_resize_job is not None:
            self.after_cancel(self._preview_resize_job)
        self._preview_resize_job = self.after(300, self._refresh_preview)

    def _seek_preview(self, seconds: float) -> None:
        upper = float(self.preview_duration or 0.0)
        value = float(self.preview_time.get()) + seconds
        self.preview_time.set(max(0.0, min(value, max(0.0, upper - 0.05)) if upper else max(0.0, value)))
        self._update_preview_time_label()
        self._refresh_preview()

    def _update_preview_time_label(self) -> None:
        def fmt(sec: float) -> str:
            sec = max(0, int(sec))
            h, rem = divmod(sec, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        if hasattr(self, "preview_time_label"):
            self.preview_time_label.configure(text=f"{fmt(self.preview_time.get())} / {fmt(self.preview_duration or 0)}")

    def _edge_rate_changed(self, value: str) -> None:
        try:
            self.edge_speed_value.configure(text=_format_edge_rate(value))
        except Exception:
            pass

    def _create_log_tab(self, title: str) -> tk.Text:
        frame = ttk.Frame(self.log_notebook)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        box = tk.Text(
            frame, wrap="word", width=36, height=12, bg="#03060a", fg="#a9d8ea",
            insertbackground=ACCENT, selectbackground=ACCENT_DIM, selectforeground="#ffffff",
            relief="flat", borderwidth=0, padx=8, pady=8, font=("Consolas", 9),
        )
        box.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=box.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        box.configure(yscrollcommand=scroll.set)
        self.log_notebook.add(frame, text=title)
        return box

    def _zoom_changed(self, value: str) -> None:
        try:
            self.zoom_value_label.configure(text=f"{float(value):.2f}x")
        except Exception:
            pass

    def _logo_opacity_changed(self) -> None:
        try:
            self.logo_opacity_label.configure(text=f"{float(self.logo_opacity.get())*100:.0f}%")
        except Exception:
            pass

    def _extra_opacity_changed(self) -> None:
        try:
            self.extra_opacity_label.configure(text=f"{float(self.extra_text_opacity.get())*100:.0f}%")
        except Exception:
            pass

    def _persist_logo_choice(self) -> None:
        """Persist logo enable/path immediately so a removed logo cannot return on restart."""
        try:
            self.cfg["logo_enabled"] = bool(self.logo_enabled.get())
            self.cfg["logo_path"] = self.logo_path.get().strip() if self.logo_enabled.get() else ""
            save_config(self.cfg)
        except Exception as exc:
            self._log(f"⚠️ Could not save logo setting: {exc}")

    def _logo_enabled_changed(self) -> None:
        # OFF means no logo is passed to the renderer even when a legacy path still exists.
        self._persist_logo_choice()
        self._redraw_editor_items()

    def _remove_logo(self) -> None:
        # Full removal: clear both the toggle and saved path so app/job resume cannot revive it.
        self.logo_enabled.set(False)
        self.logo_path.set("")
        self._logo_photo = None
        self._persist_logo_choice()
        self._redraw_editor_items()
        self.status.set("LOGO REMOVED")
        self._log("🧹 Logo removed and saved setting cleared.")

    def _browse_logo(self) -> None:
        p = filedialog.askopenfilename(title="Select logo", filetypes=[("Image", "*.png *.webp *.jpg *.jpeg"), ("All", "*.*")])
        if p:
            self.logo_path.set(p)
            self.logo_enabled.set(True)
            self._persist_logo_choice()
            self._redraw_editor_items()

    def _begin_blur_box(self) -> None:
        self._draw_blur_mode = True
        self.selected_blur = None
        self.preview_canvas.configure(cursor="crosshair")
        self.status.set("DRAW BLUR BOX")

    def _delete_selected_blur(self) -> None:
        if self.selected_blur is None:
            return
        if 0 <= self.selected_blur < len(self.blur_boxes):
            self.blur_boxes.pop(self.selected_blur)
        self.selected_blur = None
        self._redraw_editor_items()

    def _fill_code(self) -> str:
        return next((code for code, label in FILL_LABELS.items() if label == self.frame_fill.get()), "blur")

    def _output_canvas(self) -> tuple[int, int]:
        """Size of the final frame for the chosen Ratio (Original follows the loaded video)."""
        return output_canvas(self.output_ratio.get(), *self.source_size)

    def _frame_changed(self) -> None:
        self._redraw_editor_items()
        self._refresh_preview()

    def _preview_bounds(self) -> tuple[int, int, int, int]:
        """Largest output-shaped frame (Ratio) that fits the canvas: (x offset, y offset, width, height).

        Overlay positions are stored as 0..1 fractions of the output frame, so the preview
        can be any size without moving where Title/Logo/Blur land in the render.
        """
        cw, ch = getattr(self, "_preview_canvas_size", (PREVIEW_W, PREVIEW_H))
        fw, fh = self._output_canvas() if hasattr(self, "output_ratio") else (1920, 1080)
        scale = min(cw / fw, ch / fh)
        width, height = max(16, int(fw * scale)) // 2 * 2, max(16, int(fh * scale)) // 2 * 2
        return (cw - width) // 2, (ch - height) // 2, width, height

    def _preview_xy(self, event) -> tuple[float, float]:
        ox, oy, width, height = self._preview_bounds()
        return (max(float(ox), min(float(event.x), ox + width)),
                max(float(oy), min(float(event.y), oy + height)))

    def _refresh_preview(self) -> None:
        src = self.source.get().strip()
        if not src or not Path(src).is_file():
            return
        try:
            ffmpeg = _tool_path(self.cfg, "ffmpeg")
            ox, oy, width, height = self._preview_bounds()
            out = LOGS_DIR / "preview_frame.png"
            extract_preview_frame(
                ffmpeg, src, float(self.preview_time.get()), float(self.zoom_factor.get()),
                bool(self.mirror_video.get()), str(out), width, height,
                ratio=self.output_ratio.get(), fill=self._fill_code(), source_size=self.source_size,
            )
            self._preview_photo = tk.PhotoImage(file=str(out))
            self.preview_canvas.delete("frame")
            self.preview_canvas.create_image(ox, oy, image=self._preview_photo, anchor="nw", tags=("frame",))
            self.preview_canvas.tag_lower("frame")
            self._redraw_editor_items()
            self._update_preview_time_label()
        except Exception as exc:
            self._log(f"⚠️ Preview frame error: {exc}")

    def _redraw_editor_items(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        c = self.preview_canvas
        c.delete("editor")
        ox, oy, pw, ph = self._preview_bounds()
        arm = max(10, min(pw, ph) // 14)
        for cx, cy, sx, sy in ((ox, oy, 1, 1), (ox + pw, oy, -1, 1), (ox, oy + ph, 1, -1), (ox + pw, oy + ph, -1, -1)):
            c.create_line(cx, cy + sy * arm, cx, cy, cx + sx * arm, cy, fill=ACCENT, width=2, tags=("editor", "hud"))
        self.blur_count_label.configure(text=f"{len(self.blur_boxes)} box" + ("es" if len(self.blur_boxes) != 1 else ""))
        for i, b in enumerate(self.blur_boxes):
            x1, y1 = ox + b["x"] * pw, oy + b["y"] * ph
            x2, y2 = ox + (b["x"] + b["w"]) * pw, oy + (b["y"] + b["h"]) * ph
            color = "#ffd166" if i == self.selected_blur else "#48d7ff"
            c.create_rectangle(x1, y1, x2, y2, outline=color, width=2, dash=(6, 4), tags=("editor", "blur", f"blur_{i}"))
            c.create_text(x1 + 5, y1 + 5, text="BLUR", fill=color, anchor="nw", font=("Segoe UI Semibold", 9), tags=("editor", f"blur_{i}"))
            if i == self.selected_blur:
                c.create_rectangle(x2-5, y2-5, x2+5, y2+5, fill=color, outline="#111111", tags=("editor", f"blur_handle_{i}"))

        if self.sub_enabled.get():
            self._draw_subtitle_sample(c, ox, oy, pw, ph)

        txt = self.title_text.get().strip()
        if txt:
            px = ox + float(self.title_pos[0]) * pw
            py = oy + float(self.title_pos[1]) * ph
            fs = max(10, int(self.title_size.get() * pw / self._output_canvas()[0]))
            c.create_text(px+2, py+2, text=txt, fill="#000000", anchor="center", font=("Myanmar Text", fs, "bold"), width=int(pw*0.82), tags=("editor", "title"))
            c.create_text(px, py, text=txt, fill="#ffffff", anchor="center", font=("Myanmar Text", fs, "bold"), width=int(pw*0.82), tags=("editor", "title"))

        extra_txt = self.extra_text.get().strip()
        if extra_txt:
            ex = ox + float(self.extra_text_pos[0]) * pw
            ey = oy + float(self.extra_text_pos[1]) * ph
            efs = max(9, int(self.extra_text_size.get() * pw / self._output_canvas()[0]))
            opacity = max(0.10, min(1.00, float(self.extra_text_opacity.get())))
            shade = max(140, min(255, int(255 * opacity)))
            fill = f"#{shade:02x}{shade:02x}{shade:02x}"
            c.create_text(ex+2, ey+2, text=extra_txt, fill="#101010", anchor="center", font=("Myanmar Text", efs, "bold"), width=int(pw*0.78), tags=("editor", "extra_text"))
            c.create_text(ex, ey, text=extra_txt, fill=fill, anchor="center", font=("Myanmar Text", efs, "bold"), width=int(pw*0.78), tags=("editor", "extra_text"))
            box = self._extra_bbox()
            if box is not None:
                x1, y1, x2, y2 = box
                self._extra_half = (max(0.0, (x2 - x1) / 2 / pw), max(0.0, (y2 - y1) / 2 / ph))
                dragging = self._drag_kind == "extra_text"
                c.create_rectangle(x1 - 6, y1 - 4, x2 + 6, y2 + 4, outline="#ffd166" if dragging else "#48d7ff", width=2,
                                   dash=(6, 4), tags=("editor", "extra_text"))
                c.create_text(x1 - 4, y1 - 6, text="TEXT", fill="#ffd166" if dragging else "#48d7ff", anchor="sw",
                              font=("Segoe UI Semibold", 8), tags=("editor", "extra_text"))
                if dragging and self._extra_snap[0]:
                    c.create_line(ox + pw / 2, oy, ox + pw / 2, oy + ph, fill="#ffd166", dash=(3, 5), tags=("editor",))
                if dragging and self._extra_snap[1]:
                    c.create_line(ox, oy + ph / 2, ox + pw, oy + ph / 2, fill="#ffd166", dash=(3, 5), tags=("editor",))
        logo = self.logo_path.get().strip() if self.logo_enabled.get() else ""
        if logo and Path(logo).is_file():
            try:
                ffmpeg = _tool_path(self.cfg, "ffmpeg")
                lw = max(36, int(pw * float(self.logo_width_frac.get())))
                tmp = LOGS_DIR / "preview_logo.png"
                scale_logo_preview(ffmpeg, logo, lw, str(tmp))
                self._logo_photo = tk.PhotoImage(file=str(tmp))
                self.logo_size_label.configure(text=f"{float(self.logo_width_frac.get())*100:.0f}%")
                x, y = ox + float(self.logo_pos[0])*pw, oy + float(self.logo_pos[1])*ph
                c.create_image(x, y, image=self._logo_photo, anchor="nw", tags=("editor", "logo"))
            except Exception as exc:
                self._log(f"⚠️ Logo preview error: {exc}")

    def _preview_press(self, event) -> None:
        x, y = self._preview_xy(event)
        if self._draw_blur_mode:
            self._draw_start = (x, y)
            self._temp_rect = self.preview_canvas.create_rectangle(x, y, x, y, outline="#48d7ff", width=2, dash=(6,4), tags=("editor", "temp_blur"))
            return
        items = self.preview_canvas.find_overlapping(x-3, y-3, x+3, y+3)
        tags = []
        for item in reversed(items):
            t = self.preview_canvas.gettags(item)
            if t:
                tags.append(t)
        self._drag_kind = None
        self._drag_index = None
        self._drag_start = (x, y)
        for t in tags:
            handle = next((z for z in t if z.startswith("blur_handle_")), None)
            blur = next((z for z in t if z.startswith("blur_") and not z.startswith("blur_handle_")), None)
            if handle:
                i = int(handle.rsplit("_",1)[1]); self.selected_blur=i; self._drag_kind="blur_resize"; self._drag_index=i; self._drag_original=dict(self.blur_boxes[i]); break
            if "title" in t:
                self._drag_kind="title"; break
            if "extra_text" in t:
                self._drag_kind="extra_text"
                ox, oy, pw, ph = self._preview_bounds()
                self._extra_grab = (x - (ox + float(self.extra_text_pos[0]) * pw), y - (oy + float(self.extra_text_pos[1]) * ph))
                break
            if "sub_text" in t:
                self._drag_kind="sub_text"
                ox, oy, pw, ph = self._preview_bounds()
                self._sub_grab = (x - (ox + float(self.sub_pos[0]) * pw), y - (oy + float(self.sub_pos[1]) * ph))
                break
            if "logo" in t:
                self._drag_kind="logo"; self._drag_original=list(self.logo_pos); break
            if blur:
                i=int(blur.rsplit("_",1)[1]); self.selected_blur=i; self._drag_kind="blur_move"; self._drag_index=i; self._drag_original=dict(self.blur_boxes[i]); break
        self._redraw_editor_items()

    def _preview_motion(self, event) -> None:
        x, y = self._preview_xy(event)
        if self._draw_blur_mode and self._draw_start and self._temp_rect:
            self.preview_canvas.coords(self._temp_rect, self._draw_start[0], self._draw_start[1], x, y)
            return
        if not self._drag_kind or not self._drag_start:
            return
        ox, oy, pw, ph = self._preview_bounds()
        dx=(x-self._drag_start[0])/pw; dy=(y-self._drag_start[1])/ph
        if self._drag_kind == "title":
            self.title_pos=[(x-ox)/pw, (y-oy)/ph]
        elif self._drag_kind == "extra_text":
            pos = lm.drag_position((x, y), self._extra_grab, (ox, oy), (pw, ph), self._extra_half)
            self.extra_text_pos, self._extra_snap = lm.snap_center(pos)
            self._sync_extra_pos_sliders()
        elif self._drag_kind == "sub_text":
            pos = lm.drag_sub_position((x, y), self._sub_grab, (ox, oy), (pw, ph), self._sub_half_h())
            self.sub_pos, self._sub_snap = lm.snap_x(pos)
            self._sync_sub_pos_sliders()
        elif self._drag_kind == "logo":
            lx,ly=self._drag_original
            self.logo_pos=[max(0.0,min(0.95,lx+dx)), max(0.0,min(0.95,ly+dy))]
        elif self._drag_index is not None:
            i=self._drag_index; old=self._drag_original; b=dict(old)
            if self._drag_kind == "blur_move":
                b["x"]=max(0.0,min(1.0-old["w"],old["x"]+dx)); b["y"]=max(0.0,min(1.0-old["h"],old["y"]+dy))
            else:
                b["w"]=max(0.015,min(1.0-old["x"],old["w"]+dx)); b["h"]=max(0.015,min(1.0-old["y"],old["h"]+dy))
            self.blur_boxes[i]=b
        self._redraw_editor_items()

    def _preview_release(self, event) -> None:
        x, y = self._preview_xy(event)
        if self._draw_blur_mode and self._draw_start:
            ox, oy, pw, ph = self._preview_bounds()
            x1,y1=self._draw_start; x2,y2=x,y
            if abs(x2-x1)>=12 and abs(y2-y1)>=12:
                xa,xb=sorted((x1,x2)); ya,yb=sorted((y1,y2))
                self.blur_boxes.append({"x":(xa-ox)/pw,"y":(ya-oy)/ph,"w":(xb-xa)/pw,"h":(yb-ya)/ph})
                self.selected_blur=len(self.blur_boxes)-1
            self._draw_blur_mode=False; self._draw_start=None; self._temp_rect=None
            self.preview_canvas.configure(cursor="arrow")
            self.status.set("READY")
            self._redraw_editor_items()
            return
        self._drag_kind=None; self._drag_index=None; self._drag_start=None; self._drag_original=None
        self._extra_snap = (False, False)
        self._sub_snap = False
        self._redraw_editor_items()

    # ---- Extra text position: sliders, buttons, bounding box ----
    def _extra_bbox(self):
        """The Extra text on the preview as (x1, y1, x2, y2) in canvas pixels, or None."""
        try:
            box = self.preview_canvas.bbox("extra_text")
            x1, y1, x2, y2 = (float(v) for v in box)
            return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None
        except Exception:
            return None

    def _sync_extra_pos_sliders(self) -> None:
        self._syncing_extra = True
        try:
            x, y = lm.pos_to_slider(self.extra_text_pos)
            self.extra_x_var.set(x)
            self.extra_y_var.set(y)
            self.extra_x_label.configure(text=f"{x:.0f}%")
            self.extra_y_label.configure(text=f"{y:.0f}%")
        finally:
            self._syncing_extra = False

    def _extra_pos_slider_changed(self) -> None:
        if self._syncing_extra:
            return
        self.extra_text_pos = lm.slider_to_pos(self.extra_x_var.get(), self.extra_y_var.get(), self._extra_half)
        self.extra_x_label.configure(text=f"{self.extra_x_var.get():.0f}%")
        self.extra_y_label.configure(text=f"{self.extra_y_var.get():.0f}%")
        self._redraw_editor_items()

    def _set_extra_pos(self, x: float, y: float) -> None:
        self.extra_text_pos = lm.clamp_center((x, y), self._extra_half)
        self._sync_extra_pos_sliders()
        self._redraw_editor_items()

    # ---- Myanmar subtitle position: sample box on the preview, sliders, buttons ----
    def _sub_size_units(self) -> int:
        return int(self._first_number(self.sub_size.get(), 12))

    def _sub_half_h(self) -> float:
        """Half the height of a two-line subtitle as a fraction of the picture (it must stay inside the picture)."""
        cw, ch = self._output_canvas()
        return subs.text_half_height(self._sub_size_units(), cw, ch)

    def _sub_box(self) -> tuple[float, float, float, float]:
        """The subtitle sample on the preview as (x1, y1, x2, y2) in canvas pixels; its bottom centre is sub_pos."""
        ox, oy, pw, ph = self._preview_bounds()
        cw, ch = self._output_canvas()
        x, y, width_frac = subs.subtitle_layout({"size": self._sub_size_units(), "position": self.sub_pos}, cw, ch)
        cx, bottom = ox + x * pw, oy + y * ph
        return cx - width_frac * pw / 2, bottom - 2 * self._sub_half_h() * ph, cx + width_frac * pw / 2, bottom

    def _draw_subtitle_sample(self, c, ox: float, oy: float, pw: float, ph: float) -> None:
        cw, ch = self._output_canvas()
        x1, y1, x2, y2 = self._sub_box()
        dragging = self._drag_kind == "sub_text"
        colour = "#ffd166" if dragging else SECTION_COLORS["subtitle"]
        # a faint fill makes the whole box easy to grab; it is drawn below Title / Extra text so they stay grabbable
        c.create_rectangle(x1, y1, x2, y2, outline=colour, fill=colour, stipple="gray12", width=2, dash=(6, 4),
                           tags=("editor", "sub_text"))
        c.create_text(x1 + 2, y1 - 3, text="SUBTITLE", fill=colour, anchor="sw", font=("Segoe UI Semibold", 8),
                      tags=("editor", "sub_text"))
        font_px = -max(9, int(subs.subtitle_px(self._sub_size_units(), cw, ch) * pw / cw))
        cx = (x1 + x2) / 2
        c.create_text(cx + 1, y2 - 1, text="မြန်မာ စာတန်း", fill="#000000", anchor="s", font=("Myanmar Text", font_px, "bold"),
                      tags=("editor", "sub_text"))
        c.create_text(cx, y2 - 2, text="မြန်မာ စာတန်း", fill="#ffd400", anchor="s", font=("Myanmar Text", font_px, "bold"),
                      tags=("editor", "sub_text"))
        if dragging and self._sub_snap:
            c.create_line(ox + pw / 2, oy, ox + pw / 2, oy + ph, fill="#ffd166", dash=(3, 5), tags=("editor",))

    def _sync_sub_pos_sliders(self) -> None:
        self._syncing_sub = True
        try:
            x, y = lm.pos_to_slider(self.sub_pos)
            self.sub_x_var.set(x)
            self.sub_y_var.set(y)
            self.sub_x_label.configure(text=f"{x:.0f}%")
            self.sub_y_label.configure(text=f"{y:.0f}%")
        finally:
            self._syncing_sub = False

    def _sub_pos_slider_changed(self) -> None:
        if self._syncing_sub:
            return
        self.sub_pos = lm.clamp_sub_pos((self.sub_x_var.get() / 100.0, self.sub_y_var.get() / 100.0), self._sub_half_h())
        self._sync_sub_pos_sliders()
        self._redraw_editor_items()

    def _set_sub_pos(self, x: float, y: float) -> None:
        self.sub_pos = lm.clamp_sub_pos((x, y), self._sub_half_h())
        self._sync_sub_pos_sliders()
        self._redraw_editor_items()

    def _sub_size_changed(self) -> None:
        """A bigger subtitle is taller: keep it inside the picture."""
        self._set_sub_pos(self.sub_pos[0], self.sub_pos[1])

    def _append_log_file(self, text: str) -> None:
        paths = [LOGS_DIR / "latest.log"]
        if self.run_log_path:
            paths.append(self.run_log_path)
        stamp = datetime.now().strftime("%H:%M:%S")
        for path in paths:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as f:
                    f.write(f"[{stamp}] {text}\n")
            except Exception:
                pass

    def _log(self, text: str) -> None:
        self.msgq.put(("log", str(text)))

    def _set_progress(self, current: int, total: int, label: str) -> None:
        self.msgq.put(("progress", (current, total, label)))

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "log":
                    text = str(payload)
                    self.logbox.insert("end", text + "\n")
                    self.logbox.see("end")
                    self._append_log_file(text)
                elif kind == "progress":
                    current, total, label = payload
                    pct = 0 if not total else current * 100.0 / total
                    self.progress["value"] = max(0, min(100, pct))
                    self.status.set(str(label))
                elif kind == "stage":
                    self.stage.set(str(payload))
                elif kind == "job":
                    self.job_display.set(str(payload))
                elif kind == "done":
                    self._running(False)
                    self.progress["value"] = 100
                    self.status.set("DONE")
                    self.stage.set("Completed")
                    messagebox.showinfo("DONE", str(payload))
                elif kind == "error":
                    self._running(False)
                    self.status.set("ERROR")
                    self.stage.set("Stopped")
                    messagebox.showerror("ERROR", str(payload))
                    failed_segment = failed_segment_from_error(str(payload))
                    if failed_segment and messagebox.askyesno(
                        "Edit Text",
                        f"Line {failed_segment} မှာ အသံထုတ်လို့ မရလို့ ရပ်သွားပါတယ်။\n"
                        "စာသားကြောင့် ဖြစ်နိုင်ပါတယ် (ဥပမာ English စာလုံးတွေ ရောနေတာ) — အဲ့စာကြောင်းကို ဖွင့်ပြီး ပြင်မလား?\n"
                        "ပြင်ပြီး Save နှိပ်ပြီးရင် START / RESUME ပြန်နှိပ်ပါ။",
                    ):
                        self._open_text_editor(failed_segment)
        except queue.Empty:
            pass
        self.after(150, self._pump)

    def _tts_provider_changed(self) -> None:
        """Edge: as before. MMS: the Edge voice becomes the fallback voice, speed applies to both."""
        if parse_tts_provider(self.tts_provider.get()) == "mms":
            self.edge_voice_label.configure(text="Fallback Edge Voice")
            self.edge_voice_hint.configure(text="Meta MMS အသံမထွက်ရင် ဒီအသံနဲ့ အစားထိုးဖတ်မယ်")
            self.edge_speed_label.configure(text="Voice Speed")
            self.tts_provider_hint.configure(
                text="အခမဲ့၊ offline၊ key မလို။ INSTALL_MMS.bat ကို တစ်ခါ run ရမယ်။ Edge ထက် စက်ရုပ်အသံဆန်ပြီး အသံတစ်မျိုးတည်း")
        else:
            self.edge_voice_label.configure(text="Edge TTS Voice")
            self.edge_voice_hint.configure(text="စက်ထဲက Edge TTS အသံ")
            self.edge_speed_label.configure(text="Edge TTS Speed")
            self.tts_provider_hint.configure(text="Microsoft Edge အသံတွေ (internet လိုတယ်)")

    def _whisper_model_for(self, code: str) -> str:
        """English keeps the English-only small.en; every other language needs a multilingual model."""
        if code == "en":
            return ""
        if code == "zh":
            return str(self.cfg.get("whisper_model_zh", "small"))
        return str(self.cfg.get("whisper_model_other", "small"))

    @staticmethod
    def _sub_size_label(size: int) -> str:
        return {9: "9  (small)", 12: "12  (medium)", 14: "14  (large)"}.get(int(size), str(size))

    @staticmethod
    def _first_number(text: str, default: float) -> float:
        """"5 s" -> 5.0, "0.5×" -> 0.5 (what the small dropdowns hold)."""
        m = re.search(r"\d+(?:\.\d+)?", str(text or ""))
        return float(m.group(0)) if m else float(default)

    def _lang_code(self) -> str:
        return SOURCE_LANGS.get(self.source_lang.get(), "en")

    def _job_dir(self, source: Path) -> Path:
        return _job_dir_for(source, self._lang_code())

    def _language_changed(self, initial: bool = False) -> None:
        """Header text follows the language; a loaded video switches to that language's job folder."""
        code = self._lang_code()
        name = SOURCE_LANG_NAMES[code]
        self.header_note.configure(text=f"{name} → Myanmar")
        if hasattr(self, "source_lang_hint"):
            if code == "auto":
                hint_text = "Whisper က video တစ်ပုဒ်ချင်းစီရဲ့ ဘာသာစကားကို အလိုအလျောက်ရှာပြီး AI က မြန်မာလို ဘာသာပြန်မယ်"
            elif code == "en":
                hint_text = "Whisper က အင်္ဂလိပ်စကားကို နားထောင်ပြီး AI က မြန်မာလို ဘာသာပြန်မယ်"
            else:
                hint_text = (f"Whisper က {SOURCE_LANG_NAMES[code]} စကားကို (multilingual model နဲ့) နားထောင်ပြီး "
                             "AI က မြန်မာလို ဘာသာပြန်မယ်")
            self.source_lang_hint.configure(text=hint_text)
        if initial:
            return
        self.cfg["source_language"] = self._lang_code()
        save_config(self.cfg)
        source = self.source.get().strip()
        if source and Path(source).is_file():
            self.job_display.set(f"Job: {self._job_dir(Path(source)).name}")
        self._log(f"🌐 Source language: {name} → Myanmar"
                  + (" (Whisper multilingual model; a separate job folder is used)" if self._lang_code() != "en" else ""))

    def _browse_env(self) -> None:
        current = self.gemini_env.get().strip()
        initial = str(Path(current).parent) if current else str(ROOT_DIR.parent)
        p = filedialog.askopenfilename(title="Select .env containing GEMINI_API_KEY and/or ORYNX_API_KEY", initialdir=initial, filetypes=[("ENV", ".env"), ("All", "*.*")])
        if p:
            self.gemini_env.set(p)

    def _clear_batch(self) -> None:
        if self.batch_files:
            self.batch_files = []
            self.batch_folder = None
            self.start_btn.configure(text="START / RESUME")

    def _browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder of source videos")
        if not folder:
            return
        files = _list_batch_videos(Path(folder))
        if not files:
            messagebox.showinfo("Folder Batch", "ဒီ folder ထဲမှာ video ဖိုင် (mp4/mkv/mov/webm/avi) မတွေ့ပါ။")
            return
        # Load the first video so preview / editor overlays / plan state work as usual.
        self._load_source(str(files[0]))
        self.batch_folder = Path(folder)
        self.batch_files = files
        self.start_btn.configure(text=f"START BATCH ({len(files)})")
        self.job_display.set(f"Batch: {len(files)} video(s) · {Path(folder).name}")
        self._log(f"📂 Folder batch: {len(files)} video(s) in {folder}")
        for i, f in enumerate(files, 1):
            done = " (already done — will skip)" if _job_final_output(self._job_dir(f)) else ""
            self._log(f"   {i}. {f.name}{done}")
        self._log("ℹ️ Title / Logo / Blur settings on screen are applied to every video in the batch.")

    def _browse_source(self) -> None:
        p = filedialog.askopenfilename(title="Select source video", filetypes=[("Video", "*.mp4 *.mkv *.mov *.webm *.avi"), ("All", "*.*")])
        if p:
            self._clear_batch()
            self._load_source(p)

    def _load_source(self, p: str) -> None:
        if p:
            self.source.set(p)
            self.source_title.set(Path(p).stem)
            self.blur_boxes = []
            self.selected_blur = None
            job = self._job_dir(Path(p))
            # Resume editor layout too, not only transcript/TTS checkpoints.
            editor_file = job / "editor_overlays.json"
            if editor_file.is_file():
                try:
                    ed = json.loads(editor_file.read_text(encoding="utf-8"))
                    self.blur_boxes = [dict(x) for x in (ed.get("blur_boxes") or []) if isinstance(x, dict)]
                    self.title_text.set(str(ed.get("title_text") or ""))
                    self.title_pos = list(ed.get("title_position") or self.title_pos)
                    self.title_size.set(int(ed.get("title_font_size", self.title_size.get())))
                    # V19: legacy editor files had no logo_enabled flag. Do not let those
                    # cached paths silently resurrect a logo the user has disabled globally.
                    job_logo_enabled = bool(ed.get("logo_enabled", self.cfg.get("logo_enabled", False)))
                    self.logo_enabled.set(job_logo_enabled)
                    if job_logo_enabled and str(ed.get("logo_path") or "").strip():
                        self.logo_path.set(str(ed.get("logo_path")))
                    elif not job_logo_enabled:
                        self.logo_path.set("")
                    self.logo_pos = list(ed.get("logo_position") or self.logo_pos)
                    self.logo_width_frac.set(float(ed.get("logo_width_fraction", self.logo_width_frac.get())))
                    self.logo_opacity.set(float(ed.get("logo_opacity", self.logo_opacity.get())))
                    self.extra_text.set(str(ed.get("extra_text") or ""))
                    self.extra_text_pos = lm.normalize_pos(ed.get("extra_text_position"), self.extra_text_pos)
                    self._sync_extra_pos_sliders()
                    self.extra_text_size.set(int(ed.get("extra_text_font_size", self.extra_text_size.get())))
                    self.extra_text_opacity.set(float(ed.get("extra_text_opacity", self.extra_text_opacity.get())))
                except Exception as exc:
                    self._log(f"⚠️ Editor layout resume error: {exc}")
            self.job_display.set(f"Job: {job.name}")
            try:
                ffprobe = _tool_path(self.cfg, "ffprobe")
                self.preview_duration = preview_probe_duration(ffprobe, p)
                self.source_size = probe_video_size(ffprobe, p)
                self.preview_slider.configure(to=max(0.1, self.preview_duration))
                t = min(max(0.0, float(self.cfg.get("preview_seek_seconds", 1.0))), max(0.0, self.preview_duration-0.05))
                self.preview_time.set(t)
            except Exception as exc:
                self.preview_duration = 0.0
                self._log(f"⚠️ Preview duration error: {exc}")
            self._refresh_preview()

    def _save_cfg(self, settings: dict) -> None:
        self.cfg["gemini_env_path"] = settings["gemini_env_path"]
        self.cfg["source_language"] = settings.get("source_language", "en")
        self.cfg["refine_pass"] = bool(settings.get("refine", False))
        self.cfg["voice_mode"] = settings.get("voice_mode", "selected")
        self.cfg["audio_mix"] = dict(settings.get("audio_mix") or {})
        self.cfg["reuse_transcript_and_plan"] = settings["reuse_transcript_and_plan"]
        self.cfg["edge_tts_voice_mm"] = settings["edge_tts_voice"]
        self.cfg["tts_provider"] = settings.get("tts_provider", "edge")
        self.cfg["edge_tts_rate"] = settings["edge_tts_rate"]
        # Engine settings stay fixed/hidden; only user-facing production values persist.
        self.cfg["zoom_factor"] = settings["zoom_factor"]
        self.cfg["mirror_video"] = bool(settings["mirror_video"])
        self.cfg["voice_volume_percent"] = int(settings.get("voice_volume_percent", 100))
        self.cfg["short_pauses"] = bool(settings.get("short_pauses", True))
        self.cfg["freeze_rhythm"] = dict(settings.get("freeze_rhythm") or {})
        self.cfg["video_look"] = dict(settings.get("video_look") or {})
        self.cfg["subtitles"] = dict(settings.get("subtitles") or {})
        self.cfg["slow_motion"] = dict(settings.get("slow_motion") or {})
        self.cfg["auto_edit"] = dict(settings.get("auto_edit") or {})
        self.cfg["output_ratio"] = settings["output_ratio"]
        self.cfg["frame_fill"] = settings["frame_fill"]
        self.cfg["logo_enabled"] = bool(settings["overlays"].get("logo_enabled", False))
        self.cfg["logo_path"] = settings["overlays"].get("logo_path", "") if self.cfg["logo_enabled"] else ""
        self.cfg["logo_width_fraction"] = settings["overlays"].get("logo_width_fraction", 0.16)
        self.cfg["logo_opacity"] = settings["overlays"].get("logo_opacity", 0.65)
        self.cfg["logo_position"] = settings["overlays"].get("logo_position", [0.80, 0.06])
        self.cfg["title_position"] = settings["overlays"].get("title_position", [0.50, 0.12])
        self.cfg["title_font_size"] = settings["overlays"].get("title_font_size", 54)
        self.cfg["extra_text_position"] = settings["overlays"].get("extra_text_position", [0.50, 0.84])
        self.cfg["extra_text_font_size"] = settings["overlays"].get("extra_text_font_size", 42)
        self.cfg["extra_text_opacity"] = settings["overlays"].get("extra_text_opacity", 0.65)
        self.cfg["preview_seek_seconds"] = float(self.preview_time.get())
        save_config(self.cfg)

    def _capture_settings(self) -> dict:
        source = Path(self.source.get().strip()).resolve()
        env_text = str(self.gemini_env.get().strip() or self.cfg.get("gemini_env_path") or "")
        gemini_env = Path(env_text).resolve() if env_text else None
        voice = self.edge_voice.get().strip()
        if not source.is_file():
            raise ValueError("Source video ကိုရွေးပါ။")
        if gemini_env is not None and not gemini_env.is_file():
            raise ValueError("API keys .env path မမှန်ပါ။ API keys .env မှာ Browse နှိပ်ပြီး GEMINI_API_KEY (သို့) ORYNX_API_KEY ပါတဲ့ .env ဖိုင်ကိုရွေးပါ။")
        if voice not in EDGE_VOICES:
            raise ValueError("Edge TTS Voice ကိုရွေးပါ။")
        for tool in ("ffmpeg", "ffprobe"):
            if not Path(_tool_path(self.cfg, tool)).is_file():  # otherwise the job dies with "[WinError 2]"
                raise ValueError(
                    f"{tool}.exe မတွေ့ပါ — FFmpeg မသွင်းရသေးပါ။\n\n"
                    "INSTALL_REQUIREMENTS.bat ကို ပြန် run ပါ။ FFmpeg ကို ဒီ tool ရဲ့ ffmpeg folder ထဲ အလိုလို ထည့်ပေးပါမယ်။\n"
                    "(သို့) https://www.gyan.dev/ffmpeg/builds/ ကနေ download လုပ်ပြီး ffmpeg.exe နဲ့ ffprobe.exe ကို "
                    "RUN.bat ဘေးက ffmpeg folder ထဲ ထည့်ပါ။"
                )
        runtime_root = ROOT_DIR / "recap_runtime"
        for rel in ("services/whisper_service.py", "services/ai_service.py"):
            if not (runtime_root / rel).is_file():
                raise ValueError(f"Bundled Recap runtime file missing: {rel}")
        zoom = float(self.zoom_factor.get())
        if not (1.0 <= zoom <= 1.25):
            raise ValueError("Zoom must be between 1.00 and 1.25")
        logo_enabled = bool(self.logo_enabled.get())
        logo_path = self.logo_path.get().strip() if logo_enabled else ""
        overlays = {
            "blur_boxes": [dict(x) for x in self.blur_boxes],
            "blur_strength": int(self.cfg.get("overlay_blur_strength", 18)),
            "title_text": self.title_text.get().strip(),
            "title_position": [float(self.title_pos[0]), float(self.title_pos[1])],
            "title_font_size": int(self.title_size.get()),
            "title_font_path": str(self.cfg.get("title_font_path", r"C:\Windows\Fonts\mmrtext.ttf")),
            "logo_enabled": logo_enabled,
            "logo_path": logo_path,
            "logo_position": [float(self.logo_pos[0]), float(self.logo_pos[1])],
            "logo_width_fraction": float(self.logo_width_frac.get()),
            "logo_opacity": float(self.logo_opacity.get()),
            "extra_text": self.extra_text.get().strip(),
            "extra_text_position": [float(self.extra_text_pos[0]), float(self.extra_text_pos[1])],
            "extra_text_font_size": int(self.extra_text_size.get()),
            "extra_text_opacity": float(self.extra_text_opacity.get()),
        }
        if overlays["logo_path"] and not Path(overlays["logo_path"]).is_file():
            raise ValueError("Logo image path မမှန်ပါ။")
        return {
            "source": source,
            "source_language": self._lang_code(),
            "voice_mode": vg.normalize_voice_mode(self.voice_mode.get()),
            "audio_mix": amix.normalize_audio_mix({"original_percent": self.orig_percent.get(), "duck": bool(self.orig_duck.get())}),
            "asr_check": bool(self.asr_check.get()),
            "refine": bool(self.refine_pass.get()),
            "source_title": self.source_title.get().strip() or source.stem,
            "edge_tts_voice": voice,
            "edge_tts_rate": _format_edge_rate(self.edge_rate_percent.get()),
            "tts_provider": parse_tts_provider(self.tts_provider.get()),
            "edge_tts_pitch": str(self.cfg.get("edge_tts_pitch", "+0Hz")),
            "gemini_env_path": str(gemini_env) if gemini_env is not None else "",
            "voice": voice,
            # V0.3 behavior, hidden from UI.
            "max_video_speed": float(self.cfg.get("max_video_speed", 1.25)),
            "max_video_slow": float(self.cfg.get("max_video_slow", 1.35)),
            "smooth_freeze_fallback": bool(self.cfg.get("smooth_freeze_fallback", False)),
            "max_freeze_hold": float(self.cfg.get("max_freeze_hold", 0.75)),
            "mirror_video": bool(self.mirror_video.get()),
            "voice_volume_percent": int(self.voice_volume.get()),
            "short_pauses": bool(self.short_pauses.get()),
            "freeze_rhythm": normalize_freeze_rhythm({
                "enabled": bool(self.freeze_enabled.get()),
                "play_seconds": self.freeze_play.get().split()[0],
                "hold_seconds": self.freeze_hold.get().split()[0],
                "zoom_level": self.freeze_zoom.get(),
                "seed": self.cfg.get("freeze_rhythm", {}).get("seed") if isinstance(self.cfg.get("freeze_rhythm"), dict) else None,
            }),
            "subtitles": subs.normalize_subtitles({
                "enabled": bool(self.sub_enabled.get()),
                "size": self._first_number(self.sub_size.get(), 12),
                "style": self.sub_style.get(),
                "position": [float(self.sub_pos[0]), float(self.sub_pos[1])]}),
            "video_look": fx.normalize_look({
                "preset": self.look_preset.get(), "strength": self.look_strength.get(), "vignette": self.look_vignette.get()}),
            "slow_motion": fx.normalize_slow_motion({
                "enabled": bool(self.slow_enabled.get()),
                "slow_seconds": self._first_number(self.slow_len.get(), 5),
                "speed": self._first_number(self.slow_speed.get(), 0.5),
                "gap_seconds": self._first_number(self.slow_gap.get(), 30)}),
            "auto_edit": fx.normalize_auto_edit({
                "enabled": bool(self.auto_enabled.get()),
                "effects": [name for name, var in self.auto_effect_vars.items() if var.get()],
                "intensity": self.auto_intensity.get(),
                "slow_seconds": self._first_number(self.slow_len.get(), 5),
                "hold_seconds": self._first_number(self.freeze_hold.get(), 2),
                "seed": self.auto_seed.get().strip()}),
            "output_ratio": self.output_ratio.get() if self.output_ratio.get() in OUTPUT_RATIOS else "16:9",
            "frame_fill": self._fill_code() if self._fill_code() in FRAME_FILLS else "blur",
            "zoom_factor": zoom,
            "render_final_video": True,
            "reuse_transcript_and_plan": bool(self.cfg.get("reuse_transcript_and_plan", self.cfg.get("reuse_whisper_and_plan", True))),
            "overlays": overlays,
        }

    def _write_worker_cfg(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _run_child(self, script_name: str, cfg_path: Path, stage_name: str) -> dict:
        self.msgq.put(("stage", stage_name))
        self._log(f"\n{'=' * 64}\n{stage_name}\n{'=' * 64}")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        cmd = [sys.executable, "-u", str(ROOT_DIR / "app" / script_name), str(cfg_path)]
        self._log("▶ " + " ".join(f'"{x}"' if " " in x else x for x in cmd))
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        with self.proc_lock:
            self.current_proc = proc
        result: dict = {}
        reported_error = ""
        stopped_message = ""
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                if not line:
                    continue
                if line.startswith(EVENT_PREFIX):
                    try:
                        event = json.loads(line[len(EVENT_PREFIX):])
                    except Exception:
                        self._log(line)
                        continue
                    kind = event.get("kind")
                    if kind == "log":
                        self._log(str(event.get("text", "")))
                    elif kind == "progress":
                        self._set_progress(int(event.get("current", 0)), int(event.get("total", 0)), str(event.get("label", stage_name)))
                    elif kind == "result":
                        result = event
                    elif kind == "error":
                        reported_error = str(event.get("message", ""))
                    elif kind == "stopped":
                        stopped_message = str(event.get("message", "Stopped"))
                    continue
                self._log(line)
            code = proc.wait()
        finally:
            with self.proc_lock:
                if self.current_proc is proc:
                    self.current_proc = None

        if code == 10 or stopped_message:
            raise InterruptedError(stopped_message or "Stopped safely")
        if code != 0:
            if reported_error:
                raise RuntimeError(reported_error + f"\n\nChild exit code: {code}\nLog: {self.run_log_path}")
            raise RuntimeError(_native_crash_message(code) + f"\n\nLog: {self.run_log_path}")
        return result

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            settings = self._capture_settings()
            self._save_cfg(settings)
        except Exception as exc:
            messagebox.showerror("Setup Error", str(exc))
            return

        batch = [Path(p) for p in self.batch_files]
        sources: list[Path] = batch or [settings["source"]]

        self.stop_event.clear()
        self._running(True)
        self.logbox.delete("1.0", "end")
        self.progress["value"] = 0
        self.status.set("STARTING")
        self.stage.set("Preparing")
        self._log(f"📦 {APP_TITLE} | {SOURCE_LANG_NAMES[settings['source_language']]} → Myanmar · Narrator only · Edge TTS · V2 Smart Sync")
        self._log(f"📁 App root: {ROOT_DIR}")
        if batch:
            self._log(f"📂 Folder batch: {len(batch)} video(s) — one at a time")

        # Capture every Tk variable on the GUI thread; worker thread uses plain data only.
        ffmpeg = _tool_path(self.cfg, "ffmpeg")
        ffprobe = _tool_path(self.cfg, "ffprobe")
        cfg_values = {
            "translation_batch_max_items": int(self.cfg.get("translation_batch_max_items", 40)),
            "story_context_batch_max_items": int(self.cfg.get("story_context_batch_max_items", 80)),
            "context_overlap": int(self.cfg.get("context_overlap", 6)),
            "lookahead": int(self.cfg.get("lookahead", 6)),
            "translation_audit": bool(self.cfg.get("translation_audit", True)),
            "atomic_max_duration": float(self.cfg.get("atomic_max_duration", 5.6)),
            "atomic_target_duration": float(self.cfg.get("atomic_target_duration", 4.2)),
            "gemini_request_timeout_seconds": int(self.cfg.get("gemini_request_timeout_seconds", 120)),
            "gemini_text_model": str(self.cfg.get("gemini_text_model", "gemini-3.5-flash")),
        }

        def worker() -> None:
            if not batch:
                try:
                    final, job_dir = self._run_one_job(settings, sources[0], ffmpeg, ffprobe, cfg_values)
                    self.msgq.put(("done", f"ပြီးပါပြီ။\n\nOutput:\n{final}\n\nJob folder:\n{job_dir}"))
                except TranscriptPreview as exc:
                    self._log(str(exc))
                    self.msgq.put(("done", str(exc)))
                except InterruptedError as exc:
                    self._log(str(exc))
                    self.msgq.put(("error", str(exc)))
                except Exception as exc:
                    self._log(traceback.format_exc())
                    self.msgq.put(("error", str(exc)))
                return

            ok: list[str] = []
            skipped: list[str] = []
            failed: list[str] = []
            stopped = False
            for index, source in enumerate(sources, 1):
                if self.stop_event.is_set():
                    stopped = True
                    break
                label = f"[BATCH {index}/{len(sources)}] {source.name}"
                self.msgq.put(("job", f"Batch {index}/{len(sources)} · {source.name}"))
                if not source.is_file():
                    failed.append(f"{source.name} · file missing")
                    self._log(f"❌ {label} — file missing, skipped")
                    continue
                existing = _job_final_output(self._job_dir(source))
                if existing is not None:
                    skipped.append(source.name)
                    self._log(f"⏭️ {label} — already done ({existing.name}); job folder ဖျက်ရင် ပြန်လုပ်ပါမယ်")
                    continue
                self._log(f"\n{'#' * 64}\n▶ {label}\n{'#' * 64}")
                one = dict(settings)
                one["source"] = source
                one["source_title"] = source.stem
                try:
                    final, _job_dir = self._run_one_job(one, source, ffmpeg, ffprobe, cfg_values, batch_mode=True)
                    ok.append(source.name)
                    self._log(f"✅ {label} COMPLETE → {final}")
                except InterruptedError as exc:
                    self._log(str(exc))
                    stopped = True
                    failed.append(f"{source.name} · stopped")
                    break
                except Exception as exc:
                    self._log(traceback.format_exc())
                    first_line = (str(exc).splitlines() or [type(exc).__name__])[0]
                    failed.append(f"{source.name} · {first_line[:160]}")
                    self._log(f"❌ {label} FAILED — continuing with next video")

            lines = [
                f"Folder batch {'STOPPED' if stopped else 'DONE'}",
                f"OK={len(ok)} · SKIPPED={len(skipped)} · FAILED={len(failed)} / {len(sources)}",
            ]
            if failed:
                lines.append("")
                lines.append("Failed:")
                lines.extend(f"• {x}" for x in failed)
            summary = "\n".join(lines)
            self._log("\n" + summary)
            self.msgq.put(("job", f"Batch: {len(sources)} video(s) · OK {len(ok)} / FAILED {len(failed)}"))
            self.msgq.put(("error" if stopped else "done", summary))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _run_one_job(self, settings: dict, source: Path, ffmpeg: str, ffprobe: str,
                     cfg_values: dict, batch_mode: bool = False) -> tuple[str, Path]:
        """Planner + Edge TTS/Smart Sync for one video. Runs on the worker thread (no Tk calls)."""
        job_dir = self._job_dir(source)
        job_dir.mkdir(parents=True, exist_ok=True)
        self.current_job = job_dir
        self.run_log_path = job_dir / "run.log"
        try:
            self.run_log_path.write_text("", encoding="utf-8")
        except Exception:
            pass
        stop_file = job_dir / ".stop_requested"
        if not self.stop_event.is_set():
            stop_file.unlink(missing_ok=True)
        self.msgq.put(("job", f"Batch · {job_dir.name}" if batch_mode else f"Job: {job_dir.name}"))
        try:
            (job_dir / "editor_overlays.json").write_text(json.dumps(settings["overlays"], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        self._log(f"📁 Job folder: {job_dir}")

        planner_cfg = job_dir / "_planner_worker.json"
        planner_data = {
            "source_path": str(source),
            "source_title": settings["source_title"],
            "job_dir": str(job_dir),
            "runtime_root": str(ROOT_DIR / "recap_runtime"),
            "gemini_env_path": settings["gemini_env_path"],
            "ffprobe_path": ffprobe,
            "reuse": settings["reuse_transcript_and_plan"],
            "stop_file": str(stop_file),
            "source_language": settings["source_language"],
            # Chinese needs a multilingual Whisper model; "small" (~480 MB). "medium" is more accurate (~1.5 GB):
            # put "whisper_model_zh": "medium" in config.json. English keeps the English-only small.en.
            "whisper_model": self._whisper_model_for(settings["source_language"]),
            "asr_preview_seconds": ASR_CHECK_SECONDS if (settings.get("asr_check") and not batch_mode) else 0,
            "refine": bool(settings.get("refine", False)),
        }
        for key in (
            "translation_batch_max_items", "story_context_batch_max_items", "context_overlap",
            "lookahead", "translation_audit", "atomic_max_duration", "atomic_target_duration",
            "gemini_request_timeout_seconds", "gemini_text_model",
        ):
            planner_data[key] = cfg_values[key]
        self._write_worker_cfg(planner_cfg, planner_data)
        planner_result = self._run_child(
            "planner_worker.py", planner_cfg,
            "STEP 1 — Transcript + Context + Timestamp Translation",
        )
        if planner_result.get("preview"):
            raise TranscriptPreview(str(planner_result.get("message") or "Transcript check finished"))
        plan_path = str(planner_result.get("plan_path") or (job_dir / "smart_sync_plan.json"))

        plan_data = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        segment_count = len(normalize_segments(plan_data))
        self._log(f"🧩 Final plan: {segment_count} segments → {TTS_PROVIDERS[settings['tts_provider']]}")

        if stop_file.exists():
            raise InterruptedError("Stopped after planner stage. START / RESUME ပြန်နှိပ်လို့ရပါတယ်။")

        self._log("✅ Transcript/translation complete.")
        if settings["tts_provider"] == "mms":
            self._log(f"🎙️ Meta MMS (offline) — fallback Edge voice={settings['voice']}")
        else:
            self._log(f"🎙️ Edge TTS — voice={settings['voice']}")
        time.sleep(0.2)

        render_cfg = job_dir / "_render_worker.json"
        self._write_worker_cfg(render_cfg, {
            "job_dir": str(job_dir),
            "source_path": str(source),
            "plan_path": plan_path,
            "voice": settings["voice"],
            "edge_tts_rate": settings["edge_tts_rate"],
            "edge_tts_pitch": settings["edge_tts_pitch"],
            "tts_provider": settings["tts_provider"],
            "ffmpeg_path": ffmpeg,
            "ffprobe_path": ffprobe,
            "max_video_speed": settings["max_video_speed"],
            "max_video_slow": settings["max_video_slow"],
            "smooth_freeze_fallback": settings["smooth_freeze_fallback"],
            "max_freeze_hold": settings["max_freeze_hold"],
            "mirror_video": settings["mirror_video"],
            "zoom_factor": settings["zoom_factor"],
            "render_final_video": settings["render_final_video"],
            "overlays": settings["overlays"],
            "voice_volume_percent": settings["voice_volume_percent"],
            "short_pauses": bool(settings.get("short_pauses", True)),
            "freeze_rhythm": settings.get("freeze_rhythm") or {},
            "video_look": settings.get("video_look") or {},
            "subtitles": settings.get("subtitles") or {},
            "voice_mode": settings.get("voice_mode", "selected"),
            "audio_mix": settings.get("audio_mix") or {},
            "slow_motion": settings.get("slow_motion") or {},
            "auto_edit": settings.get("auto_edit") or {},
            "output_ratio": settings.get("output_ratio", "16:9"),
            "frame_fill": settings.get("frame_fill", "blur"),
            "gemini_env_path": settings.get("gemini_env_path", ""),
            "stop_file": str(stop_file),
        })
        result = self._run_child("render_worker.py", render_cfg, "STEP 2 — Edge TTS + Smart Sync").get("result") or {}
        final = result.get("final") or result.get("audio") or str(job_dir)
        return str(final), job_dir

    def _stop(self) -> None:
        self.stop_event.set()
        if self.current_job:
            try:
                (self.current_job / ".stop_requested").write_text("stop", encoding="utf-8")
            except Exception:
                pass
        self.status.set("STOP REQUESTED")
        self._log("⏹️ Stop requested — current safe boundary ရောက်တာနဲ့ရပ်မယ်။ Resume data မဖျက်ပါ။")

    def _running(self, yes: bool) -> None:
        self.start_btn.configure(state="disabled" if yes else "normal")
        self.stop_btn.configure(state="normal" if yes else "disabled")

    def _open_text_editor(self, segment: int | None = None) -> None:
        """Edit Text: read the source line next to its Burmese narration and fix the Burmese by hand."""
        source_text = self.source.get().strip()
        job = self.current_job or (self._job_dir(Path(source_text)) if source_text else None)
        if job is None or not (job / "smart_sync_plan.json").is_file():
            messagebox.showinfo("Edit Text", "ဒီ video အတွက် translation plan မရှိသေးပါ။ START နှိပ်ပြီး translation ပြီးမှ ပြင်လို့ရပါမယ်။")
            return
        existing = getattr(self, "_text_editor", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            if segment:
                existing._show(max(1, min(int(segment), len(existing.segments))))
            return
        self._text_editor = NarrationEditor(
            self, job, start_segment=segment or 1, on_saved=lambda n, _t: self._narration_saved(n),
            colors={"bg": BG, "panel": PANEL, "fg": FG, "muted": MUTED},
        )

    def _narration_saved(self, segment: int) -> None:
        self._log(f"✏️ Line {segment} saved — START / RESUME gives a new voice only to the edited line(s).")

    def _open_output(self) -> None:
        if not self.source.get().strip():
            messagebox.showinfo("Output", "Source video မရွေးရသေးပါ။")
            return
        job = self._job_dir(Path(self.source.get().strip()))
        if not job.exists():
            messagebox.showinfo("Output", "Job folder မရှိသေးပါ။")
            return
        os.startfile(str(job))


if __name__ == "__main__":
    App().mainloop()
