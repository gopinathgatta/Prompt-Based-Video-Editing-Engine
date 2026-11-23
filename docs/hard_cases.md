# Official hard-case scenarios and execution record

The scenario statements below preserve the workbook's wording. **Not tested** means no full scenario session was run; related unit/API checks are described in `TRACEABILITY.md` and must not be mistaken for a pass.

1. **Partial:** “A caption added, then the exact sentence under it cut; then that cut restored (the caption should come back).” The engine lifecycle is unit-tested; rendered pixel assertion is absent.
2. **Partial:** “A section reordered, then a word inside it muted; filler removal cutting into a bleeped word.” Reorder and mute paths exist; bleep is rejected, so the full scenario is not met.
3. **Partial:** “"Remove 0:30-0:40" sent twice; "add a caption at 5:00" on a shorter video; times as "80 seconds", "a minute twenty", "the last 10 seconds".” Repeat cut and current-time policy are tested; remaining language/caption cases are not.
4. **Not tested:** “"Undo the second-to-last cut but keep the music"; "make it bigger" when no caption exists.” Specific historical-edit undo with unrelated music preservation is not implemented.
5. **Partial:** “"Remove everything after I say thanks" where thanks is said four times.” Pricing/cost duplicate clarification is tested, not this phrase or four-match case.
6. **Partial:** “"Speed up 10x", "cut everything", and a three-part instruction where one part is impossible.” Full cut is tested as a rejection; 10x/multi-part behavior is not comprehensively tested.
7. **Not tested:** “A two-speaker video with a speaker-label swap, overlapping speech, background music, and a phone video with variable frame rate.” No such media is included; music ducking and diarization are not implemented.

Automated suite result: 14 tests passed on synthetic timeline/video fixtures. The official seven scenarios have **not** all passed. No scenario evidence was altered to imply otherwise.
