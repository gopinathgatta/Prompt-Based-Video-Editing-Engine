"""Reproducible local demo using generated synthetic media, never a real person."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.render import probe, render
from app.server import apply_instruction
from app.timeline.engine import TimelineEngine
from app.timeline.models import Segment, Timeline, TranscriptWord


OUT = ROOT / "outputs" / "demo"
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = OUT / "synthetic_source.mp4"
VIDEO = OUT / "synthetic_edited.mp4"


def main():
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=8",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(SOURCE),
    ], check=True)
    meta = probe(str(SOURCE))
    source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    words = [
        TranscriptWord("welcome", "Welcome", 3.0, 3.25),
        TranscriptWord("to", "to", 3.26, 3.4),
        TranscriptWord("the", "the", 3.41, 3.52),
        TranscriptWord("channel", "channel", 3.53, 4.0),
        TranscriptWord("pricing1", "pricing", 5.1, 5.5),
        TranscriptWord("pricing2", "cost", 6.4, 6.8),
        TranscriptWord("filler", "um", 7.1, 7.3, filler=True),
    ]
    timeline = Timeline(source_hash, meta["duration_s"], meta["frame_rate"], words, [Segment("source_0", 0, meta["duration_s"])])
    engine = TimelineEngine(timeline)
    run = []

    def record(instruction, result):
        row = result.as_dict()
        row["instruction"] = instruction
        run.append(row)
        return result

    record("Add a caption 'Welcome!' when I say welcome to the channel", apply_instruction(engine, "Add a caption 'Welcome!' when I say welcome to the channel"))
    record("Remove the pricing discussion", apply_instruction(engine, "Remove the pricing discussion"))
    record("Cut the first 1 seconds (short synthetic demo adaptation)", engine.cut(0, 1, "Cut the first 1 seconds (short synthetic demo adaptation)"))
    record("Speed up from 4 to 6 seconds by 2x", engine.speed(4, 6, 2))
    record("Restore the intro", engine.restore_source_range(0, 1))
    record("Undo the restoration", engine.undo())
    record("Make the caption red", engine.modify_caption(color="red"))
    manifest = render(engine, str(SOURCE), str(VIDEO))
    (OUT / "timeline.json").write_text(json.dumps(engine.timeline.as_dict(), indent=2), encoding="utf-8")
    (OUT / "results.json").write_text(json.dumps({"steps": run, "final_timeline_hash": engine.timeline_hash(), "final_duration_s": engine.timeline.duration_s}, indent=2), encoding="utf-8")
    print(json.dumps({"source": str(SOURCE), "rendered": str(VIDEO), "manifest": manifest, "results": str(OUT / "results.json"), "timeline_hash": engine.timeline_hash()}, indent=2))


if __name__ == "__main__":
    main()
