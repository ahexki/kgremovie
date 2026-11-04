"""Version 2.0 picture effects for the Smart Sync video (picture only: the audio and the video length never change).

  * Video look   - one colour filter over the whole video (strength %) and a vignette (strength %).
  * Slow motion  - play G seconds, then S seconds (5 or 10) in slow motion, and so on.
  * Auto edit    - the video is cut into random sections; each section gets a random mix of the effects you allow:
                   flip, zoom-in, freeze frame, vignette, slow motion. The same seed gives the same edit.

Like Freeze rhythm, a slow / freeze part REPLACES the picture of its time window (it does not pause the video and
shift everything after it), so the narration stays in step. This module runs after Smart Sync and before the Title /
Logo / Blur overlays.

The planners are pure functions (testable without ffmpeg); apply_* render with ffmpeg and keep their finished parts, so
STOP / RESUME continues where it stopped.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

LogFn = Callable[[str], None]
FPS = 30                                # every Smart Sync part is locked to 30 fps

# ------------------------------------------------------------------------------------------------ look
LOOK_PRESETS = ("Off", "Warm", "Cool", "Cinematic", "Vivid", "Vintage", "Black & White", "Matte")


def vignette_angle(percent: float) -> float:
    """Vignette strength % -> ffmpeg angle. (ffmpeg: the BIGGER the angle, the darker the corners.)
    Measured on a flat picture: 25% -> corners at ~75% brightness, 50% -> ~54%, 75% -> ~33%, 100% -> ~15%."""
    p = max(0.0, min(100.0, float(percent))) / 100.0
    return 0.18 + 0.62 * (p ** 0.9)


def normalize_look(cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(cfg or {})
    preset = str(cfg.get("preset") or "Off").strip()
    preset = next((p for p in LOOK_PRESETS if p.lower() == preset.lower()), "Off")
    def pct(value: Any, default: float) -> int:
        try:
            return int(round(max(0.0, min(100.0, float(value)))))
        except Exception:
            return int(default)
    return {"preset": preset, "strength": pct(cfg.get("strength", 60), 60), "vignette": pct(cfg.get("vignette", 0), 0)}


def look_enabled(cfg: dict[str, Any]) -> bool:
    cfg = normalize_look(cfg)
    return (cfg["preset"] != "Off" and cfg["strength"] > 0) or cfg["vignette"] > 0


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def look_filter(preset: str, strength_percent: float) -> str:
    """ffmpeg filter text of one colour preset at a strength of 0-100 % ('' = nothing to do)."""
    s = max(0.0, min(1.0, float(strength_percent) / 100.0))
    if preset == "Off" or s <= 0:
        return ""
    f = lambda v: f"{v:.3f}"
    if preset == "Warm":
        return f"colorbalance=rm={f(0.10 * s)}:bm={f(-0.10 * s)}:rh={f(0.07 * s)}:bh={f(-0.08 * s)},eq=saturation={f(1 + 0.06 * s)}"
    if preset == "Cool":
        return f"colorbalance=rm={f(-0.10 * s)}:bm={f(0.10 * s)}:rh={f(-0.06 * s)}:bh={f(0.08 * s)},eq=saturation={f(1 + 0.04 * s)}"
    if preset == "Cinematic":      # teal shadows, warm highlights, a little more contrast
        return (f"colorbalance=rs={f(-0.06 * s)}:bs={f(0.08 * s)}:rh={f(0.08 * s)}:bh={f(-0.07 * s)},"
                f"eq=contrast={f(1 + 0.10 * s)}:saturation={f(1 + 0.08 * s)}")
    if preset == "Vivid":
        return f"eq=saturation={f(1 + 0.5 * s)}:contrast={f(1 + 0.08 * s)}"
    if preset == "Vintage":        # identity -> a faded sepia mix
        sepia = ((0.62, 0.32, 0.06), (0.28, 0.62, 0.10), (0.17, 0.34, 0.35))
        ident = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
        names = (("rr", "rg", "rb"), ("gr", "gg", "gb"), ("br", "bg", "bb"))
        parts = [f"{names[r][c]}={f(_lerp(ident[r][c], sepia[r][c], s))}" for r in range(3) for c in range(3)]
        return "colorchannelmixer=" + ":".join(parts) + f",eq=contrast={f(1 - 0.05 * s)}"
    if preset == "Black & White":
        return f"hue=s={f(1 - s)},eq=contrast={f(1 + 0.08 * s)}"
    if preset == "Matte":
        return f"eq=contrast={f(1 - 0.08 * s)}:brightness={f(0.03 * s)}:saturation={f(1 - 0.10 * s)}"
    return ""


def look_vf(cfg: dict[str, Any]) -> str:
    cfg = normalize_look(cfg)
    chain = [x for x in (look_filter(cfg["preset"], cfg["strength"]),
                         f"vignette=angle={vignette_angle(cfg['vignette']):.4f}" if cfg["vignette"] > 0 else "") if x]
    return ",".join(chain)


# ------------------------------------------------------------------------------------------------ slow motion
SLOW_LENGTHS = (5, 10)
SLOW_GAPS = (10, 20, 30, 60)
SLOW_SPEEDS = (0.25, 0.35, 0.5, 0.7)          # 0.25 = four times slower


def _pick(value: Any, choices: tuple, default: Any) -> Any:
    try:
        number = float(value)
    except Exception:
        return default
    return min(choices, key=lambda c: abs(c - number))


def normalize_slow_motion(cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(cfg or {})
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "slow_seconds": int(_pick(cfg.get("slow_seconds", 5), SLOW_LENGTHS, 5)),
        "gap_seconds": int(_pick(cfg.get("gap_seconds", 30), SLOW_GAPS, 30)),
        "speed": float(_pick(cfg.get("speed", 0.5), SLOW_SPEEDS, 0.5)),
    }


def plan_slow_motion(total_frames: int, *, gap_seconds: float, slow_seconds: float, speed: float = 0.5,
                     fps: int = FPS) -> list[dict[str, Any]]:
    """play `gap` s, slow `slow` s, play, slow ... The parts add up to exactly `total_frames`."""
    total = int(total_frames)
    gap_n = max(1, int(round(gap_seconds * fps)))
    slow_n = max(1, int(round(slow_seconds * fps)))
    parts: list[dict[str, Any]] = []
    pos = 0
    while pos < total:
        n = min(gap_n, total - pos)
        if total - pos - n < fps:
            n = total - pos
        parts.append({"kind": "play", "start": pos, "frames": n})
        pos += n
        if pos >= total:
            break
        m = min(slow_n, total - pos)
        if total - pos - m < fps:
            m = total - pos
        parts.append({"kind": "slow", "start": pos, "frames": m, "speed": float(speed)})
        pos += m
    return parts


# ------------------------------------------------------------------------------------------------ auto edit
AUTO_EFFECTS = ("flip", "zoom", "freeze", "vignette", "slow")
AUTO_INTENSITY = {"Low": (0.35, 1), "Medium": (0.55, 2), "High": (0.80, 3)}     # (chance a section is edited, max effects)
AUTO_HOLD_CHOICES = (2, 4)


def normalize_auto_edit(cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(cfg or {})
    raw = cfg.get("effects")
    effects = [e for e in AUTO_EFFECTS if e in (raw if isinstance(raw, (list, tuple, set)) else AUTO_EFFECTS)]
    intensity = str(cfg.get("intensity") or "Medium").strip().title()
    seed = cfg.get("seed")
    try:
        seed = int(seed) if seed not in (None, "") else None
    except Exception:
        seed = None
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "effects": effects,
        "intensity": intensity if intensity in AUTO_INTENSITY else "Medium",
        "slow_seconds": int(_pick(cfg.get("slow_seconds", 5), SLOW_LENGTHS, 5)),
        "hold_seconds": int(_pick(cfg.get("hold_seconds", 2), AUTO_HOLD_CHOICES, 2)),
        "seed": seed,
    }


def plan_auto_edit(total_frames: int, *, effects: list[str], intensity: str = "Medium", slow_seconds: float = 5,
                   hold_seconds: float = 2, seed: int = 0, fps: int = FPS) -> list[dict[str, Any]]:
    """Random sections of 6-14 s; each is edited with a random mix of `effects`. Repeatable for one seed.

    play / slow part: {"kind", "start", "frames", "flip", "zoom": {"end","fx","fy"} | None, "vignette": 0-100, ["speed"]}
    hold part       : the same keys plus "at" (the source frame that is frozen). The parts add up to `total_frames`.
    """
    total = int(total_frames)
    rng = random.Random(int(seed))
    allowed = [e for e in AUTO_EFFECTS if e in set(effects)]
    chance, max_stack = AUTO_INTENSITY.get(intensity, AUTO_INTENSITY["Medium"])
    slow_n, hold_n = max(1, int(round(slow_seconds * fps))), max(1, int(round(hold_seconds * fps)))
    parts: list[dict[str, Any]] = []
    pos = 0

    def look(chosen: list[str]) -> dict[str, Any]:
        zoom = None
        if "zoom" in chosen:
            zoom = {"end": round(rng.uniform(1.08, 1.22), 3), "fx": round(rng.uniform(0.30, 0.70), 3),
                    "fy": round(rng.uniform(0.30, 0.70), 3)}
        return {"flip": "flip" in chosen, "zoom": zoom,
                "vignette": rng.choice([30, 45, 60]) if "vignette" in chosen else 0}

    while pos < total:
        chosen: list[str] = []
        if allowed and rng.random() < chance:
            chosen = rng.sample(allowed, k=min(rng.randint(1, max_stack), len(allowed)))
        length = int(rng.uniform(6.0, 14.0) * fps)
        if "slow" in chosen:
            length = slow_n
        n = min(length, total - pos)
        if total - pos - n < fps:                              # a tail under 1 s joins this section
            n = total - pos
        part = {"kind": "slow" if "slow" in chosen else "play", "start": pos, "frames": n, **look(chosen)}
        if "slow" in chosen:
            part["speed"] = rng.choice([0.35, 0.5, 0.6, 0.7])
        parts.append(part)
        pos += n
        if "freeze" in chosen and pos < total:
            h = min(hold_n, total - pos)
            if total - pos - h < fps:
                h = total - pos
            hold = {"kind": "hold", "start": pos, "at": pos - 1, "frames": h, **look(chosen)}
            if hold["zoom"] is None:                           # a freeze always breathes a little
                hold["zoom"] = {"end": round(rng.uniform(1.04, 1.10), 3), "fx": round(rng.uniform(0.35, 0.65), 3),
                                "fy": round(rng.uniform(0.35, 0.65), 3)}
            parts.append(hold)
            pos += h
    return parts


# ------------------------------------------------------------------------------------------------ rendering
def _run(cmd: list[str], what: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"{what} failed:\n{(result.stderr or '')[-3000:]}")


def probe_frames(ffprobe: str, path: Path) -> int:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    for token in (result.stdout or "").split():
        if token.isdigit() and int(token) > 0:
            return int(token)
    dur = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                          str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return int(round(float((dur.stdout or "0").strip() or 0) * FPS))


def probe_size(ffprobe: str, path: Path) -> tuple[int, int]:
    result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                             "-of", "csv=p=0:s=x", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    w, h = (result.stdout or "").strip().split("x")[:2]
    return int(w), int(h)


def part_vf(part: dict[str, Any], width: int, height: int) -> str:
    """The ffmpeg filter chain of one part: slow motion -> flip -> zoom-in -> vignette."""
    chain: list[str] = []
    if part["kind"] == "slow":
        chain.append(f"setpts=PTS/{float(part['speed']):.4f},minterpolate=fps={FPS}:mi_mode=blend")
    if part.get("flip"):
        chain.append("hflip")
    zoom = part.get("zoom")
    if zoom and zoom["end"] > 1.0005 and part["frames"] >= 2:
        last = max(1, part["frames"] - 1)
        p = f"(on/{last})"
        z = f"1+({zoom['end'] - 1.0:.5f})*(3*pow({p},2)-2*pow({p},3))"          # eased push-in
        # upscaled 2x first: zoompan moves in whole pixels, which would make a slow push-in jitter
        chain.append(f"scale={width * 2}:{height * 2}:flags=bilinear,"
                     f"zoompan=z='{z}':x='(iw-iw/zoom)*{zoom['fx']:.3f}':y='(ih-ih/zoom)*{zoom['fy']:.3f}':d=1:s={width}x{height}:fps={FPS}")
    if part.get("vignette", 0) > 0:
        chain.append(f"vignette=angle={vignette_angle(part['vignette']):.4f}")
    chain.append("setsar=1")
    chain.append("format=yuv420p")
    return ",".join(chain)


def _concat(ffmpeg: str, clips: list[Path], output: Path, work_dir: Path) -> None:
    listing = work_dir / "parts.txt"
    listing.write_text("".join("file '" + c.resolve().as_posix().replace("'", "'\\''") + "'\n" for c in clips), encoding="utf-8")
    _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
          "-c", "copy", "-movflags", "+faststart", str(output)], "FX concat")


def _render_parts_once(ffmpeg: str, input_video: Path, output_video: Path, parts: list[dict[str, Any]], size: tuple[int, int],
                       encoder: str, work_dir: Path, should_stop: Callable[[], bool],
                       progress: Callable[[int, int, str], None] | None, label: str) -> None:
    from core import _encoder_args           # lazy: core imports this module
    width, height = size
    work_dir.mkdir(parents=True, exist_ok=True)
    enc = _encoder_args(encoder) + ["-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-movflags", "+faststart"]
    clips: list[Path] = []
    for i, part in enumerate(parts, 1):
        if should_stop():
            raise InterruptedError(f"STOP requested — {label} parts are kept; START / RESUME continues.")
        clip = work_dir / f"part_{i:05d}_{part['kind']}.mp4"
        clips.append(clip)
        if clip.is_file() and clip.stat().st_size > 1000:
            if progress:
                progress(i, len(parts), f"{label} {i}/{len(parts)}")
            continue
        tmp = clip.with_suffix(".tmp.mp4")
        vf = part_vf(part, width, height)
        if part["kind"] == "hold":
            png = work_dir / f"hold_{i:05d}.png"
            seek = max(0.0, (part["at"] - 0.25) / FPS)
            _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{seek:.6f}", "-i", str(input_video),
                  "-frames:v", "1", str(png)], f"{label} frame grab")
            _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(png),
                  "-vf", vf, "-frames:v", str(part["frames"]), *enc, str(tmp)], f"{label} hold part")
            png.unlink(missing_ok=True)
        else:
            seek = max(0.0, (part["start"] - 0.25) / FPS)         # a quarter frame early: frame-exact cut
            _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{seek:.6f}", "-i", str(input_video),
                  "-vf", vf, "-frames:v", str(part["frames"]), *enc, str(tmp)], f"{label} {part['kind']} part")
        tmp.replace(clip)
        if progress:
            progress(i, len(parts), f"{label} {i}/{len(parts)}")
    _concat(ffmpeg, clips, output_video, work_dir)


def _render_parts(ffmpeg: str, ffprobe: str, input_video: Path, output_video: Path, parts: list[dict[str, Any]],
                  encoder: str, work_dir: Path, tag: str, signature: Any, log: LogFn,
                  should_stop: Callable[[], bool], progress: Callable[[int, int, str], None] | None, label: str) -> Path:
    size = probe_size(ffprobe, input_video)
    total = probe_frames(ffprobe, input_video)
    sig = hashlib.sha1(json.dumps([signature, total, size, input_video.stat().st_size, encoder], sort_keys=True,
                                  default=str).encode("utf-8")).hexdigest()[:10]
    run_dir = work_dir / f"fx_{tag}_{sig}"
    for old in work_dir.glob(f"fx_{tag}_*"):                      # parts of other settings / other pictures
        if old.is_dir() and old != run_dir:
            shutil.rmtree(old, ignore_errors=True)
    try:
        _render_parts_once(ffmpeg, input_video, output_video, parts, size, encoder, run_dir, should_stop, progress, label)
    except RuntimeError as exc:
        if encoder != "h264_nvenc":
            raise
        log(f"⚠️ {label} NVENC failed ({str(exc).splitlines()[0][:120]}) — libx264 for the whole pass")
        shutil.rmtree(run_dir, ignore_errors=True)
        _render_parts_once(ffmpeg, input_video, output_video, parts, size, "libx264", run_dir, should_stop, progress, label)
    if not output_video.is_file() or output_video.stat().st_size < 5000:
        raise RuntimeError(f"{label} render produced no video")
    got = probe_frames(ffprobe, output_video)
    if abs(got - total) > 2:
        log(f"⚠️ {label}: {got} frames out, {total} in (differs by {got - total}); check the result")
    shutil.rmtree(run_dir, ignore_errors=True)
    return output_video


def apply_slow_motion(ffmpeg: str, ffprobe: str, input_video: Path, output_video: Path, settings: dict[str, Any],
                      encoder: str, work_dir: Path, *, log: LogFn = lambda _m: None,
                      should_stop: Callable[[], bool] | None = None,
                      progress: Callable[[int, int, str], None] | None = None) -> Path:
    cfg = normalize_slow_motion(settings)
    total = probe_frames(ffprobe, input_video)
    parts = plan_slow_motion(total, gap_seconds=cfg["gap_seconds"], slow_seconds=cfg["slow_seconds"], speed=cfg["speed"])
    slows = sum(1 for p in parts if p["kind"] == "slow")
    log(f"🐌 Slow motion: play {cfg['gap_seconds']}s → slow {cfg['slow_seconds']}s at {cfg['speed']:g}× | "
        f"{slows} slow part(s) over {total / FPS:.0f}s of picture")
    if slows == 0:
        log("ℹ️ Video is shorter than one play block — no slow motion added.")
        return input_video
    out = _render_parts(ffmpeg, ffprobe, input_video, output_video, parts, encoder, work_dir, "slow", cfg, log,
                        should_stop or (lambda: False), progress, "Slow motion")
    log(f"✅ Slow motion done: {output_video.name}")
    return out


def apply_auto_edit(ffmpeg: str, ffprobe: str, input_video: Path, output_video: Path, settings: dict[str, Any],
                    encoder: str, work_dir: Path, *, default_seed: int = 0, log: LogFn = lambda _m: None,
                    should_stop: Callable[[], bool] | None = None,
                    progress: Callable[[int, int, str], None] | None = None) -> Path:
    cfg = normalize_auto_edit(settings)
    total = probe_frames(ffprobe, input_video)
    seed = cfg["seed"] if cfg["seed"] is not None else default_seed
    parts = plan_auto_edit(total, effects=cfg["effects"], intensity=cfg["intensity"], slow_seconds=cfg["slow_seconds"],
                           hold_seconds=cfg["hold_seconds"], seed=seed)
    counts = {k: 0 for k in AUTO_EFFECTS}
    for p in parts:
        counts["flip"] += bool(p.get("flip"))
        counts["zoom"] += bool(p.get("zoom")) and p["kind"] != "hold"
        counts["freeze"] += p["kind"] == "hold"
        counts["vignette"] += p.get("vignette", 0) > 0
        counts["slow"] += p["kind"] == "slow"
    log(f"🎲 Auto edit ({cfg['intensity']}, seed {seed}): " + ", ".join(f"{k} {counts[k]}" for k in cfg["effects"])
        + f" | {len(parts)} part(s) over {total / FPS:.0f}s of picture")
    if not cfg["effects"] or all(p["kind"] == "play" and not p.get("flip") and not p.get("zoom") and not p.get("vignette")
                                 for p in parts):
        log("ℹ️ Auto edit chose nothing for this video — the picture is left as it is.")
        return input_video
    out = _render_parts(ffmpeg, ffprobe, input_video, output_video, parts, encoder, work_dir, "auto", [cfg, seed], log,
                        should_stop or (lambda: False), progress, "Auto edit")
    log(f"✅ Auto edit done: {output_video.name}")
    return out


def apply_video_look(ffmpeg: str, ffprobe: str, input_video: Path, output_video: Path, settings: dict[str, Any],
                     encoder: str, *, log: LogFn = lambda _m: None) -> Path:
    """Colour filter + vignette over the whole video in one pass."""
    from core import _encoder_args
    cfg = normalize_look(settings)
    vf = look_vf(cfg)
    if not vf:
        return input_video
    log(f"🎨 Video look: filter {cfg['preset']} {cfg['strength']}% | vignette {cfg['vignette']}%")
    enc = _encoder_args(encoder) + ["-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-movflags", "+faststart"]
    cmd = lambda e: [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_video),
                     "-vf", vf + ",setsar=1,format=yuv420p", *e, str(output_video)]
    try:
        _run(cmd(enc), "Video look")
    except RuntimeError as exc:
        if encoder != "h264_nvenc":
            raise
        log(f"⚠️ Video look NVENC failed ({str(exc).splitlines()[0][:120]}) — libx264")
        _run(cmd(_encoder_args("libx264") + ["-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-movflags", "+faststart"]), "Video look")
    if not output_video.is_file() or output_video.stat().st_size < 5000:
        raise RuntimeError("Video look render produced no video")
    log(f"✅ Video look done: {output_video.name}")
    return output_video
