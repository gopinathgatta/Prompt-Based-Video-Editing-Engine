"""Replay one or more JSON edit sessions against a running local demo API."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def request(url, method="GET", data=None, headers=None, content_type="application/json"):
    raw = data if isinstance(data, bytes) else (json.dumps(data).encode() if data is not None else None)
    req = urllib.request.Request(url, data=raw, method=method, headers={"Content-Type": content_type, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            payload = res.read()
            return res.status, json.loads(payload) if "json" in res.headers.get("Content-Type", "") else payload
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try: return exc.code, json.loads(payload)
        except Exception: return exc.code, {"error": {"message": payload.decode(errors="replace")}}


def run(path: Path, base_url: str, output: Path):
    spec = json.loads(path.read_text(encoding="utf-8"))
    media = Path(spec["video"]).resolve()
    if not media.is_file(): raise FileNotFoundError(media)
    output.mkdir(parents=True, exist_ok=True)
    status, uploaded = request(base_url + "/api/v1/media/upload?filename=" + urllib.parse.quote(media.name), "POST", media.read_bytes(), {"Idempotency-Key": str(uuid.uuid4())}, "video/mp4" if media.suffix.lower()==".mp4" else "video/quicktime")
    if status != 201: raise RuntimeError(f"Upload failed: {uploaded}")
    sid = uploaded["session_id"]
    results = []
    if spec.get("words") is not None:
        _, result = request(f"{base_url}/api/v1/sessions/{sid}/transcript", "POST", {"words": spec["words"]}, {"Idempotency-Key": str(uuid.uuid4())})
        results.append({"step": "load transcript", "response": result})
    for index, step in enumerate(spec.get("steps", []), 1):
        instruction = step["say"] if isinstance(step, dict) else str(step)
        started = time.perf_counter()
        _, result = request(f"{base_url}/api/v1/sessions/{sid}/instructions", "POST", {"instruction": instruction}, {"Idempotency-Key": str(uuid.uuid4())})
        results.append({"step": index, "instruction": instruction, "latency_ms": round((time.perf_counter()-started)*1000, 3), "response": result})
        _, timeline = request(f"{base_url}/api/v1/sessions/{sid}")
        (output / f"{path.stem}_step_{index:02d}.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
    _, final_state = request(f"{base_url}/api/v1/sessions/{sid}")
    result = {"session_id": sid, "upload": uploaded, "steps": results, "final_state": final_state, "media_rights": spec.get("media_rights", "not specified by session file")}
    (output / f"{path.stem}_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if spec.get("render", True):
        _, job = request(f"{base_url}/api/v1/sessions/{sid}/render", "POST", {}, {"Idempotency-Key": str(uuid.uuid4())})
        if job.get("job_id"):
            while True:
                _, current = request(f"{base_url}/api/v1/jobs/{job['job_id']}")
                if current.get("status") in {"succeeded", "failed"}:
                    job = current; break
                time.sleep(.5)
        result["render_job"] = job
        downloaded = []
        if job.get("status") == "succeeded":
            for index, url in enumerate(job.get("result_links", [])):
                code, content = request(base_url + url)
                if code != 200:
                    raise RuntimeError(f"Render output download failed ({code}): {url}")
                if index == 0:
                    name = f"{path.stem}_rendered.mp4"
                    payload = content if isinstance(content, bytes) else json.dumps(content).encode()
                else:
                    name = f"{path.stem}_rendered.mp4.manifest.json"
                    payload = content if isinstance(content, bytes) else json.dumps(content, indent=2).encode()
                (output / name).write_bytes(payload)
                downloaded.append(str(output / name))
        result["render_outputs"] = downloaded
        (output / f"{path.stem}_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("inputs", help="JSON session file or directory of JSON session files")
    p.add_argument("--api", default="http://127.0.0.1:8000")
    p.add_argument("--output", default="outputs/session_runs")
    p.add_argument("--start-server", action="store_true", help="start and stop an isolated local API for this run")
    p.add_argument("--data-dir", help="session media/output directory when using --start-server")
    args = p.parse_args()
    src = Path(args.inputs)
    files = sorted(src.glob("*.json")) if src.is_dir() else [src]
    if not files: raise SystemExit("No JSON session files found")
    out = Path(args.output)
    proc = None
    base_url = args.api.rstrip("/")
    try:
        if args.start_server:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = dict(os.environ, PS2_HOST="127.0.0.1", PS2_PORT=str(port))
            if args.data_dir:
                env["PS2_DATA_DIR"] = str(Path(args.data_dir).resolve())
            project_root = Path(__file__).resolve().parents[1]
            proc = subprocess.Popen(
                [sys.executable, "-m", "app.server"], cwd=project_root, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            base_url = f"http://127.0.0.1:{port}"
            for _ in range(100):
                if proc.poll() is not None:
                    raise RuntimeError(f"Local API exited with code {proc.returncode}")
                try:
                    code, _ = request(base_url + "/health")
                    if code == 200:
                        break
                except Exception:
                    time.sleep(0.1)
            else:
                raise TimeoutError("Local API did not become healthy")
        for f in files:
            print(json.dumps({"input": str(f), "result": run(f, base_url, out)}, ensure_ascii=False))
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__": main()
