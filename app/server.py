from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .render import probe, render
from .timeline.engine import OperationResponse, TimelineEngine
from .timeline.models import Segment, Timeline, TranscriptWord

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static"
# Vercel functions have a read-only deployment bundle; /tmp is their writable
# ephemeral location. Local and container deployments retain the configured path.
_is_serverless = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
_default_data = "/tmp/ps2-runtime-data" if _is_serverless else ROOT / "work" / "runtime_data"
DATA = Path(os.environ.get("PS2_DATA_DIR", _default_data)).resolve()
MEDIA_DIR, OUTPUT_DIR = DATA / "media", DATA / "outputs"
for directory in (MEDIA_DIR, OUTPUT_DIR):
    directory.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = int(os.environ.get("PS2_MAX_UPLOAD_BYTES", 200 * 1024 * 1024))
SESSIONS: dict[str, dict] = {}
JOBS: dict[str, dict] = {}
IDEMPOTENCY: dict[str, dict] = {}
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=2)


def response(status: str, engine: TimelineEngine | None = None, **kwargs) -> dict:
    data = {"status": status, "time_policy": "Current edited-timeline seconds; restore_source_range uses original-source seconds."}
    if engine:
        data.update({"duration_s": engine.timeline.duration_s, "timeline_hash": engine.timeline_hash(), "timeline": engine.timeline.as_dict()})
    data.update(kwargs)
    return data


