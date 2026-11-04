"""Burned-in Myanmar subtitles (version 2.1 feature, shipped in 2.0 beta).

The subtitle text is the Burmese narration itself, timed by the narration audio: a line appears when the voice starts
it and goes when the voice finishes. A long narration line is split into several short subtitles (cut at ။ ၊ . ? ! and
spaces) that share the line's time in proportion to their length.

Each subtitle is a transparent PNG of the SAME size (one strip across the bottom of the picture), drawn by Chromium so
Myanmar is shaped correctly (the same renderer as the Title). The PNGs and their times go into a concat list that
core.apply_production_overlays lays over the video in the same pass as the Title / Logo / Blur boxes.

Size 9 / 12 / 14 are relative sizes: 4 px per unit on a 1080-px canvas (9 -> 36 px, 12 -> 48 px, 14 -> 56 px), scaled
with the canvas (the shorter side), so a 9:16 video and a 16:9 video look alike.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Callable

import layout_math as lm

LogFn = Callable[[str], None]

SUB_SIZES = (9, 12, 14)
SUB_PX_PER_UNIT = 4.0
SUB_STYLES = {                         # label in the app -> style key used by the renderer
    "Yellow · black stroke": "yellow_black",
    "White · black stroke": "white_black",
    "White on black box": "white_box",
    "Black on yellow box": "black_yellow",
}
SUB_STYLE_LABELS = {key: label for label, key in SUB_STYLES.items()}
SUB_LINES = 2                          # a subtitle shows at most two lines
TAIL_SECONDS = 2.0                     # transparent tail after the last subtitle (the video decides when the output ends)
MIN_CUE_SECONDS = 0.35
TEXT_WIDTH_FRACTION = 0.86             # widest a subtitle gets (share of the picture width), at the centre


def normalize_subtitles(cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(cfg or {})
    try:
        size = int(round(float(cfg.get("size", 12))))
    except Exception:
        size = 12
    size = min(SUB_SIZES, key=lambda s: abs(s - size))
    style = str(cfg.get("style") or "yellow_black").strip()
    style = SUB_STYLES.get(style, style)
    position = lm.clamp_sub_pos(lm.normalize_pos(cfg.get("position"), lm.DEFAULT_SUB_POS), 0.0, 0.0)
    return {"enabled": bool(cfg.get("enabled", False)), "size": size,
            "style": style if style in SUB_STYLE_LABELS else "yellow_black", "position": position}


def subtitle_px(size: int, canvas_w: int, canvas_h: int) -> int:
    return max(14, int(round(size * SUB_PX_PER_UNIT * min(int(canvas_w), int(canvas_h)) / 1080.0)))


def bottom_margin(canvas_h: int) -> int:
    """Pixels between the text and the strip's bottom edge (the strip is a full-width PNG, text at its bottom centre)."""
    return max(12, int(round(int(canvas_h) * 0.055)))


def strip_geometry(px: int, canvas_w: int, canvas_h: int) -> tuple[int, int, int]:
    """(strip height, bottom margin, strip width): room for two lines, their padding and the stroke."""
    bottom = bottom_margin(canvas_h)
    height = int(round(px * 1.35 * SUB_LINES + px * 0.9)) + bottom
    return height, bottom, int(canvas_w)


def text_half_height(size: int, canvas_w: int, canvas_h: int) -> float:
    """Half the height of a two-line subtitle as a fraction of the picture (what the position is kept clear of)."""
    px = subtitle_px(size, canvas_w, canvas_h)
    strip_h, bottom, _w = strip_geometry(px, canvas_w, canvas_h)
    return (strip_h - bottom) / float(canvas_h) / 2.0


def subtitle_layout(cfg: dict[str, Any] | None, canvas_w: int, canvas_h: int) -> tuple[float, float, float]:
    """(x, y, width fraction) the render uses: the bottom centre of the subtitle as fractions of the picture, kept inside
    the picture, and how wide the text may be there (narrower near the sides so it never leaves the picture)."""
    cfg = normalize_subtitles(cfg)
    x, y = lm.clamp_sub_pos(cfg["position"], text_half_height(cfg["size"], canvas_w, canvas_h), 0.0)
    return x, y, min(TEXT_WIDTH_FRACTION, 2.0 * min(x, 1.0 - x) - 0.04)


