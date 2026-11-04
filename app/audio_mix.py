"""Mix the ORIGINAL sound of the video with the Burmese dub.

The picture of every Smart Sync part is stretched / squeezed so that it lasts as long as its Burmese line. The original
sound of that part is stretched the same way (pitch kept, ffmpeg `atempo`), so it stays in step with the picture, and
the parts are joined into one track as long as the dub. The mix then lowers ("ducks") the original while the dub
speaks, so the dub stays clear and the background (music, ambience, the original voice) comes back between lines.

original_percent  0   = dub only (the default, the old behaviour)  ...  100 = the original at its own level
dub_percent       100 = unchanged (what the "Voice vol" slider already did)
duck              True = the original is lowered while the dub speaks
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import shutil
from pathlib import Path
from typing import Any, Callable

LogFn = Callable[[str], None]
RATE = 48000
DUCK_THRESHOLD = 0.02
DUCK_RATIO = 8.0


def normalize_audio_mix(cfg: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(cfg or {})
    def num(value: Any, default: float, lo: float, hi: float) -> int:
        try:
            return int(round(max(lo, min(hi, float(value)))))
        except Exception:
            return int(default)
    return {"original_percent": num(cfg.get("original_percent", 0), 0, 0, 100),
            "duck": bool(cfg.get("duck", True))}


def has_audio(ffprobe: str, source: Path) -> bool:
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type",
                          "-of", "csv=p=0", str(source)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return "audio" in (out.stdout or "")


def atempo_chain(ratio: float) -> str:
    """ffmpeg atempo takes 0.5 - 2.0 per stage: longer / shorter stretches are chained."""
    ratio = max(0.1, min(10.0, float(ratio)))
    stages: list[float] = []
    while ratio > 2.0:
        stages.append(2.0)
        ratio /= 2.0
    while ratio < 0.5:
        stages.append(0.5)
        ratio /= 0.5
    stages.append(ratio)
    return ",".join(f"atempo={s:.5f}" for s in stages)


def _run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed:\n{(r.stderr or '')[-2500:]}")


def build_original_track(ffmpeg: str, ffprobe: str, source: Path, timing: list[dict[str, Any]], work_dir: Path, *,
                         log: LogFn = lambda _m: None, should_stop: Callable[[], bool] = lambda: False) -> Path | None:
    """One WAV as long as the dub, made of the original sound of every part stretched like its picture."""
    if not has_audio(ffprobe, source):
        log("ℹ️ Original audio: the video has no sound track — the dub is used alone")
        return None
    sig = hashlib.sha1(json.dumps([str(source.resolve()), source.stat().st_size, source.stat().st_mtime_ns,
                                   [[t["video_start"], t["video_end"], round(float(t["audio_duration"]), 3)] for t in timing]],
                                  sort_keys=True).encode("utf-8")).hexdigest()[:10]
    out = work_dir / f"original_track_{sig}.wav"
    if out.is_file() and out.stat().st_size > 1000:
        log("♻️ Original audio track reuse")
        return out
    for old in work_dir.glob("original_track_*"):
        if old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
        else:
            old.unlink(missing_ok=True)
    parts_dir = work_dir / f"original_track_{sig}_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    log(f"🎼 Original audio: stretching the sound of {len(timing)} part(s) like their picture...")
    for i, item in enumerate(timing, 1):
        if should_stop():
            raise InterruptedError("STOP requested while preparing the original audio")
        window = max(0.05, float(item["video_end"]) - float(item["video_start"]))
        target = max(0.05, float(item["audio_duration"]))
        clip = parts_dir / f"p{i:05d}.wav"
        if not (clip.is_file() and clip.stat().st_size > 100):
            af = f"{atempo_chain(window / target)},apad=whole_dur={target:.5f},atrim=0:{target:.5f},asetpts=PTS-STARTPTS"
            _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{float(item['video_start']):.6f}",
                  "-t", f"{window:.6f}", "-i", str(source), "-map", "0:a:0", "-vn", "-af", af,
                  "-ac", "2", "-ar", str(RATE), "-c:a", "pcm_s16le", str(clip)], f"Original audio part {i}")
        clips.append(clip)
    listing = parts_dir / "list.txt"
    listing.write_text("".join("file '" + c.resolve().as_posix().replace("'", "'\\''") + "'\n" for c in clips), encoding="utf-8")
    tmp = out.with_suffix(".tmp.wav")
    _run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
          "-c", "copy", str(tmp)], "Original audio concat")
    tmp.replace(out)
    shutil.rmtree(parts_dir, ignore_errors=True)
    return out


def mix_filter(original_percent: float, dub_percent: float, duck: bool, dub_mono: bool = True) -> str:
    o = max(0.0, float(original_percent)) / 100.0
    d = max(0.0, float(dub_percent)) / 100.0
    # The dub (Edge TTS / MMS) is mono. A plain mono -> stereo conversion lowers it by 3 dB, which would make the
    # dub quieter as soon as the mix is switched on: copy the channel instead.
    to_stereo = "pan=stereo|c0=c0|c1=c0" if dub_mono else f"aformat=channel_layouts=stereo"
    chain = [f"[0:a]aresample={RATE},{to_stereo},volume={d:.4f},asplit=2[dub][key]",
             f"[1:a]volume={o:.4f},aformat=sample_rates={RATE}:channel_layouts=stereo[orig]"]
    if duck:
        chain.append(f"[orig][key]sidechaincompress=threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}:attack=20:release=450:"
                     f"makeup=1[ducked]")
        chain.append("[dub][ducked]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=disabled[mix]")
    else:
        chain.append("[key]anullsink")
        chain.append("[dub][orig]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=disabled[mix]")
    return ";".join(chain)


def mix_tracks(ffmpeg: str, dub: Path, original: Path, output: Path, *, original_percent: float, dub_percent: float,
               duck: bool, dub_mono: bool = True) -> Path:
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(dub), "-i", str(original),
           "-filter_complex", mix_filter(original_percent, dub_percent, duck, dub_mono), "-map", "[mix]",
           "-c:a", "pcm_s16le", "-ar", str(RATE), str(output)]
    _run(cmd, "Audio mix")
    return output
