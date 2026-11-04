"""Meta MMS-TTS Burmese (facebook/mms-tts-mya): a free voice that runs on this PC, no account and no API key.

Needs the optional packages in requirements-mms.txt (torch + transformers). The model (a VITS checkpoint, a few
hundred MB at most) is downloaded from huggingface.co on first use and cached; set HF_ENDPOINT in .env for a mirror.

The class has the same method as EdgeTTSEngine (generate_channel99_voice -> path of a 24 kHz mono WAV), so the Smart
Sync code treats both alike. If it cannot load or fails on a line, core.TTSRouter falls back to Edge TTS.

Limits to know: the voice is more robotic than Edge's Thiha / Nilar, there is one voice (no pitch), and numbers are
read digit by digit. The MMS model licence (CC-BY-NC 4.0) does not allow commercial use - check it before monetising.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import unicodedata
import wave
from pathlib import Path
from typing import Any, Callable

LogFn = Callable[[str], None]
MODEL_ID = "facebook/mms-tts-mya"
MAX_CHUNK_CHARS = 180          # VITS gets unstable on very long inputs: speak sentence-sized chunks
PAUSE_SECONDS = 0.12           # between chunks of one line
OUT_RATE = 24000               # the same as the Edge TTS WAV files

_DIGIT_WORDS = {
    "0": "သုည", "1": "တစ်", "2": "နှစ်", "3": "သုံး", "4": "လေး",
    "5": "ငါး", "6": "ခြောက်", "7": "ခုနစ်", "8": "ရှစ်", "9": "ကိုး",
    "၀": "သုည", "၁": "တစ်", "၂": "နှစ်", "၃": "သုံး", "၄": "လေး",
    "၅": "ငါး", "၆": "ခြောက်", "၇": "ခုနစ်", "၈": "ရှစ်", "၉": "ကိုး",
}
_SENTENCE_RE = re.compile(r"[^။.!?]+[။.!?]*")


def mms_missing_packages() -> list[str]:
    return [name for name in ("torch", "transformers") if importlib.util.find_spec(name) is None]


def rate_to_speaking_rate(rate: str) -> float:
    """Edge-style "+10%" / "-20%" -> VITS speaking_rate (1.0 = normal)."""
    m = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*%\s*", str(rate or "+0%"))
    percent = float(m.group(1)) if m else 0.0
    return max(0.5, min(2.0, 1.0 + percent / 100.0))


def prepare_text(text: str) -> str:
    """What the model is fed: NFC, digits spelt out, Burmese punctuation as , and ."""
    value = unicodedata.normalize("NFC", str(text or ""))
    value = "".join(ch if ch in "\n\t" or ord(ch) >= 32 else " " for ch in value)
    value = re.sub(r"[0-9၀-၉]", lambda m: " " + _DIGIT_WORDS[m.group(0)] + " ", value)
    value = value.replace("၊", ",").replace("။", ".").lower()
    value = re.sub(r"\s+", " ", value).strip()
    if not any(ch.isalpha() for ch in value):
        raise RuntimeError(f"MMS TTS text has nothing speakable: {text!r}")
    return value


def split_chunks(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Sentence-sized pieces (<= limit characters where the text allows it); nothing is dropped."""
    pieces: list[str] = []
    for sentence in (m.group(0).strip() for m in _SENTENCE_RE.finditer(text)):
        if not sentence:
            continue
        while len(sentence) > limit:
            cut = max(sentence.rfind(",", 0, limit), sentence.rfind(" ", 0, limit))
            cut = cut + 1 if cut > limit // 3 else limit
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)
    chunks: list[str] = []
    for piece in pieces:                                   # join short neighbours back together
        if chunks and len(chunks[-1]) + 1 + len(piece) <= limit:
            chunks[-1] += " " + piece
        else:
            chunks.append(piece)
    return chunks


class MMSTTSEngine:
    def __init__(self, *, ffmpeg: str, work_dir: Path, rate: str = "+0%", log: LogFn = lambda _m: None,
                 model_id: str = MODEL_ID) -> None:
        missing = mms_missing_packages()
        if missing:
            raise RuntimeError(
                "Meta MMS အတွက် " + " + ".join(missing) + " မရှိသေးပါ။ "
                "INSTALL_MMS.bat ကို run ပါ (သို့) pip install -r requirements-mms.txt လုပ်ပါ။")
        import numpy as np
        import torch
        from transformers import AutoTokenizer, VitsModel
        self.np, self.torch = np, torch
        self.ffmpeg = ffmpeg
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.model_id = model_id
        self.speaking_rate = rate_to_speaking_rate(rate)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._counter = 0
        log(f"⬇️ Meta MMS model '{model_id}' — the first run downloads it from huggingface.co (kept for next time)...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = VitsModel.from_pretrained(model_id).to(self.device).eval()
        self.model.speaking_rate = self.speaking_rate
        self.sample_rate = int(self.model.config.sampling_rate)
        log(f"✅ Meta MMS READY — {model_id} on {self.device} | speed x{self.speaking_rate:.2f} | one voice, no pitch control")

    def _speak(self, chunk: str, seed: int) -> Any:
        inputs = self.tokenizer(chunk, return_tensors="pt")
        if int(inputs["input_ids"].shape[-1]) == 0:
            return None
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        self.torch.manual_seed(seed)                         # VITS is random: same text -> same audio, run after run
        with self.torch.no_grad():
            wave_out = self.model(**inputs).waveform
        return wave_out[0].float().cpu().numpy()

    def generate_channel99_voice(self, text: str, voice: str = ""):
        clean = prepare_text(text)
        seed = int(hashlib.sha1(clean.encode("utf-8")).hexdigest()[:8], 16)
        np = self.np
        silence = np.zeros(int(self.sample_rate * PAUSE_SECONDS), dtype=np.float32)
        parts: list[Any] = []
        for chunk in split_chunks(clean):
            audio = self._speak(chunk, seed)
            if audio is not None and audio.size:
                if parts:
                    parts.append(silence)
                parts.append(audio)
        if not parts:
            raise RuntimeError(f"MMS TTS produced no audio (the model knew none of the letters): {clean[:120]!r}")
        samples = np.concatenate(parts)
        peak = float(np.max(np.abs(samples)))
        if peak < 1e-4:
            raise RuntimeError("MMS TTS produced silence")
        samples = samples * min(0.9 / peak, 6.0)             # steady level from line to line
        self._counter += 1
        stem = f"mms_{self._counter:05d}_{hashlib.sha1(clean.encode('utf-8')).hexdigest()[:10]}"
        raw, wav = self.work_dir / f"{stem}_raw.wav", self.work_dir / f"{stem}.wav"
        with wave.open(str(raw), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self.sample_rate)
            handle.writeframes((np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
        conv = subprocess.run(
            [self.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
             "-ac", "1", "-ar", str(OUT_RATE), "-c:a", "pcm_s16le", str(wav)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        raw.unlink(missing_ok=True)
        if conv.returncode != 0 or not wav.is_file():
            raise RuntimeError("MMS TTS WAV conversion failed: " + (conv.stderr or "")[-1500:])
        return str(wav)
