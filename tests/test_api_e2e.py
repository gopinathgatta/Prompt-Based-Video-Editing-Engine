import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def call(url, method="GET", body=None, key=None, content_type="application/json"):
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    headers = {"Content-Type": content_type}
    if key: headers["Idempotency-Key"] = key
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw
    except urllib.error.HTTPError as error:
        raw = error.read()
        try: return error.code, json.loads(raw)
        except Exception: return error.code, raw


class ApiEndToEndTests(unittest.TestCase):
    def test_upload_content_edit_ambiguity_render_and_idempotency(self):
        import shutil
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            self.skipTest("FFmpeg and FFprobe are required")
        with tempfile.TemporaryDirectory() as tmp:
            port_sock = socket.socket(); port_sock.bind(("127.0.0.1", 0)); port = port_sock.getsockname()[1]; port_sock.close()
            env = dict(os.environ, PS2_HOST="127.0.0.1", PS2_PORT=str(port), PS2_DATA_DIR=str(Path(tmp) / "data"))
            proc = subprocess.Popen([PYTHON, "-m", "app.server"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(80):
                    try:
                        if call(base + "/health")[0] == 200: break
                    except Exception: time.sleep(.1)
                else: self.fail("local API did not start")
                ui_code, ui_page = call(base + "/")
                self.assertEqual(ui_code, 200)
                self.assertIn(b"Prompt Video Editor", ui_page)
                self.assertIn(b"Import video", ui_page)
                self.assertIn(b"Prompt command center", ui_page)
                self.assertIn(b'id="previewSeek"', ui_page)
                self.assertIn(b'id="audioTrack"', ui_page)
                self.assertIn(b'id="transcriptWords"', ui_page)
                self.assertEqual(call(base + "/ready")[0], 200)
                video = Path(tmp) / "input.mp4"
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=6", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
                upload_key = str(uuid.uuid4())
                code, uploaded = call(base + "/api/v1/media/upload?filename=input.mp4", "POST", video.read_bytes(), upload_key, "video/mp4")
                self.assertEqual(code, 201)
                sid = uploaded["session_id"]
                self.assertEqual(uploaded["media"]["sha256"], __import__("hashlib").sha256(video.read_bytes()).hexdigest())
                words = [
                    {"id":"welcome","text":"Welcome","start_s":2.0,"end_s":2.2},
                    {"id":"to","text":"to","start_s":2.21,"end_s":2.32},
                    {"id":"the","text":"the","start_s":2.33,"end_s":2.43},
                    {"id":"channel","text":"channel","start_s":2.44,"end_s":2.8},
                    {"id":"price1","text":"pricing","start_s":3.5,"end_s":3.8},
                    {"id":"price2","text":"cost","start_s":4.6,"end_s":4.9},
                    {"id":"host_old","text":"old","start_s":0.5,"end_s":0.7,"speaker":"host"},
                    {"id":"host_job","text":"job","start_s":0.71,"end_s":0.9,"speaker":"host"},
                    {"id":"guest_old","text":"old","start_s":1.1,"end_s":1.3,"speaker":"guest"},
                    {"id":"guest_job","text":"job","start_s":1.31,"end_s":1.5,"speaker":"guest"},
                ]
                code, _ = call(f"{base}/api/v1/sessions/{sid}/transcript", "POST", {"words":words}, str(uuid.uuid4()))
                self.assertEqual(code, 200)
                _, speaker_question = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", {"instruction":"Remove everything the guest says about their old job"}, str(uuid.uuid4()))
                self.assertEqual(speaker_question["status"], "Needs clarification")
                _, speaker_cut = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", {"instruction":"Only the guest answer"}, str(uuid.uuid4()))
                self.assertEqual(speaker_cut["status"], "Applied")
                _, caption = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", {"instruction":"Add a caption 'Welcome!' when I say welcome to the channel"}, str(uuid.uuid4()))
                self.assertEqual(caption["status"], "Applied")
                instruction = {"instruction":"Cut the first 1 seconds"}; idem = str(uuid.uuid4())
                _, cut1 = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", instruction, idem)
                _, cut2 = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", instruction, idem)
                self.assertEqual(cut1["timeline_hash"], cut2["timeline_hash"])
                _, current = call(f"{base}/api/v1/sessions/{sid}")
                self.assertAlmostEqual(current["duration_s"], 4.6, places=2)
                _, clarification = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", {"instruction":"Remove the pricing discussion"}, str(uuid.uuid4()))
                self.assertEqual(clarification["status"], "Needs clarification")
                _, chosen = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", {"instruction":"the second one"}, str(uuid.uuid4()))
                self.assertEqual(chosen["status"], "Applied")
                _, bleep = call(f"{base}/api/v1/sessions/{sid}/instructions", "POST", {"instruction":"Bleep welcome"}, str(uuid.uuid4()))
                self.assertEqual(bleep["status"], "Applied")
                self.assertEqual(bleep["operations"][0]["type"], "audio.bleep")
                job_key = str(uuid.uuid4())
                code, job = call(f"{base}/api/v1/sessions/{sid}/render", "POST", {}, job_key)
                self.assertEqual(code, 202)
                _, same_job = call(f"{base}/api/v1/sessions/{sid}/render", "POST", {}, job_key)
                self.assertEqual(job["job_id"], same_job["job_id"])
                for _ in range(200):
                    _, state = call(f"{base}/api/v1/jobs/{job['job_id']}")
                    if state["status"] in {"succeeded", "failed"}: break
                    time.sleep(.1)
                self.assertEqual(state["status"], "succeeded", state)
                self.assertTrue(state["manifest"]["output_sha256"])
                self.assertLessEqual(state["manifest"]["av_start_offset_frames"], 1)
                self.assertLessEqual(state["manifest"]["duration_error_frames"], 1.01)
                output_code, output_video = call(base + state["result_links"][0])
                manifest_code, output_manifest = call(base + state["result_links"][1])
                self.assertEqual(output_code, 200)
                self.assertIsInstance(output_video, bytes)
                self.assertGreater(len(output_video), 1000)
                self.assertEqual(manifest_code, 200)
                self.assertEqual(output_manifest["output_sha256"], state["manifest"]["output_sha256"])
                _, original_after = call(base + f"/api/v1/sessions/{sid}/source")
                self.assertEqual(__import__("hashlib").sha256(original_after).hexdigest(), uploaded["media"]["sha256"])
            finally:
                proc.terminate(); proc.wait(timeout=10)


if __name__ == "__main__": unittest.main()
