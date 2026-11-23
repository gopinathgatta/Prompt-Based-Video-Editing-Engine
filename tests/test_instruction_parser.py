import hashlib
import unittest

from app.server import apply_instruction
from app.timeline.engine import TimelineEngine
from app.timeline.models import Segment, Timeline, TranscriptWord


class InstructionParserTests(unittest.TestCase):
    def engine(self):
        return TimelineEngine(Timeline(
            source_sha256=hashlib.sha256(b"intro fixture").hexdigest(),
            source_duration_s=8.0,
            frame_rate=30.0,
            words=[],
            segments=[Segment("source", 0.0, 8.0)],
        ))

    def test_restore_intro_restores_only_the_missing_prefix(self):
        engine = self.engine()
        self.assertEqual(engine.cut(0, 1).status, "Applied")
        result = apply_instruction(engine, "Restore the intro")
        self.assertEqual(result.status, "Applied")
        self.assertAlmostEqual(engine.timeline.duration_s, 8.0)
        self.assertAlmostEqual(engine.timeline.segments[0].source_start_s, 0.0)
        self.assertAlmostEqual(engine.timeline.segments[0].source_end_s, 1.0)

    def test_restore_intro_does_not_duplicate_existing_source(self):
        result = apply_instruction(self.engine(), "Restore the introduction")
        self.assertEqual(result.status, "Rejected")

    def test_caption_color_change_is_applied_by_instruction_parser(self):
        engine = self.engine()
        engine.timeline.words = [TranscriptWord("welcome", "Welcome", 2.0, 2.3)]
        engine.add_caption("Welcome!", ["welcome"])
        result = apply_instruction(engine, "Change the existing caption to red")
        self.assertEqual(result.status, "Applied")
        self.assertEqual(engine.timeline.captions[0].color, "red")

    def test_caption_color_change_without_caption_is_rejected(self):
        result = apply_instruction(self.engine(), "Make the caption red")
        self.assertEqual(result.status, "Rejected")


if __name__ == "__main__":
    unittest.main()
