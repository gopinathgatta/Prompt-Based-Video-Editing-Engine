import unittest
from engine import Engine
class EngineTest(unittest.TestCase):
 def test_same_initial_hash(self): self.assertEqual(Engine().timeline.hash(),Engine().timeline.hash())
 def test_caption_and_style(self):
  e=Engine();self.assertEqual(e.apply("Add a caption 'Welcome!' when I say welcome to the channel")['status'],'applied');self.assertEqual(e.apply('Make that caption red')['status'],'applied');self.assertEqual(e.timeline.captions[0]['style']['color'],'#ef4444')
 def test_undo(self):
  e=Engine();e.apply('Cut the first 30 seconds');e.apply('Undo');self.assertFalse(e.timeline.cuts)
 def test_pricing_is_safe(self): self.assertEqual(Engine().apply('Remove the part about pricing')['status'],'needs_clarification')
 def test_invalid_speed(self): self.assertEqual(Engine().apply('Speed up from 1:00 to 1:30 by 10x')['status'],'rejected')
 def test_clarification_answer_is_applied(self):
  e=Engine();self.assertEqual(e.apply('Remove the part about pricing')['status'],'needs_clarification');self.assertEqual(e.apply('the second one')['status'],'applied');self.assertEqual(len(e.timeline.cuts),1)
 def test_restore_preserves_speed(self):
  e=Engine();e.apply('Cut the first 30 seconds');e.apply('Speed up from 1:00 to 1:30 by 2x');e.apply('Actually, put the intro back');self.assertFalse(e.timeline.cuts);self.assertEqual(len(e.timeline.speeds),1)
