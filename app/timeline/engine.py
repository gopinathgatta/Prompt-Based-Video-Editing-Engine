from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .models import Caption, EditStep, Segment, Timeline, TranscriptWord


@dataclass
class OperationResponse:
    status: Literal["Applied", "Needs clarification", "Rejected"]
    operations: list[dict[str, Any]] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    duration_s: float | None = None
    moved_or_changed: list[str] = field(default_factory=list)
    timeline_hash: str | None = None
    warnings: list[str] = field(default_factory=list)
    question: str | None = None
    options: list[str] = field(default_factory=list)
    reason: str | None = None
    time_policy: str = "current edited timeline seconds"

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "operations": self.operations, "before": self.before,
                "after": self.after, "duration_s": self.duration_s,
                "moved_or_changed": self.moved_or_changed, "timeline_hash": self.timeline_hash,
                "warnings": self.warnings, "question": self.question, "options": self.options,
                "reason": self.reason, "time_policy": self.time_policy}


class TimelineEngine:
    """Deterministic transformations over immutable source-time references.

    Time literals supplied to operations use current edited timeline seconds. Effects
    reference stable transcript word IDs, so their presentation follows segment order.
    """
    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self._undo_snapshots: list[tuple[dict[str, Any], EditStep]] = []
        self._redo_snapshots: list[tuple[dict[str, Any], dict[str, Any], EditStep]] = []
        self._validate()

    def _validate(self) -> None:
        t = self.timeline
        if t.source_duration_s <= 0 or t.frame_rate <= 0:
            raise ValueError("source duration and frame rate must be positive")
        word_ids = [w.id for w in t.words]
        if len(word_ids) != len(set(word_ids)):
            raise ValueError("transcript word ids must be unique")
        for s in t.segments:
            if s.source_start_s < 0 or s.source_end_s <= s.source_start_s or s.source_end_s > t.source_duration_s + 1e-6:
                raise ValueError("segment source range is invalid")
            if not 0.25 <= s.speed <= 4.0:
                raise ValueError("speed must be between 0.25x and 4x")
        for c in t.captions:
            if any(wid not in set(word_ids) for wid in c.word_ids):
                raise ValueError(f"caption {c.id} refers to an unknown word")

    def canonical_json(self) -> str:
        d = self.timeline.as_dict()
        # Operational history metadata doesn't affect current visual/edit state.
        d.pop("history", None); d.pop("redo_stack", None); d.pop("rendering", None)
        # Segment IDs are implementation details; canonical timeline identity uses ordered media ranges.
        d["segments"] = [{k:v for k,v in seg.items() if k != "id"} for seg in d["segments"]]
        d["overlays"] = [{k:v for k,v in item.items() if k != "id"} for item in d["overlays"]]
        return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def timeline_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def _clock(self) -> list[tuple[Segment, float, float]]:
        out, pos = [], 0.0
        for s in self.timeline.segments:
            end = pos + s.duration_s
            out.append((s, pos, end)); pos = end
        return out

    def _current_range_to_source(self, start: float, end: float) -> list[Segment]:
        if start < 0 or end <= start or end > self.timeline.duration_s + 1e-6:
            raise ValueError(f"invalid current timeline range [{start}, {end}] for duration {self.timeline.duration_s:.3f}")
        result = []
        for seg, cur0, cur1 in self._clock():
            a, b = max(start, cur0), min(end, cur1)
            if b <= a: continue
            src_a = seg.source_start_s + (a-cur0)*seg.speed
            src_b = seg.source_start_s + (b-cur0)*seg.speed
            sid = hashlib.sha256(f"{src_a:.9f}:{src_b:.9f}:{seg.speed:.9f}".encode()).hexdigest()[:16]
            result.append(Segment(sid, src_a, src_b, seg.speed))
        return result

    def _remove_current_ranges(self, ranges: list[tuple[float, float]]) -> None:
        # Applying ranges from right to left keeps earlier current-time coordinates stable.
        for start, end in sorted(ranges, reverse=True):
            if start < 0 or end <= start or end > self.timeline.duration_s + 1e-6:
                raise ValueError(f"invalid current timeline range [{start}, {end}]")
            kept=[]
            for seg,a,b in self._clock():
                if b <= start or a >= end:
                    kept.append(copy.deepcopy(seg)); continue
                if a < start: kept.extend(self._current_range_to_source(a,start))
                if b > end: kept.extend(self._current_range_to_source(end,b))
            if not kept: raise ValueError("whole-video cuts are not allowed")
            self.timeline.segments=kept

    def _snapshot(self) -> dict[str, Any]:
        t = self.timeline
        return {"segments": copy.deepcopy(t.segments), "captions": copy.deepcopy(t.captions),
                "overlays": copy.deepcopy(t.overlays), "audio_effects": copy.deepcopy(t.audio_effects),
                "background_music": copy.deepcopy(t.background_music), "deliberate_pauses": copy.deepcopy(t.deliberate_pauses),
                "warnings": copy.deepcopy(t.warnings)}

    def _restore_snapshot(self, snap: dict[str, Any]) -> None:
        for k, v in snap.items(): setattr(self.timeline, k, copy.deepcopy(v))

    def _apply(self, instruction: str, op: dict[str, Any], fn) -> OperationResponse:
        before_d = self.timeline.duration_s; before_hash = self.timeline_hash(); old = self._snapshot()
        try: moved = fn()
        except (ValueError, KeyError) as exc:
            self._restore_snapshot(old)
            return OperationResponse("Rejected", before={"duration_s": before_d}, after={"duration_s": before_d},
                                     duration_s=before_d, timeline_hash=before_hash, reason=str(exc))
        self.timeline.redo_stack.clear()
        self._redo_snapshots.clear()
        step = EditStep(str(uuid.uuid4()), instruction, copy.deepcopy(op), before_hash, "")
        self._undo_snapshots.append((old, step))
        warnings = self._reconcile_captions()
        step.after_hash = self.timeline_hash()
        self.timeline.history.append(step)
        return OperationResponse("Applied", [op], {"duration_s": before_d}, {"duration_s": self.timeline.duration_s},
                                 self.timeline.duration_s, moved if isinstance(moved, list) else [str(moved)],
                                 self.timeline_hash(), warnings)

    def _reconcile_captions(self) -> list[str]:
        present = {w.id for w in self.visible_words()}
        warnings=[]
        for c in self.timeline.captions:
            visible = [x for x in c.word_ids if x in present]
            if not visible:
                # Keep the original anchor IDs in the edit state. If the source
                # range is restored later, the caption becomes visible again.
                warnings.append(f"Caption {c.id} is temporarily hidden because all anchored words were cut; restoring those words restores the caption.")
            elif len(visible) < len(c.word_ids):
                warnings.append(f"Caption {c.id} follows the remaining anchored words (partial-cut rule); hidden anchors remain available for restore.")
        return warnings

    def visible_words(self) -> list[TranscriptWord]:
        words=[]
        for seg in self.timeline.segments:
            words.extend(w for w in self.timeline.words if w.start_s >= seg.source_start_s-1e-6 and w.end_s <= seg.source_end_s+1e-6)
        return words

    def word_positions(self) -> dict[str, tuple[float,float]]:
        pos={}; clock=self._clock()
        for seg, cur0, _ in clock:
            for w in self.timeline.words:
                if w.start_s >= seg.source_start_s-1e-6 and w.end_s <= seg.source_end_s+1e-6:
                    pos[w.id]=(cur0+(w.start_s-seg.source_start_s)/seg.speed, cur0+(w.end_s-seg.source_start_s)/seg.speed)
        return pos

    def cut(self, start: float, end: float, instruction="cut range") -> OperationResponse:
        op={"type":"cut","start_s":start,"end_s":end,"time_policy":self.timeline.time_policy}
        if self.timeline.history and self.timeline.history[-1].active and self.timeline.history[-1].operation==op:
            return OperationResponse("Applied",[],{"duration_s":self.timeline.duration_s},{"duration_s":self.timeline.duration_s},self.timeline.duration_s,["identical cut already applied"],self.timeline_hash(),["Repeated identical cut treated as a no-op."])
        def change():
            removed=self._current_range_to_source(start,end); kept=[]
            self._remove_current_ranges([(start,end)])
            return [f"removed source {x.source_start_s:.3f}-{x.source_end_s:.3f}s" for x in removed]
        return self._apply(instruction,op,change)

    def cut_ranges(self, ranges: list[tuple[float,float]], instruction="cut ranges") -> OperationResponse:
        op={"type":"cut_ranges","ranges":[[a,b] for a,b in ranges],"time_policy":self.timeline.time_policy}
        def change():
            self._remove_current_ranges(ranges)
            return [f"removed {len(ranges)} current-timeline range(s)"]
        return self._apply(instruction,op,change)

    def keep(self, start: float, end: float) -> OperationResponse:
        op={"type":"keep","start_s":start,"end_s":end,"time_policy":self.timeline.time_policy}
        def change(): self.timeline.segments=self._current_range_to_source(start,end); return ["kept requested range"]
        return self._apply("keep only range",op,change)

    def restore_source_range(self, start: float, end: float) -> OperationResponse:
        op={"type":"restore_source_range","source_start_s":start,"source_end_s":end}
        def change():
            if start<0 or end<=start or end>self.timeline.source_duration_s: raise ValueError("invalid original source range")
            if any(max(start,s.source_start_s)<min(end,s.source_end_s) for s in self.timeline.segments):
                raise ValueError("requested source range is already present or partially present")
            sid=hashlib.sha256(f"{start:.9f}:{end:.9f}:1.000000000".encode()).hexdigest()[:16]
            seg=Segment(sid,start,end,1.0)
            index=next((i for i,s in enumerate(self.timeline.segments) if s.source_start_s>=end),len(self.timeline.segments))
            self.timeline.segments.insert(index,seg)
            return [f"restored original source range {start:.3f}-{end:.3f}s in source order"]
        return self._apply("restore original source range",op,change)

    def speed(self, start: float, end: float, factor: float) -> OperationResponse:
        op={"type":"speed","start_s":start,"end_s":end,"factor":factor,"time_policy":self.timeline.time_policy}
        def change():
            if not 0.25 <= factor <= 4: raise ValueError("speed factor must be between 0.25x and 4x")
            if start < 0 or end <= start or end > self.timeline.duration_s + 1e-6: raise ValueError("invalid current timeline speed range")
            new=[]
            for seg,a,b in self._clock():
                if b<=start or a>=end: new.append(copy.deepcopy(seg)); continue
                if a<start: new.extend(self._current_range_to_source(a,start))
                left,right=max(start,a),min(end,b)
                src_a=seg.source_start_s+(left-a)*seg.speed
                src_b=seg.source_start_s+(right-a)*seg.speed
                sid=hashlib.sha256(f"{src_a:.9f}:{src_b:.9f}:{factor:.9f}".encode()).hexdigest()[:16]
                new.append(Segment(sid,src_a,src_b,factor))
                if b>end: new.extend(self._current_range_to_source(end,b))
            self.timeline.segments=new; return [f"changed range to {factor}x"]
        return self._apply("change speed",op,change)

    def reorder(self, start: float, end: float, before: float) -> OperationResponse:
        op={"type":"reorder","start_s":start,"end_s":end,"before_s":before,"time_policy":self.timeline.time_policy}
        def change():
            if before<0 or before>self.timeline.duration_s or start<0 or end<=start or end>self.timeline.duration_s: raise ValueError("invalid reorder range")
            if start<=before<=end: raise ValueError("destination overlaps the moved range")
            moved=self._current_range_to_source(start,end); remain=[]
            for seg,a,b in self._clock():
                if b<=start or a>=end: remain.append(copy.deepcopy(seg)); continue
                if a<start: remain.extend(self._current_range_to_source(a,start))
                if b>end: remain.extend(self._current_range_to_source(end,b))
            dest=before if before<start else before-(end-start)
            prefix=[]; suffix=[]; cursor=0
            for seg in remain:
                d=seg.duration_s
                if cursor+d<=dest: prefix.append(seg)
                elif cursor>=dest: suffix.append(seg)
                else:
                    split=cursor+(dest-cursor)
                    prefix.extend(self._current_range_to_source(cursor,split)); suffix.extend(self._current_range_to_source(split,cursor+d))
                cursor+=d
            self.timeline.segments=prefix+moved+suffix; return ["moved section; word anchors retained"]
        return self._apply("reorder section",op,change)

    def add_caption(self, text: str, word_ids: list[str]) -> OperationResponse:
        if not word_ids: return OperationResponse("Needs clarification",question="Which spoken words should this caption follow?",options=["Select transcript words"] ,timeline_hash=self.timeline_hash())
        op={"type":"caption.add","text":text,"word_ids":word_ids}
        def change():
            known={w.id for w in self.timeline.words}
            if not set(word_ids)<=known: raise ValueError("caption contains an unknown word reference")
            if not set(word_ids)<=set(self.word_positions()): raise ValueError("caption anchors must be visible transcript words")
            if any(c.id=="caption_1" for c in self.timeline.captions): raise ValueError("caption already exists; specify which caption to modify")
            self.timeline.captions.append(Caption("caption_1",text,list(word_ids))); return [f"caption anchored to {len(word_ids)} word(s)"]
        return self._apply("add caption",op,change)

    def modify_caption(self, color: str | None=None, text: str | None=None, caption_id="caption_1") -> OperationResponse:
        op={"type":"caption.modify","caption_id":caption_id,"color":color,"text":text}
        def change():
            c=next((x for x in self.timeline.captions if x.id==caption_id),None)
            if not c: raise ValueError(f"no caption named {caption_id} exists")
            if color: c.color=color
            if text: c.text=text
            return [f"modified {caption_id}"]
        return self._apply("modify caption",op,change)

    def add_overlay(self,text:str,start:float,end:float,word_ids:list[str]|None=None) -> OperationResponse:
        op={"type":"overlay.add","text":text,"start_s":start,"end_s":end,"word_ids":word_ids or []}
        def change():
            if start<0 or end<=start or end>self.timeline.duration_s: raise ValueError("overlay range is invalid")
            if word_ids and not set(word_ids)<=set(self.word_positions()): raise ValueError("overlay word anchors must be visible transcript words")
            oid=hashlib.sha256(f"{text}:{start:.9f}:{end:.9f}".encode()).hexdigest()[:16]
            self.timeline.overlays.append({"id":oid,"text":text,"start_s":start,"end_s":end,"word_ids":list(word_ids or [])}); return ["added text overlay" + (" anchored to transcript words" if word_ids else " at the requested current-timeline time")]
        return self._apply("add text overlay",op,change)

    def audio_word(self, word_ids:list[str], effect:Literal["mute","bleep"]) -> OperationResponse:
        op={"type":f"audio.{effect}","word_ids":word_ids}
        def change():
            visible={w.id for w in self.visible_words()};
            if not word_ids or not set(word_ids)<=visible: raise ValueError("audio effect needs visible, valid word references")
            self.timeline.audio_effects.append({"type":effect,"word_ids":list(word_ids)}); return [f"{effect} attached to {len(word_ids)} word(s)"]
        return self._apply(f"{effect} words",op,change)

    def auto_caption(self) -> OperationResponse:
        groups=[]; words=self.visible_words()
        for i in range(0,len(words),7): groups.append(words[i:i+7])
        op={"type":"caption.auto","group_size":7}
        def change():
            self.timeline.captions=[Caption(f"auto_{i+1}"," ".join(w.text for w in group),[w.id for w in group]) for i,group in enumerate(groups)]
            return [f"created {len(groups)} word-anchored captions"]
        return self._apply("auto-caption",op,change)

    def remove_fillers(self) -> OperationResponse:
        targets=[w for w in self.visible_words() if w.filler and w.text.lower().strip(".,!?;:") in {"um","uh","like"}]
        op={"type":"remove_fillers","word_ids":[w.id for w in targets]}
        if not targets: return OperationResponse("Applied",[op],{"duration_s":self.timeline.duration_s},{"duration_s":self.timeline.duration_s},self.timeline.duration_s,[],self.timeline_hash(),["No transcript words were confidently labeled as fillers."])
        # Map source word ranges into current edited clock, then cut in reverse order.
        mapped=[]
        for w in targets:
            for seg,a,b in self._clock():
                if w.start_s>=seg.source_start_s and w.end_s<=seg.source_end_s:
                    mapped.append((a+(w.start_s-seg.source_start_s)/seg.speed,a+(w.end_s-seg.source_start_s)/seg.speed)); break
        def change():
            self._remove_current_ranges(mapped)
            return [f"removed {len(targets)} filler word(s)"]
        return self._apply("remove filler words",op,change)

    def remove_silences(self, ranges:list[tuple[float,float]], threshold_s:float) -> OperationResponse:
        if threshold_s<=0: return OperationResponse("Rejected",reason="silence threshold must be positive",timeline_hash=self.timeline_hash())
        eligible=[(a,b) for a,b in ranges if b-a>threshold_s and not any(max(a,x)<min(b,y) for x,y in self.timeline.deliberate_pauses)]
        if not eligible: return OperationResponse("Applied",duration_s=self.timeline.duration_s,timeline_hash=self.timeline_hash(),warnings=["No qualifying non-deliberate silences found."])
        op={"type":"remove_silences","ranges":eligible,"threshold_s":threshold_s}
        def change():
            self._remove_current_ranges(eligible)
            return [f"removed {len(eligible)} silence(s)"]
        return self._apply("remove silences",op,change)

    def add_music(self,source:str,level_db:float=-18.0) -> OperationResponse:
        op={"type":"music.add","source":source,"level_db":level_db,"duck_under_speech":True}
        def change(): self.timeline.background_music={"source":source,"level_db":level_db,"duck_under_speech":True}; return ["added background music with speech ducking"]
        return self._apply("add background music",op,change)

    def undo(self) -> OperationResponse:
        if not self.timeline.history or not self._undo_snapshots:
            return OperationResponse("Rejected",reason="nothing to undo",timeline_hash=self.timeline_hash())
        snap,step=self._undo_snapshots.pop(); current=self._snapshot()
        self._redo_snapshots.append((snap,current,step)); self._restore_snapshot(snap); step.active=False
        return OperationResponse("Applied",[{"type":"undo","edit_id":step.id}],duration_s=self.timeline.duration_s,timeline_hash=self.timeline_hash(),moved_or_changed=[f"undid {step.instruction}"])

    def redo(self) -> OperationResponse:
        if not self._redo_snapshots: return OperationResponse("Rejected",reason="nothing to redo",timeline_hash=self.timeline_hash())
        _before,after,step=self._redo_snapshots.pop(); self._undo_snapshots.append((_before,step)); step.active=True
        self._restore_snapshot(after)
        return OperationResponse("Applied",[{"type":"redo"}],duration_s=self.timeline.duration_s,timeline_hash=self.timeline_hash(),moved_or_changed=["redid latest edit"])

    def undo_second_to_last_cut_keep_music(self) -> OperationResponse:
        """Undo an earlier cut while preserving a later music-addition edit.

        This deliberately handles the stated compound instruction rather than
        silently undoing the most recent operation. Later edits must be music
        additions only; other dependencies require a clarification.
        """
        active = [(i, step) for i, step in enumerate(self.timeline.history) if step.active]
        cut_positions = [(i, step) for i, step in active if step.operation.get("type") in {"cut", "cut_ranges"}]
        if not cut_positions:
            return OperationResponse("Needs clarification", reason="There is no active cut to undo.", timeline_hash=self.timeline_hash(), duration_s=self.timeline.duration_s)
        target_index, target = cut_positions[-1]
        later = [step for i, step in active if i > target_index]
        if not later or any(step.operation.get("type") != "music.add" for step in later):
            return OperationResponse("Needs clarification", question="I can preserve only later background-music edits for this targeted undo. Which edit should be undone?", options=["Undo the latest edit"] , timeline_hash=self.timeline_hash(), duration_s=self.timeline.duration_s)
        snapshot_pos = next((i for i, (_, step) in enumerate(self._undo_snapshots) if step.id == target.id), None)
        if snapshot_pos is None:
            return OperationResponse("Rejected", reason="The requested historical cut cannot be restored in this session.", timeline_hash=self.timeline_hash(), duration_s=self.timeline.duration_s)
        before, _ = self._undo_snapshots[snapshot_pos]
        restored = copy.deepcopy(before)
        restored["background_music"] = copy.deepcopy(self.timeline.background_music)
        self._restore_snapshot(restored)
        target.active = False
        self._undo_snapshots.pop(snapshot_pos)
        for i, (snap, step) in enumerate(self._undo_snapshots):
            if step.operation.get("type") == "music.add":
                self._undo_snapshots[i] = (copy.deepcopy(before), step)
        return OperationResponse("Applied", [{"type": "undo.specific", "edit_id": target.id, "preserved": ["music.add"]}], duration_s=self.timeline.duration_s, timeline_hash=self.timeline_hash(), moved_or_changed=["undid the second-to-last cut and preserved background music"])

    def response(self, status="Applied", **kw) -> OperationResponse:
        return OperationResponse(status,timeline_hash=self.timeline_hash(),duration_s=self.timeline.duration_s,**kw)