# ------------------------------------------------------------------------------------------------ cue splitting
def est_em(text: str) -> float:
    """Rough width of `text` in em (enough to decide where to cut; Chromium still shrinks a line that does not fit)."""
    total = 0.0
    for ch in text:
        cat = unicodedata.category(ch)
        if cat == "Mn":
            continue
        if ch.isspace():
            total += 0.28
        elif cat == "Mc":
            total += 0.30
        elif "\u1000" <= ch <= "\u109f":
            total += 0.66
        elif ch.isascii() and ch.isalnum():
            total += 0.55
        elif cat.startswith("P"):
            total += 0.30
        else:
            total += 0.9
    return total


_SENTENCE = re.compile(r"[^။၊.!?…]+[။၊.!?…]*\s*")


def _pieces(text: str, max_em: float) -> list[str]:
    parts = [m.group(0).strip() for m in _SENTENCE.finditer(text) if m.group(0).strip()]
    out: list[str] = []
    for part in parts:                                    # a piece that alone is too wide: cut at spaces, then anywhere
        if est_em(part) <= max_em:
            out.append(part)
            continue
        words = part.split(" ")
        cur = ""
        for w in words:
            cand = (cur + " " + w).strip()
            if cur and est_em(cand) > max_em:
                out.append(cur)
                cur = w
            else:
                cur = cand
            while est_em(cur) > max_em and len(cur) > 1:    # no spaces at all (Burmese): cut at the em budget
                cut, acc = 0, 0.0
                for i, ch in enumerate(cur):
                    acc += est_em(ch)
                    if acc > max_em and i > 0 and unicodedata.category(ch) not in ("Mn", "Mc"):
                        cut = i
                        break
                if not cut:
                    break
                out.append(cur[:cut])
                cur = cur[cut:]
        if cur:
            out.append(cur)
    return out


