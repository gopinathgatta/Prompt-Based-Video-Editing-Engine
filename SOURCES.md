# Sources and licensing register

| Source | Use | License / commercial-use status | Verification / notes |
|---|---|---|---|
| Python 3.12 standard library | API, timeline, tests and scripts | Python Software Foundation License; commercial use allowed | No pip dependencies are listed in `requirements.txt`. |
| FFmpeg and FFprobe from host Gyan.FFmpeg.Essentials (FFmpeg 9.0.1) | Synthetic media generation, media probing, rendering | Host build is GPL-enabled and reports GPL v3 in `ffmpeg -L`; do not redistribute this host binary or claim LGPL-only deployment. Commercial use may be possible under GPL obligations; legal review is needed before distributing a product. | Host verification from `ffmpeg -version` and `ffmpeg -L`; Docker image installs Debian packages instead, exact resolved package versions not yet recorded. FFmpeg is dynamically invoked, not vendored. |
| `libx264` encoder in host FFmpeg | H.264 output encoding | GPL component; distribution obligations apply through the FFmpeg build | Enabled in the tested host build. |
| Liberation Sans fonts (Docker image package `fonts-liberation2`) | Caption text in container renderer | Liberation fonts are distributed under SIL Open Font License 1.1; preserve license/notice when redistributing font files. | Package is installed by Dockerfile; Docker image itself was not built/tested on this host. |
| Windows Arial at `C:/Windows/Fonts/arial.ttf` (host default) | Caption renderer default font | Microsoft font redistribution/commercial terms were not independently verified; host installation is not copied into project | For redistribution/container use, set `PS2_FONT_FILE` to an appropriately licensed font. |
| Pre-existing `app/timeline/models.py` and initial `app/timeline/engine.py` from task workspace | Core data model | Original author, source, license and provenance are unknown. Commercial-use rights cannot be verified from this workspace. | Candidate must establish source/author and compatible license before declaration or public redistribution. |
| Synthetic test pattern and sine tone generated with FFmpeg lavfi | Render/test fixture | Generated locally; no identifiable person or third-party recording | Reproducible by the checked-in test/demo commands. |
| Synthetic transcript in tests and demo | Timeline test content | Authored as test strings; no real person's speech | Not a ground-truth transcription benchmark. |
| IncuBrix PS2 brief and submission workbook | Requirements and scoring | Candidate-provided assessment materials; confidential handling presumed; excluded from repository | Original files remain under `work/`. |
| ChatGPT Work / Codex assistance | Code review, code edits, tests, documentation and evidence preparation | AI tool use disclosed in `AI_USE.md`; candidate must review and be able to explain work | No provider API was called by the application. |

No speech model, dataset, external API, stock media, uploaded human media, or third-party project dependency is used by the verified local test run. The existing timeline core's provenance is a material unresolved licensing issue.
