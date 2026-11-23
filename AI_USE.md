# AI use and service cost disclosure

- **Assistant:** ChatGPT Work / Codex (GPT-6), used in this conversation to inspect the official brief/workbook, implement and review portions of the project, create tests, run the local suite, and prepare documentation/evidence.
- **Application model/provider:** None. The application uses deterministic local parsing rules; no LLM API is called.
- **Transcription/diarization:** None. Word-level transcripts are manually supplied by a user. The demo transcript is synthetic and does not claim recognized speech.
- **Code and content:** The existing timeline model and initial engine were already present in the workspace at the start. Their original authoring tool, author, and license are unknown. Changes to the engine, server, renderer, UI, tests, and docs were made with ChatGPT Work assistance and must be reviewed by the candidate.
- **Prompting and human review:** Natural-language example prompts were authored for the assessment flow. Candidate must review every implementation and personally verify each claim before submission/live session.
- **Generated media:** FFmpeg lavfi generated a colored test pattern and sine tone only; no generated human voice, face, or likeness.
- **Paid services and cost:** No paid external service or API was used by the test/demo flow. No external API charge was incurred in recorded work. Local electricity/hardware cost and FFmpeg runtime cost were not monetized; per-minute cost is unknown/not measured.
- **Testing of AI-assisted work:** `py -m unittest discover -s tests -v` passed 18 tests on 2026-11-22 local system time. The synthetic API session runner also completed nine example instructions and a render. Coverage and limitations are recorded in `TRACEABILITY.md`; these checks do not prove transcription accuracy, perceived sync, deployment or licensing.
