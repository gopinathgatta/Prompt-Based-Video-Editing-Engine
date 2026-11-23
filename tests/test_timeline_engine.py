import hashlib
import unittest

from app.timeline.engine import TimelineEngine
from app.timeline.models import Segment, Timeline, TranscriptWord


def sample_engine():
    words = [
        TranscriptWord("w_welcome", "Welcome", 42.0, 42.35),
        TranscriptWord("w_to", "to", 42.36, 42.5),
        TranscriptWord("w_channel", "the channel", 42.51, 43.0),
        TranscriptWord("w_um", "um", 50.0, 50.2, filler=True),
        TranscriptWord("w_cost", "cost", 65.0, 65.5),
    ]
    timeline = Timeline(
        source_sha256=hashlib.sha256(b"synthetic fixture").hexdigest(),
        source_duration_s=120.0,
        frame_rate=30.0,
        words=words,
        segments=[Segment("source", 0.0, 120.0)],
    )
    return TimelineEngine(timeline)


class TimelineEngineTests(unittest.TestCase):
    def test_caption_word_anchor_moves_after_preceding_cut(self):
        engine = sample_engine()
        self.assertEqual(engine.add_caption("Welcome!", ["w_welcome", "w_to", "w_channel"]).status, "Applied")
        self.assertEqual(engine.cut(0, 30).status, "Applied")
        start, end = engine.word_positions()["w_welcome"]
        self.assertAlmostEqual(start, 12.0)
        self.assertAlmostEqual(end, 12.35)

    def test_caption_is_hidden_on_exact_cut_and_returns_when_source_is_restored(self):
        engine = sample_engine()
        engine.add_caption("Welcome!", ["w_welcome", "w_to", "w_channel"])
        engine.cut(41, 44)
        self.assertEqual(len(engine.timeline.captions), 1)
        self.assertEqual(engine.word_positions().get("w_welcome"), None)
        engine.restore_source_range(41, 44)
        self.assertEqual(len(engine.timeline.captions), 1)
        self.assertIn("w_welcome", engine.word_positions())

    def test_out_of_range_and_whole_video_cuts_are_rejected_without_mutation(self):
        engine = sample_engine()
        before = engine.timeline_hash()
        self.assertEqual(engine.cut(0, 120).status, "Rejected")
        self.assertEqual(engine.cut(121, 122).status, "Rejected")
        self.assertEqual(engine.timeline_hash(), before)

    def test_repeat_identical_cut_is_safe_noop(self):
        engine = sample_engine()
        engine.cut(30, 40)
        duration = engine.timeline.duration_s
        result = engine.cut(30, 40)
        self.assertEqual(result.status, "Applied")
        self.assertAlmostEqual(engine.timeline.duration_s, duration)

    def test_speed_changes_timeline_duration_not_source_anchors(self):
        engine = sample_engine()
        result = engine.speed(60, 90, 2)
        self.assertEqual(result.status, "Applied")
        self.assertAlmostEqual(engine.timeline.duration_s, 105)
        self.assertAlmostEqual(engine.word_positions()["w_cost"][0], 62.5)

    def test_restore_source_range_restores_content_without_reverting_other_edits(self):
        engine = sample_engine()
        engine.cut(0, 30)
        engine.speed(20, 30, 2)
        self.assertEqual(engine.restore_source_range(0, 30).status, "Applied")
        self.assertAlmostEqual(engine.timeline.duration_s, 115)
        self.assertAlmostEqual(engine.word_positions()["w_cost"][0], 60.0)

    def test_undo_and_redo_round_trip(self):
        engine = sample_engine()
        original = engine.timeline_hash()
        engine.cut(0, 10)
        edited = engine.timeline_hash()
        self.assertEqual(engine.undo().status, "Applied")
        self.assertEqual(engine.timeline_hash(), original)
        self.assertEqual(engine.redo().status, "Applied")
        self.assertEqual(engine.timeline_hash(), edited)

    def test_two_undos_follow_latest_active_edits_and_new_edit_clears_redo(self):
        engine = sample_engine()
        original = engine.timeline_hash()
        engine.cut(0, 10)
        after_first = engine.timeline_hash()
        engine.cut(20, 25)
        self.assertEqual(engine.undo().status, "Applied")
        self.assertEqual(engine.timeline_hash(), after_first)
        self.assertEqual(engine.undo().status, "Applied")
        self.assertEqual(engine.timeline_hash(), original)
        engine.redo()
        self.assertEqual(engine.timeline_hash(), after_first)
        engine.speed(0, 10, 2)
        self.assertEqual(engine.redo().status, "Rejected")

    def test_reorder_preserves_word_ids(self):
        engine = sample_engine()
        self.assertEqual(engine.reorder(40, 45, 0).status, "Applied")
        self.assertIn("w_welcome", [w.id for w in engine.visible_words()])
        self.assertAlmostEqual(engine.word_positions()["w_welcome"][0], 2.0)

    def test_invalid_caption_reference_is_rejected(self):
        engine = sample_engine()
        self.assertEqual(engine.add_caption("x", ["missing"]).status, "Rejected")

    def test_time_literals_are_current_timeline_seconds(self):
        engine = sample_engine()
        engine.cut(0, 30)
        engine.cut(20, 25)
        self.assertAlmostEqual(engine.timeline.duration_s, 85)
        self.assertEqual(engine.timeline.time_policy, "current_timeline_seconds")

    def test_identical_fixture_runs_have_identical_canonical_hash(self):
        results = []
        for _ in range(3):
            engine = sample_engine()
            engine.add_caption("Welcome!", ["w_welcome", "w_to", "w_channel"])
            engine.cut(0, 30)
            results.append(engine.timeline_hash())
        self.assertEqual(len(set(results)), 1)


if __name__ == "__main__":
    unittest.main()