def parse_seconds(value: str) -> float:
    value = value.strip()
    if ":" in value:
        parts = [float(p) for p in value.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(value)


def find_phrase(words: list[TranscriptWord], phrase: str) -> list[list[str]]:
    def norm(s: str) -> str:
        return re.sub(r"[^\w']+", "", s.casefold())
    wanted = [norm(x) for x in phrase.split() if norm(x)]
    tokens = [norm(w.text) for w in words]
    out = []
    for i in range(len(tokens) - len(wanted) + 1):
        if tokens[i:i + len(wanted)] == wanted:
            out.append([w.id for w in words[i:i + len(wanted)]])
    return out


def apply_instruction(engine: TimelineEngine, instruction: str) -> OperationResponse:
    text = instruction.strip()
    lower = text.casefold()
    if lower in {"undo", "undo the previous edit"}:
        return engine.undo()
    if lower == "redo":
        return engine.redo()
    if "render" in lower:
        return engine.response("Rejected", reason="Rendering is started through the Render button/API job, not as an edit instruction.")
    if "caption" in lower and "when i say" in lower:
        label_match = re.search(r"caption\s+['\"](.+?)['\"]", text, re.I)
        phrase_match = re.search(r"when i say\s+['\"]?(.+?)['\"]?$", text, re.I)
        if not phrase_match:
            return engine.response("Needs clarification", question="Which transcript phrase should the caption follow?", options=["Load/select transcript words"])
        phrase = phrase_match.group(1).strip().strip("'\"")
        matches = find_phrase(engine.visible_words(), phrase)
        if not matches:
            return engine.response("Needs clarification", question=f"I could not find “{phrase}” in the loaded transcript. Which words should anchor the caption?", options=["Select transcript words"])
        if len(matches) > 1:
            return engine.response("Needs clarification", question=f"“{phrase}” occurs {len(matches)} times. Which occurrence should receive the caption?", options=[f"Occurrence {i+1}" for i in range(len(matches))])
        return engine.add_caption(label_match.group(1) if label_match else phrase, matches[0])
    if "caption" in lower and lower.startswith(("change ", "make ", "set ", "update ")):
        color_match = re.search(r"\b(white|black|red|green|blue|yellow|cyan|magenta)\b", lower)
        if color_match:
            return engine.modify_caption(color=color_match.group(1))
        return engine.response("Needs clarification", question="Which caption change should I make?", options=["Specify a supported caption color"])
    if "caption" in lower and (" at " in lower or "color" in lower or "colour" in lower):
        return engine.response("Needs clarification", question="Caption placement must be anchored to transcript words. Which phrase should it follow?", options=["Select transcript words"])
    if "automatic caption" in lower or "auto-caption" in lower or "auto caption" in lower:
        return engine.auto_caption()
    overlay_match = re.search(r"(?:add|show) (?:a )?(?:text )?overlay\s+['\"](.+?)['\"]\s+when i say\s+['\"]?(.+?)['\"]?$", text, re.I)
    if overlay_match:
        phrase = overlay_match.group(2).strip().strip("'\"")
        matches = find_phrase(engine.visible_words(), phrase)
        if not matches:
            return engine.response("Needs clarification", question=f"I could not find “{phrase}” in the loaded transcript.", options=["Select transcript words"])
        if len(matches) > 1:
            return engine.response("Needs clarification", question=f"“{phrase}” occurs {len(matches)} times. Which occurrence should receive the overlay?", options=[f"Occurrence {i+1}" for i in range(len(matches))])
        positions = engine.word_positions()
        spans = [positions[wid] for wid in matches[0] if wid in positions]
        return engine.add_overlay(overlay_match.group(1), min(s[0] for s in spans), max(s[1] for s in spans), matches[0])
    if "filler" in lower or "ums and ahs" in lower or "um and ah" in lower:
        return engine.remove_fillers()
    if lower.startswith("bleep "):
        return engine.response("Rejected", reason="Bleep output is not yet supported by the local renderer; no timeline change was made.")
    if lower.startswith("mute "):
        phrase = text.split(" ", 1)[1].strip("'\"")
        matches = find_phrase(engine.visible_words(), phrase)
        if not matches:
            return engine.response("Needs clarification", question="Which visible transcript word should receive the audio effect?", options=["Select transcript words"])
        if len(matches) > 1:
            return engine.response("Needs clarification", question="That word or phrase occurs multiple times. Which occurrence?", options=[f"Occurrence {i+1}" for i in range(len(matches))])
        return engine.audio_word(matches[0], "mute")
    if lower.startswith("cut ") or lower.startswith("remove first ") or lower.startswith("remove the first "):
        range_match = re.search(r"(\d+(?::\d{1,2}){0,2}(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?::\d{1,2}){0,2}(?:\.\d+)?)", text, re.I)
        if range_match:
            try:
                return engine.cut(parse_seconds(range_match.group(1)), parse_seconds(range_match.group(2)), text)
            except ValueError as exc:
                return engine.response("Rejected", reason=str(exc))
        first_match = re.search(r"first\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?)", text, re.I)
        if first_match:
            duration = float(first_match.group(1)) * (60 if first_match.group(2).lower().startswith(("min",)) else 1)
            return engine.cut(0, duration, text)
    speed_match = re.search(r"(?:speed up|speed)\s+from\s+(\d+(?::\d{1,2}){0,2})\s+to\s+(\d+(?::\d{1,2}){0,2}).*?(\d+(?:\.\d+)?)\s*x", text, re.I)
    if speed_match:
        try:
            return engine.speed(parse_seconds(speed_match.group(1)), parse_seconds(speed_match.group(2)), float(speed_match.group(3)))
        except ValueError as exc:
            return engine.response("Rejected", reason=str(exc))
    range_expr = r"(\d+(?::\d{1,2}){0,2}(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?::\d{1,2}){0,2}(?:\.\d+)?)"
    reorder_match = re.search(r"reorder\s+" + range_expr + r"\s+before\s+(\d+(?::\d{1,2}){0,2}(?:\.\d+)?)", text, re.I)
    if reorder_match:
        try: return engine.reorder(parse_seconds(reorder_match.group(1)), parse_seconds(reorder_match.group(2)), parse_seconds(reorder_match.group(3)))
        except ValueError as exc: return engine.response("Rejected", reason=str(exc))
    keep_match = re.search(r"keep(?: only)?\s+(?:from\s+)?" + range_expr, text, re.I)
    if keep_match:
        try: return engine.keep(parse_seconds(keep_match.group(1)), parse_seconds(keep_match.group(2)))
        except ValueError as exc: return engine.response("Rejected", reason=str(exc))
    if "pricing" in lower or "price" in lower or "cost" in lower:
        words = engine.visible_words()
        hit_indices = [i for i, w in enumerate(words) if re.sub(r"[^\w]", "", w.text.casefold()) in {"pricing", "price", "cost"}]
        if not hit_indices:
            return engine.response("Needs clarification", question="No pricing or cost match is in the loaded transcript. Which transcript passage should be removed?", options=["Select transcript words"])
        if len(hit_indices) > 1:
            return engine.response("Needs clarification", question=f"Pricing/cost matches {len(hit_indices)} times. Which occurrence or occurrences should be removed?", options=[f"Occurrence {i+1}" for i in range(len(hit_indices))] + ["All occurrences"])
        w = words[hit_indices[0]]
        pos = engine.word_positions().get(w.id)
        if pos:
            return engine.cut(*pos, instruction=text)
    if "silence" in lower:
        return engine.response("Rejected", reason="Automatic silence detection is not implemented; no segment was changed.")
    if "background music" in lower or "duck" in lower:
        return engine.response("Rejected", reason="Background music ingestion and speech ducking are not implemented in this local demo.")
    if lower.startswith("restore") and ("intro" in lower or "introduction" in lower):
        earliest_source = min((segment.source_start_s for segment in engine.timeline.segments), default=0.0)
        restore_end = min(30.0, earliest_source, engine.timeline.source_duration_s)
        if restore_end <= 1e-9:
            return engine.response("Rejected", reason="The original introduction is already present; no source prefix needs restoring.")
        return engine.restore_source_range(0, restore_end)
    return engine.response("Rejected", reason="This instruction is not supported by the current local demo. Use a cut range, speed range, transcript-anchored caption, filler removal, mute/bleep, undo, or redo.")


def envelope(code: str, message: str, retryable=False, details=None) -> dict:
    return {"error": {"code": code, "message": message, "retryable": retryable, "details": details or {}}}


class Handler(BaseHTTPRequestHandler):
    server_version = "PS2LocalDemo/0.1"

    def log_message(self, fmt, *args):
        print(json.dumps({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "level": "INFO", "job_id": getattr(self, "job_id", None), "correlation_id": self.headers.get("X-Correlation-Id", "local"), "message": fmt % args}))

    def _send(self, status_code: int, data, content_type="application/json", headers=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        elif isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(data)

    def _json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_UPLOAD:
            raise ValueError("Request exceeds configured maximum size")
        return json.loads(self.rfile.read(length) or b"{}")

    def _idem(self, body: bytes | None = None) -> tuple[str | None, dict | None]:
        key = self.headers.get("Idempotency-Key")
        if not key:
            return None, envelope("IDEMPOTENCY_KEY_REQUIRED", "POST requests require Idempotency-Key", details={})
        raw = body if body is not None else b""
        digest = hashlib.sha256(raw).hexdigest()
        with LOCK:
            prior = IDEMPOTENCY.get(key)
            if prior:
                if prior["digest"] != digest:
                    return None, envelope("IDEMPOTENCY_CONFLICT", "This key was already used for a different request")
                return key, prior["result"]
        return (key, None)

    def _store_idem(self, key, digest, result):
        with LOCK: IDEMPOTENCY[key] = {"digest": digest, "result": result}

    def do_OPTIONS(self):
        self._send(204, b"", headers={"Access-Control-Allow-Headers": "Content-Type, Idempotency-Key, X-Correlation-Id", "Access-Control-Allow-Methods": "GET, POST, OPTIONS"})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "/index.html":
            try: data = (STATIC / "index.html").read_bytes()
            except OSError: return self._send(500, envelope("UI_MISSING", "Static UI could not be loaded"))
            return self._send(200, data, "text/html; charset=utf-8")
        if path == "/health": return self._send(200, {"status": "ok"})
        if path == "/ready": return self._send(200, {"status": "ready", "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe"))})
        if path.startswith("/api/v1/jobs/"):
            job = JOBS.get(path.rsplit("/", 1)[-1])
            return self._send(200, job) if job else self._send(404, envelope("JOB_NOT_FOUND", "No job with that ID"))
        if path.startswith("/api/v1/sessions/") and path.endswith("/source"):
            sid = path.split("/")[4]; session = SESSIONS.get(sid)
            if not session: return self._send(404, envelope("SESSION_NOT_FOUND", "No session with that ID"))
            src = Path(session["source"])
            return self._send(200, src.read_bytes(), session["mime"], {"Content-Disposition": f'inline; filename="{src.name}"'})
        if path.startswith("/api/v1/sessions/"):
            sid = path.rsplit("/", 1)[-1]; session = SESSIONS.get(sid)
            if not session: return self._send(404, envelope("SESSION_NOT_FOUND", "No session with that ID"))
            return self._send(200, {"session_id": sid, "media": session["media"], "timeline": session["engine"].timeline.as_dict(), "timeline_hash": session["engine"].timeline_hash(), "duration_s": session["engine"].timeline.duration_s, "time_policy": "current edited timeline seconds"})
        if path.startswith("/api/v1/outputs/"):
            name = Path(unquote(path.rsplit("/", 1)[-1])).name
            candidate = (OUTPUT_DIR / name).resolve()
            if candidate.parent != OUTPUT_DIR or not candidate.is_file(): return self._send(404, envelope("OUTPUT_NOT_FOUND", "No such output file"))
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            disposition = {"Content-Disposition": f'inline; filename="{name}"'} if ctype.startswith("video/") else {"Content-Disposition": f'attachment; filename="{name}"'}
            return self._send(200, candidate.read_bytes(), ctype, disposition)
        return self._send(404, envelope("NOT_FOUND", "Route not found"))

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_UPLOAD: return self._send(413, envelope("UPLOAD_TOO_LARGE", "Request exceeds configured size limit"))
            raw = self.rfile.read(length)
            key = self.headers.get("Idempotency-Key")
            if not key: return self._send(400, envelope("IDEMPOTENCY_KEY_REQUIRED", "POST requests require Idempotency-Key"))
            digest = hashlib.sha256(raw).hexdigest()
            prior = IDEMPOTENCY.get(key)
            if prior:
                if prior["digest"] != digest: return self._send(409, envelope("IDEMPOTENCY_CONFLICT", "Idempotency key was reused with different content"))
                return self._send(prior["code"], prior["result"])
            if path == "/api/v1/media/upload":
                filename = Path(parse_qs(urlparse(self.path).query).get("filename", ["upload.mp4"])[0]).name
                suffix = Path(filename).suffix.casefold()
                if suffix not in {".mp4", ".mov"}: return self._send(415, envelope("UNSUPPORTED_MEDIA", "Upload an MP4 or MOV video"))
                if not raw: return self._send(400, envelope("EMPTY_UPLOAD", "Uploaded media is empty"))
                sid = str(uuid.uuid4()); source = MEDIA_DIR / f"{sid}{suffix}"; source.write_bytes(raw)
                try: meta = probe(str(source))
                except Exception as exc:
                    source.unlink(missing_ok=True)
                    return self._send(422, envelope("INVALID_VIDEO", "FFprobe could not read this video", details={"reason": str(exc)[-800:]}))
                sha = hashlib.sha256(raw).hexdigest()
                timeline = Timeline(sha, meta["duration_s"], meta["frame_rate"], [], [Segment("source_0", 0, meta["duration_s"])])
                SESSIONS[sid] = {"source": str(source), "mime": "video/quicktime" if suffix == ".mov" else "video/mp4", "media": {**meta, "filename": filename, "sha256": sha}, "engine": TimelineEngine(timeline)}
                result = {"session_id": sid, "media": SESSIONS[sid]["media"], "source_url": f"/api/v1/sessions/{sid}/source", "transcription_status": "not_started; load word-level transcript JSON"}
                IDEMPOTENCY[key] = {"digest": digest, "result": result, "code": 201}
                return self._send(201, result)
            m = re.fullmatch(r"/api/v1/sessions/([^/]+)/(instructions|transcript|render|undo|redo|restore)", path)
            if m:
                sid, action = m.groups(); session = SESSIONS.get(sid)
                if not session: return self._send(404, envelope("SESSION_NOT_FOUND", "No session with that ID"))
                engine: TimelineEngine = session["engine"]
                try: body = json.loads(raw or b"{}")
                except json.JSONDecodeError: return self._send(400, envelope("INVALID_JSON", "Request body must be JSON"))
                if action == "instructions":
                    instruction = str(body.get("instruction", ""))
                    selection = re.fullmatch(r"the\s+(\d+)(?:st|nd|rd|th)?\s+(?:one|occurrence)", instruction.strip(), re.I)
                    if not selection:
                        ordinal = re.fullmatch(r"the\s+(first|second|third|fourth|last)\s+(?:one|occurrence)", instruction.strip(), re.I)
                        if ordinal:
                            word = ordinal.group(1).lower()
                            selection = type("Selection", (), {"group": lambda self, n: str({"first": 1, "second": 2, "third": 3, "fourth": 4, "last": 999}[word])})()
                    all_selection = re.fullmatch(r"all(?: occurrences)?", instruction.strip(), re.I)
                    pending = session.get("pending_clarification")
                    if pending and selection and pending["kind"] == "pricing":
                        pick = int(selection.group(1)) - 1
                        if 0 <= pick < len(pending["word_ids"]):
                            word_id = pending["word_ids"][pick]
                            span = engine.word_positions().get(word_id)
                            session["pending_clarification"] = None
                            result = engine.cut(*span, instruction=f"{instruction} (resolved pricing occurrence)") if span else engine.response("Rejected", reason="The selected transcript match is no longer visible.")
                        else:
                            result = engine.response("Needs clarification", question="Choose one of the listed pricing occurrences.", options=[f"The {i+1} one" for i in range(len(pending["word_ids"]))])
                    elif pending and all_selection and pending["kind"] == "pricing":
                        positions = engine.word_positions()
                        ranges = [positions[x] for x in pending["word_ids"] if x in positions]
                        session["pending_clarification"] = None
                        result = engine.cut_ranges(ranges, instruction="Remove all pricing/cost matches") if ranges else engine.response("Rejected", reason="No pricing matches remain visible.")
                    else:
                        result = apply_instruction(engine, instruction)
                        if result.status == "Needs clarification" and any(x in instruction.casefold() for x in ("pricing", "price", "cost")):
                            hits = [w.id for w in engine.visible_words() if re.sub(r"[^\w]", "", w.text.casefold()) in {"pricing", "price", "cost"}]
                            if len(hits) > 1: session["pending_clarification"] = {"kind": "pricing", "word_ids": hits}
                    payload = result.as_dict()
                    code = 200
                elif action == "transcript":
                    words = body.get("words", [])
                    try:
                        parsed = [TranscriptWord(**w) for w in words]
                        if len({w.id for w in parsed}) != len(parsed): raise ValueError("Transcript word IDs must be unique")
                        if any(w.end_s > engine.timeline.source_duration_s for w in parsed): raise ValueError("Transcript words must use original-source seconds within the media duration")
                        engine.timeline.words = parsed; engine._validate()
                    except Exception as exc: return self._send(422, envelope("INVALID_TRANSCRIPT", str(exc)))
                    payload = response("Applied", engine, message=f"Loaded {len(parsed)} word-level transcript entries; transcript accuracy was not independently checked.")
                    code = 200
                elif action == "undo": payload = engine.undo().as_dict(); code = 200
                elif action == "redo": payload = engine.redo().as_dict(); code = 200
                elif action == "restore":
                    a, b = float(body.get("source_start_s", 0)), float(body.get("source_end_s", 0))
                    payload = engine.restore_source_range(a, b).as_dict(); code = 200
                else:
                    job_id = str(uuid.uuid4()); output = str(OUTPUT_DIR / f"{sid}_{job_id}.mp4")
                    JOBS[job_id] = {"job_id": job_id, "status": "queued", "progress": 0, "result_links": [], "error": None}
                    IDEMPOTENCY[key] = {"digest": digest, "result": {"job_id": job_id, "status": "queued"}, "code": 202}
                    def run_render():
                        job = JOBS[job_id]; job.update(status="running", progress=5)
                        try:
                            manifest = render(engine, session["source"], output)
                            manifest_path = Path(output + ".manifest.json")
                            job.update(status="succeeded", progress=100, result_links=[f"/api/v1/outputs/{Path(output).name}", f"/api/v1/outputs/{manifest_path.name}"], manifest=manifest)
                        except Exception as exc: job.update(status="failed", progress=100, error=envelope("RENDER_FAILED", str(exc)[-1500:])["error"])
                    POOL.submit(run_render)
                    return self._send(202, {"job_id": job_id, "status": "queued", "progress": 0})
                IDEMPOTENCY[key] = {"digest": digest, "result": payload, "code": code}
                return self._send(code, payload)
            return self._send(404, envelope("NOT_FOUND", "Route not found"))
        except ValueError as exc:
            return self._send(400, envelope("INVALID_REQUEST", str(exc)))
        except Exception as exc:
            return self._send(500, envelope("INTERNAL_ERROR", str(exc)[-1000:], retryable=True))


def main():
    host = os.environ.get("PS2_HOST", "127.0.0.1")
    port = int(os.environ.get("PS2_PORT", "8000"))
    print(json.dumps({"event": "server_start", "host": host, "port": port, "data_dir": str(DATA), "max_upload_bytes": MAX_UPLOAD}))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
