# Requirement traceability

| Requirement | Component | Test/evidence | Status |
|---|---|---|---|
| Preserve original | `Timeline.source.sha256` | `engine.py` | Partial |
| Content anchoring | `anchor_word_ids` | `test_caption_and_style` | Partial |
| Three responses | `Engine.respond` | unit tests | Partial |
| Determinism | canonical JSON SHA-256 | `test_same_initial_hash` | Partial |
| Undo/redo | immutable snapshots | `test_undo` | Partial |
| Renderer accuracy | — | — | Not implemented |
| Full Integration Standard | HTTP baseline | `server.py` | Partial |
