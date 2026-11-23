# Official PS2 traceability

Statuses are evidence-based. **PASS** means an automated check directly exercised the behavior shown; **PARTIAL** means only a subset or synthetic/local behavior was exercised; **FAIL** means the official criterion is not met. The official brief and workbook remain authoritative.

| ID | Requirement | Implementation | Test and reviewer evidence | Status |
|---|---|---|---|---|
| MH-1 | Preserve original media; make edits reversible | Upload saves a separate source file and SHA-256; outputs are written separately; timeline history supports undo/redo | `tests/test_api_e2e.py` uploads media, checks uploaded hash, edits/renders, downloads original and checks the same SHA-256 | PASS (tested local flow) |
| MH-2 | Content-anchored edits survive timeline changes | Caption/audio effects refer to stable word IDs; source-time words are mapped through ordered/speed-adjusted segments | `tests/test_timeline_engine.py` checks caption movement after preceding cut, hide/restore, reorder; API test checks caption anchor in the real generated render path | PARTIAL (mute/effect lifecycle not comprehensively asserted) |
| MH-3 | Every instruction has Applied, Needs clarification, or Rejected outcome | `OperationResponse` and API parser return these three statuses; ambiguity is surfaced | API end-to-end test checks Applied caption/cut, pricing clarification and selection, and Rejected bleep; invalid timeline operations are unit-tested | PASS for exercised instruction routes; parser is intentionally limited |
| MH-4 | Deterministic timeline hash across three runs | Canonical JSON hash excludes operational history metadata | `test_identical_fixture_runs_have_identical_canonical_hash` runs the same fixture sequence three times; all hashes equal | PASS for the tested sequence |
| MH-5 | Verify A/V sync and rendered duration within official tolerance | FFmpeg output is probed; manifest reports frame-based duration error and stream start offset | `tests/test_api_e2e.py` checks duration error <=1.01 frames and stream offset <=1 frame; `outputs/demo/*manifest.json` records a 30 fps render | PARTIAL (stream timestamp offset only; perceptual sync/listening was not measured) |
| MH-6 | Required edit operations, undo/redo, restore | Engine/parser/render support cut, keep, reorder, speed, mute, captions, overlay, auto-captions, filler removal, undo, redo, source-range restore; unsupported bleep/silence/music are rejected | Unit tests cover cut, keep-related engine paths, reorder, speed, captions, filler anchors, undo/redo and restore; API test covers cut/caption/mute support boundary/render. See `docs/hard_cases.md` | FAIL (bleep, silence removal, background music ducking and specific historical-edit undo are incomplete) |
| MH-7 | Explicit, consistent timestamp policy | Numeric instruction times use current edited-timeline seconds; transcript word ranges use original-source seconds; source restore uses source seconds | `test_time_literals_are_current_timeline_seconds`; API responses include policy; UI labels transcript input as original-source seconds | PASS for documented policy |
| MH-8 | Integration, runner, reproducibility, live demo | Local HTTP API, OpenAPI contract, background rendering, output links, batch runner, Docker files, local UI | 18-test suite passes; source is committed on the public GitHub `main` branch. Docker not installed; port could not be exposed to the browser from this managed workspace; no public app deployment | FAIL (no verified live demo/deployment; Docker unverified) |
| CORE-1 | All must-haves pass | See MH rows | MH-2, MH-5 partial; MH-6 and MH-8 fail | FAIL |
| CORE-2 | Eight-step worked example on candidate-owned video | `scripts/demo_session.py` runs a shortened sequence against a generated test pattern | Synthetic sample is 8 seconds, not candidate-owned footage; no full official eight-step run | FAIL |
| CORE-3 | One single-speaker and one multi-speaker video | Transcript schema permits speaker label, but transcription/diarization not provided | No consented single-/multi-speaker video tested | FAIL |
| ADV-1 | Caption lifecycle and readability through cuts/speed | Word-ID anchored caption and renderer minimum duration | Unit movement/restore and render integration; no complete readability/clipping evaluation | PARTIAL |
| ADV-2 | Vague/reference and semantic instruction support | Limited phrase search, repeated pricing clarification and ordinal choice | API end-to-end pricing ambiguity test; no broad semantic search | PARTIAL |
| ADV-3 | Conflicts/repeated instructions/partial failure behavior | repeated cuts safe; unsupported single instructions rejected | Unit repeated/full-cut checks; no general multi-part instruction transaction support | PARTIAL |
| ADV-4 | Speaker-aware editing | Transcript stores speaker field | No speaker-aware parser/media tests | FAIL |
| OUT-1 | Noisy transcript, VFR, no-audio, overlap cases | Not implemented or verified | None | FAIL |
| OUT-2 | Fast instruction handling on 60-minute media | No long-media benchmark | None | FAIL |
| OUT-3 | OpenTimelineIO export | Not implemented | None | FAIL |
| OUT-4 | 40+ automated scenarios | 18 tests total | `py -m unittest discover -s tests -v`; no 40-scenario suite/CI | FAIL |
| INT-1 | One-command Docker startup and tests | Dockerfile and Compose file exist | Docker executable unavailable on host; not verified | FAIL |
| INT-2 | OpenAPI 3.1 and `/api/v1/` routes | `openapi.yaml`, `app/server.py` | E2E exercises actual `/api/v1/` routes; YAML not independently schema-validated | PARTIAL |
| INT-3 | Async job returns 202/job ID and poll | Thread-pool render endpoint | API E2E checks 202, returned job ID, polling to succeeded | PASS for render job |
| INT-4 | Idempotency-Key for POST | Server requires key, caches response by key | API E2E checks duplicate instruction and duplicate render idempotency | PASS for tested paths |
| INT-5 | Standard JSON error envelope | `envelope()` in API | Unit/API error envelope route not directly asserted | PARTIAL |
| INT-6 | Environment configuration and `.env.example` | Environment variables in server/Compose | Files inspected; no env override test | PARTIAL |
| INT-7 | File upload/output links | Local upload and output download routes | API E2E uploads source, renders and checks response links/manifest | PASS for local file flow |
| INT-8 | Structured logs, health and readiness | JSON request logs, `/health`, `/ready` | API E2E checks both health/readiness responses; log field/correlation format not asserted | PARTIAL |
| INT-9 | Output manifest | Render writes hash, durations, offsets, runtime, cost note, warnings and model list | `outputs/demo/synthetic_edited.mp4.manifest.json`; API E2E asserts hash and timing metrics | PARTIAL (versions/settings/licensing completeness needs improvement) |
| INT-10 | Batch/session runner | `scripts/run_session.py` accepts one file or directory, can start isolated API | `py scripts/run_session.py examples/demo_session.json --start-server --output outputs/session_runs` completed all nine example instructions, then downloaded the MP4 and manifest; raw results/snapshots/output files are under `outputs/session_runs/` and the summary is `evidence/session_runner_summary.json` | PASS for a one-file synthetic session |

## Verified local test result

Command: `py -m unittest discover -s tests -v`  
Result: **18 passed, 0 failed**, using Python 3.12 and the host FFmpeg/FFprobe; raw log: `evidence/full_test_run.log`.

The sample render is synthetic, not a human-recorded source. Its manifest and raw values are under `outputs/demo/`. The stream-start timestamp comparison does not measure perceived lip sync. See `REPORT.md` for exact limitations.
