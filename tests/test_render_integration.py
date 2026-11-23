import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from app.render import probe, render
from app.timeline.engine import TimelineEngine
from app.timeline.models import Segment, Timeline, TranscriptWord


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class RenderIntegrationTests(unittest.TestCase):
    def test_cut_speed_and_caption_render_to_valid_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "synthetic.mp4"
            out = Path(tmp) / "rendered.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=6",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
                "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(src),
            ], check=True)
            source = probe(str(src))
            timeline = Timeline(
                hashlib.sha256(src.read_bytes()).hexdigest(), source["duration_s"], source["frame_rate"],
                [TranscriptWord("w_hello", "hello", 3.0, 3.4)],
                [Segment("s0", 0, source["duration_s"])],
            )
            engine = TimelineEngine(timeline)
            self.assertEqual(engine.add_caption("Hello!", ["w_hello"]).status, "Applied")
            self.assertEqual(engine.cut(0, 1).status, "Applied")
            manifest = render(engine, str(src), str(out))
            self.assertTrue(out.exists())
            self.assertTrue(manifest["output_sha256"])
            self.assertLess(manifest["duration_error_frames"], 2.0)
            self.assertTrue(probe(str(out))["audio"])


if __name__ == "__main__":
    unittest.main()