def split_cues(text: str, start: float, end: float, *, max_em: float) -> list[dict[str, Any]]:
    """One narration line -> subtitles that each fit `max_em`, sharing [start, end] in proportion to their length."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text or end <= start:
        return []
    pieces = _pieces(text, max_em)
    merged: list[str] = []
    for piece in pieces:                                  # join short neighbours back while they still fit
        if merged and est_em(merged[-1] + " " + piece) <= max_em:
            merged[-1] += " " + piece
        else:
            merged.append(piece)
    # a cue that would be on screen for less than MIN_CUE_SECONDS joins its neighbour
    span = end - start
    weights = [max(0.5, est_em(m)) for m in merged]
    while len(merged) > 1 and min(w / sum(weights) * span for w in weights) < MIN_CUE_SECONDS:
        i = min(range(len(weights)), key=lambda k: weights[k])
        j = i - 1 if i > 0 else i + 1
        a, b = sorted((i, j))
        merged[a:b + 1] = [merged[a] + " " + merged[b]]
        weights[a:b + 1] = [weights[a] + weights[b]]
    total = sum(weights)
    cues, t = [], start
    for i, (m, w) in enumerate(zip(merged, weights)):
        d = span * w / total
        cues.append({"text": m, "start": round(t, 3), "end": round(end if i == len(merged) - 1 else t + d, 3)})
        t += d
    return cues


def build_cues(timeline: list[dict[str, Any]], *, canvas_w: int, px: int,
               width_frac: float = TEXT_WIDTH_FRACTION) -> list[dict[str, Any]]:
    usable = canvas_w * width_frac - px * 1.0             # the text box inside the strip (padding)
    max_em = SUB_LINES * (usable / px) * 0.9
    cues: list[dict[str, Any]] = []
    for item in sorted(timeline, key=lambda x: float(x.get("start", 0))):
        cues += split_cues(item.get("text", ""), float(item["start"]), float(item["end"]), max_em=max_em)
    return cues


# ------------------------------------------------------------------------------------------------ concat list
def write_concat_list(cues: list[dict[str, Any]], png_of: Callable[[str], Path], gap_png: Path, total_seconds: float,
                      list_path: Path) -> Path:
    """concat-demuxer list: a transparent PNG while nobody speaks, a subtitle PNG while a cue is shown."""
    def line(path: Path) -> str:
        return "file '" + path.resolve().as_posix().replace("'", "'\\''") + "'"
    rows: list[tuple[Path, float]] = []
    t = 0.0
    for cue in cues:
        s, e = max(t, float(cue["start"])), max(float(cue["end"]), t)
        if s > t + 0.001:
            rows.append((gap_png, s - t))
        if e > s:
            rows.append((png_of(cue["text"]), e - s))
            t = e
    rows.append((gap_png, max(0.5, total_seconds - t) + TAIL_SECONDS))
    out: list[str] = []
    for path, dur in rows:
        out += [line(path), f"duration {dur:.3f}"]
    out.append(line(rows[-1][0]))                          # the demuxer ignores the last duration: repeat the file
    list_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return list_path


def prepare_subtitles(
    timeline: list[dict[str, Any]],
    total_seconds: float,
    canvas: tuple[int, int],
    settings: dict[str, Any],
    work_dir: Path,
    *,
    log: LogFn = lambda _m: None,
    renderer: Callable[..., list[Path]] | None = None,
) -> Path | None:
    """Make the subtitle PNGs + concat list for this video. Returns the list path (None when disabled / nothing to show).

    Finished PNGs are kept: START / RESUME with the same text, style and size does not render them again."""
    cfg = normalize_subtitles(settings)
    if not cfg["enabled"]:
        return None
    cw, ch = int(canvas[0]), int(canvas[1])
    px = subtitle_px(cfg["size"], cw, ch)
    _x, _y, width_frac = subtitle_layout(cfg, cw, ch)       # narrower text when the subtitle is moved towards a side
    cues = build_cues(timeline, canvas_w=cw, px=px, width_frac=width_frac)
    if not cues:
        log("ℹ️ Subtitles: no narration text to show")
        return None
    strip_h, bottom, strip_w = strip_geometry(px, cw, ch)
    texts = list(dict.fromkeys(c["text"] for c in cues))
    sig = hashlib.sha1(json.dumps([texts, cfg["style"], px, cw, ch, round(width_frac, 3)],
                                  ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    run_dir = work_dir / f"subtitles_{sig}"
    for old in work_dir.glob("subtitles_*"):
        if old.is_dir() and old != run_dir:
            shutil.rmtree(old, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"💬 Subtitles: {len(cues)} line(s) | size {cfg['size']} ({px}px) | {SUB_STYLE_LABELS[cfg['style']]}")
    done = run_dir / "pngs.json"
    pngs: list[Path] = []
    if done.is_file():
        try:
            saved = json.loads(done.read_text(encoding="utf-8"))
            pngs = [run_dir / name for name in saved["files"]]
            if saved.get("texts") != texts or not all(p.is_file() and p.stat().st_size > 100 for p in pngs):
                pngs = []
        except Exception:
            pngs = []
    if not pngs:
        if renderer is None:
            import sys
            root = Path(__file__).resolve().parents[1]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from services.text_overlay_service import make_subtitle_pngs as renderer     # lazy: needs Playwright
        pngs = renderer(texts, run_dir, {"width": strip_w, "height": strip_h, "font_size": px, "style": cfg["style"],
                                         "bottom_margin": bottom, "max_lines": SUB_LINES,
                                         "max_width_pct": round(width_frac * 100.0, 2)})
        done.write_text(json.dumps({"texts": texts, "files": [p.name for p in pngs]}, ensure_ascii=False), encoding="utf-8")
    lookup = dict(zip(texts, pngs))
    gap = run_dir / "gap.png"
    from PIL import Image
    Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0)).save(gap)
    return write_concat_list(cues, lambda t: lookup[t], gap, total_seconds, run_dir / "subtitles.txt")
