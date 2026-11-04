"""Check transcript first: only the first seconds are transcribed, no AI key, no plan."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import recap_planner as rp  # noqa: E402

STUB = '''
import os
class WhisperTimestampService:
    def __init__(self, **kw):
        self.kw = kw
        self._model = None
        with open(os.environ["STUB_CALLS_FILE"], "a", encoding="utf-8") as f:
            f.write("init %s %s\\n" % (kw.get("model_size"), kw.get("language")))
    def transcribe(self, path, duration):
        lines = ["很久以前，山里住着一位老人。", "他每天清晨都会去河边打水。", "有一天，河里漂来一个木盒子。"]
        segs = [{"id": i, "start": i * 4.0, "end": i * 4.0 + 3, "text": t, "words": []} for i, t in enumerate(lines)]
        return {"backend": "x", "language": self.kw.get("language"), "segments": segs, "text": "".join(lines), "media_duration": duration}
'''


class PreviewTests(unittest.TestCase):
    def tearDown(self):
        rp.configure_source_language("en")

    def test_the_check_needs_no_key_and_makes_no_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            runtime = tmp / "runtime"
            (runtime / "services").mkdir(parents=True)
            (runtime / "services" / "whisper_service.py").write_text(STUB, encoding="utf-8")
            (runtime / "services" / "ai_service.py").write_text("x = 1\n", encoding="utf-8")
            env = tmp / ".env"
            env.write_text("# no keys at all\n", encoding="utf-8")
            calls = tmp / "calls.txt"
            video = tmp / "clip.mp4"
            video.write_bytes(b"x" * 2048)
            job = tmp / "job"
            job.mkdir()
            saved = dict(os.environ)
            for name in ("GEMINI_API_KEY", "ORYNX_API_KEY"):
                os.environ.pop(name, None)
            os.environ["STUB_CALLS_FILE"] = str(calls)
            try:
                builder = rp.RecapPlanBuilder(
                    runtime_root=str(runtime), gemini_env_path=str(env), ffprobe_path="ffprobe", log=lambda _m: None,
                    progress=lambda *_a: None, should_stop=lambda: False, source_language="zh", asr_preview_seconds=30)
                (job / "_whisper_preview_16k.wav").write_bytes(b"RIFF")          # what ffmpeg would have made
                with mock.patch.object(rp, "_probe_video_duration", return_value=60.0), \
                     mock.patch.object(rp, "_probe_audio_duration", return_value=60.0), \
                     mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stderr="")):
                    with self.assertRaises(rp.TranscriptPreviewDone) as caught:
                        builder.build(source=video, job_dir=job, source_title="clip", reuse=True)
            finally:
                os.environ.clear()
                os.environ.update(saved)
            message = str(caught.exception)
            self.assertIn("ပထမ 30 စက္ကန့်", message)
            self.assertIn("很久以前", message)
            self.assertTrue((job / "whisper_preview.txt").read_text(encoding="utf-8").startswith("[00:00:00"))
            self.assertFalse((job / "smart_sync_plan.json").exists())
            self.assertIn("init small zh", calls.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
