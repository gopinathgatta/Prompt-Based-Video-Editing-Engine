# Prompt-Based Video Editing Engine (PS2)

A local, deterministic video-editing prototype with a browser UI, a source-anchored timeline, a small natural-language command interpreter, FFmpeg rendering, and a JSON API. It is an assessment prototype, not a hosted production service. The UI supports MP4/MOV upload, user-supplied word-level transcript JSON, captions, timeline edits, history, render jobs, preview, download, and manifest review.

The editor uses a responsive creative-workspace layout: a section rail, source-media library and properties, a dominant preview with custom play/pause/seek/mute/fullscreen controls, a command center, operation history, and a lower timeline with proportional time ticks and separate video, linked-source-audio, and word-anchored caption tracks. A transcript navigator can seek to supplied words. Navigation and example prompts are interactive; examples populate the composer and require a deliberate Apply action. At narrow widths, the workspace stacks its panels while keeping the timeline horizontally navigable. The page uses the system font stack and inline SVG icons without added font, icon, or UI framework dependencies.

## Run the editor on your computer

Requirements: Python 3.10+, FFmpeg and FFprobe on `PATH`, and (for caption burn-in) a readable font file. No Python packages are needed.

```powershell
.\scripts\start_editor.ps1
```

The helper launches the server in the background, checks `/health`, and opens the browser. To run it in the foreground instead:

```powershell
py -m app.server
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The server defaults to localhost only. Uploaded sources and renders are kept in `work/runtime_data/`; the server does not overwrite the source. Max upload size defaults to 200 MiB.

The service could not be exposed by this managed execution workspace to its browser pane, so this is a **local run URL**, not a currently hosted public demo. Run the command in a terminal on your own computer to use the UI. The service is volatile: sessions/history are in memory and are lost after restart (uploaded files remain on disk).

## Supported command examples

- `Cut the first 30 seconds`
- `Cut 00:10 to 00:20`
- `Keep 00:30 to 01:15`
- `Reorder 00:20 to 00:30 before 00:05`
- `Speed up from 00:40 to 00:50 by 1.5x`
- `Add a caption 'Welcome!' when I say welcome to the channel`
- `Change the existing caption to red`
- `Add text overlay 'Chapter 1' when I say introduction`
- `Mute pricing` (unique transcript phrase required)
- `Bleep pricing` (unique transcript phrase required; rendered as a 1 kHz tone)
- `Remove filler words` (only transcript entries marked `filler: true`)
- `Remove silences longer than 0.5 seconds` (FFmpeg source-audio detection; preserves configured deliberate pauses)
- Upload optional MP3/WAV/M4A/AAC music, then `Add background music` (ducked beneath source speech during render)
- `Undo`, `Redo`, `Restore the intro`

Repeated semantic matches request clarification. URL ingestion and machine transcription are not implemented. Unsupported instructions must not be described as applied.

## Timestamp policy

- Numeric edit ranges in instructions mean **current edited-timeline seconds**.
- Word transcript `start_s` / `end_s` values mean **original-source seconds**.
- Captions and word effects retain transcript word IDs; current positions are derived through source segments, order, and speed.
- `Restore the intro` restores original-source range 0–30 seconds (or the entire source if shorter). The engine method `restore_source_range()` takes original-source seconds.
- Time formats `MM:SS` and `HH:MM:SS` are accepted by the limited parser. Ambiguous language that is not safely handled should be clarified/rejected.

## Test and sample commands

```powershell
py -m unittest discover -s tests -v
py scripts/demo_session.py
```

The automated suite generates synthetic test-pattern/sine-tone videos, exercises the timeline, rendering and HTTP API, and checks the source hash remains unchanged. Current verified local result: 30 tests pass. The sample output and FFprobe-derived manifest are under `outputs/demo/`. There is no real speech, no transcription accuracy result, and no perceptual lip-sync listening test.

Run the API-backed sample against an isolated local server process:

```powershell
py scripts/demo_session.py
py scripts/run_session.py examples/demo_session.json --start-server --output outputs/session_runs
```

The included example expects `py scripts/demo_session.py` to generate its synthetic input first. The runner accepts one JSON session file or a directory of JSON session files. Each contains a local video path, optional word-level transcript, ordered steps, and an optional render flag. It records responses, timeline snapshots, instruction timings, downloads the rendered MP4 and manifest, and writes them locally. Omit `--start-server` to connect to a server already running at `--api`.

## API and container

The OpenAPI 3.1 contract is `openapi.yaml`; routes are under `/api/v1/`. Render returns HTTP 202 and a job ID. `Idempotency-Key` is required for POSTs. JSON errors use a common envelope. `/health` and `/ready` are included.

Environment examples are in `.env.example`. Docker files are included, but Docker was not installed in the verification environment and this image has not been built. Use `docker compose up --build` only after installing Docker; container behavior remains unverified.

Common JSON error codes include `INVALID_REQUEST`, `UNSUPPORTED_MEDIA`, `UPLOAD_TOO_LARGE`, `NOT_FOUND`, `IDEMPOTENCY_CONFLICT`, and `INTERNAL_ERROR`. Route-specific error details are returned in the `error` object.

## Project layout

- `app/timeline/models.py`, `app/timeline/engine.py` — timeline model and deterministic edit engine.
- `app/server.py` — local HTTP API, upload, instruction handling, job polling.
- `app/render.py` — FFmpeg/FFprobe renderer and output manifest.
- `app/static/index.html` — browser-based editor.
- `tests/` — 12 unit tests, one render integration test, one API end-to-end test.
- `scripts/` — synthetic demo and session runner.
- `TRACEABILITY.md`, `REPORT.md`, `SOURCES.md`, `AI_USE.md` — assessment record and disclosures.

## Important limitations before submission

This prototype does **not** yet pass all official must-haves. See the precise statuses in `TRACEABILITY.md`. There is no verified public full-render deployment, durable session database, ASR/diarization, complete hard-case evidence, specific historical-edit restore, or candidate-owned single-/multi-speaker test videos. The FFmpeg output reports stream-start offset, not perceptual sync. The provenance/license of the timeline code that was present before this task is unknown and must be resolved before any commercial-use declaration. Do not answer “Yes” to the all-must-haves submission question.
