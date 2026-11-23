# How timeline anchors work

The original media is treated as a fixed source. Each timeline segment stores an original-source interval `[source_start_s, source_end_s)` plus a playback speed. Segments are ordered; the current timeline start of each segment is the sum of the durations before it, where duration is `(source_end_s - source_start_s) / speed`.

Transcript words keep stable IDs and original-source start/end times. To locate a word in the edited timeline, the engine finds the segment containing the full word and maps source offset into the segment's current-time offset using the segment speed. A cut splits or removes source intervals; it does not rewrite word IDs or transcript times. Reorder changes segment order. Speed changes segment duration. Caption records store word IDs instead of a screen coordinate, so a preceding cut or reorder moves the caption with those words. A caption whose anchors are all cut is hidden but retained; restoring the source interval makes it visible again.

Numeric time literals accepted by the core are **current edited-timeline seconds**. The source-restore operation is explicit and accepts **original-source seconds**. The core has no natural-language parser yet, so it cannot safely interpret formats such as “a minute twenty” or resolve repeated semantic matches.

This is a data-model explanation, not evidence of a real rendered result. Caption rendering, audio effects, media ingest, and persistent history remain unimplemented.
