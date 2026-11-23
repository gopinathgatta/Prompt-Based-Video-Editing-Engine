"""Deterministic, content-anchored timeline editor. No model mutates state."""
from __future__ import annotations
import copy, hashlib, json, re, uuid
from dataclasses import dataclass, field, asdict

TIME_POLICY = "original_source_time"

def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def demo_words():
    rows=[("welcome",42,42.4),("to",42.4,42.6),("the",42.6,42.8),("channel",42.8,43.2),("pricing",65,65.4),("cost",140,140.4),("pricing",195,195.5),("thanks",220,220.3),("thanks",240,240.3)]
    return [{"id":f"w{i:03d}","text":t,"start":s,"end":e,"speaker":"host","confidence":.98} for i,(t,s,e) in enumerate(rows)]

@dataclass
class Timeline:
    source: dict
    transcript: list
    duration: float = 300.0
    cuts: list = field(default_factory=list)
    speeds: list = field(default_factory=list)
    captions: list = field(default_factory=list)
    audio_effects: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    version: str = "1.0"
    def data(self): return asdict(self)
    def hash(self): return canonical_hash(self.data())
    def visible(self, start, end):
        return not any(c["start"] <= start and end <= c["end"] for c in self.cuts)
    def effective_duration(self):
        cut=sum(c["end"]-c["start"] for c in self.cuts)
        delta=sum((s["end"]-s["start"])*(1-1/s["factor"]) for s in self.speeds)
        return round(self.duration-cut-delta, 3)

class Engine:
    def __init__(self, source_url="mock://talking-head.mp4", duration=300, transcript=None):
        digest=hashlib.sha256(source_url.encode()).hexdigest()
        self.timeline=Timeline({"url":source_url,"sha256":digest,"immutable":True}, transcript or demo_words(), float(duration))
        self.history=[]; self.redo=[]; self.last_caption=None; self.pending=None
    def snapshot(self): return copy.deepcopy(self.timeline)
    def respond(self,status,operations=None,summary="",question=None,options=None,warnings=None):
        return {"status":status,"operations":operations or [],"summary":summary,"question":question,"options":options or [],"warnings":warnings or [],"time_policy":TIME_POLICY,"timeline_hash":self.timeline.hash(),"duration_s":self.timeline.effective_duration()}
    def commit(self, kind, instruction, before, operation):
        self.history.append({"id":str(uuid.uuid4()),"type":kind,"instruction":instruction,"before":before,"after":self.snapshot(),"operation":operation})
        self.redo.clear()
    def _range(self, text):
        vals=re.findall(r"(?:\d+:)?\d+(?:\.\d+)?",text)
        if len(vals)<2:return None
        def sec(v):
            p=v.split(":"); return float(p[-1])+(60*float(p[-2]) if len(p)>1 else 0)
        return sec(vals[0]),sec(vals[1])
    def _matches(self, term):
        aliases={"pricing":{"pricing","cost"},"cost":{"pricing","cost"}}
        return [w for w in self.timeline.transcript if w["text"].lower() in aliases.get(term,{term})]
    def apply(self, instruction):
        text=instruction.strip(); low=text.lower(); before=self.snapshot()
        # A clarification answer is intentionally a separate deterministic state transition.
        if self.pending:
            pending=self.pending; self.pending=None
            if pending["kind"]=="content_cut":
                choice=low.replace("the ","").replace(" one","").strip()
                matches=pending["matches"]
                if choice=="all": selected=matches
                elif choice.isdigit() and 1<=int(choice)<=len(matches): selected=[matches[int(choice)-1]]
                elif "second" in choice and len(matches)>=2: selected=[matches[1]]
                elif "first" in choice: selected=[matches[0]]
                elif "third" in choice and len(matches)>=3: selected=[matches[2]]
                else:
                    self.pending=pending
                    return self.respond("needs_clarification",summary="Please choose one of the listed occurrences or all.",question=pending["question"],options=pending["options"])
                ops=[]
                for w in selected:
                    op={"start":max(0,w["start"]-.15),"end":min(self.timeline.duration,w["end"]+.15),"anchor":"word:"+w["id"]}
                    if not any(c["start"]==op["start"] and c["end"]==op["end"] for c in self.timeline.cuts): self.timeline.cuts.append(op);ops.append({"type":"cut",**op})
                self.commit("cut_content",pending["instruction"],before,{"matches":[w["id"] for w in selected]})
                return self.respond("applied",ops,f"Cut {len(ops)} selected content occurrence(s).")
        if low == "undo":
            if not self.history:return self.respond("rejected",summary="There is no applied edit to undo.")
            step=self.history.pop(); self.redo.append(step); self.timeline=copy.deepcopy(step["before"])
            return self.respond("applied",[{"type":"undo","target":step["id"]}],f"Undid {step['type']}.")
        if low == "redo":
            if not self.redo:return self.respond("rejected",summary="There is no edit to redo.")
            step=self.redo.pop(); self.history.append(step); self.timeline=copy.deepcopy(step["after"])
            return self.respond("applied",[{"type":"redo","target":step["id"]}],f"Redid {step['type']}.")
        if "put the intro back" in low or "put back what i removed" in low or low.startswith("restore"):
            candidates=[h for h in self.history if h["type"] in ("cut","cut_content","remove_filler","remove_silence")]
            if not candidates:return self.respond("rejected",summary="There is no prior removable edit to restore.")
            target=candidates[-1]
            # Restore removes only the target cut(s), retaining every other later edit.
            if target["type"]=="cut":
                op=target["operation"]; self.timeline.cuts=[c for c in self.timeline.cuts if not (c["start"]==op["start"] and c["end"]==op["end"])]
            elif target["type"]=="cut_content":
                ids=set(target["operation"]["matches"]);self.timeline.cuts=[c for c in self.timeline.cuts if c.get("anchor","").removeprefix("word:") not in ids]
            else: self.timeline.cuts=[c for c in self.timeline.cuts if c.get("history_id")!=target["id"]]
            op={"target_history_id":target["id"]};self.commit("restore",text,before,op)
            return self.respond("applied",[{"type":"restore",**op}],"Restored the selected earlier cut while preserving unrelated edits.")
        if low.startswith("render"):
            return self.respond("applied",[{"type":"render_plan"}],"Render plan generated; external FFmpeg execution is not enabled in this local build.",warnings=["RENDER_NOT_EXECUTED"])
        if "caption" in low and ("add" in low or "when i say" in low):
            quoted=re.findall(r"['\"]([^'\"]+)['\"]",text); label=quoted[0] if quoted else "Caption"
            phrase=low.split("when i say",1)[-1].strip(" .!?'")
            words=[w for w in self.timeline.transcript if w["text"].lower() in phrase.split()]
            if not words:return self.respond("rejected",summary="No matching transcript words were found.")
            cap={"id":str(uuid.uuid4()),"text":label,"anchor_word_ids":[w["id"] for w in words],"style":{"color":"#f8fafc","size":36}}
            self.timeline.captions.append(cap); self.last_caption=cap["id"]; self.commit("add_caption",text,before,cap)
            return self.respond("applied",[{"type":"add_caption","id":cap["id"]}],f"Caption attached to {len(words)} source words.")
        if "make that caption red" in low:
            cap=next((c for c in self.timeline.captions if c["id"]==self.last_caption),None)
            if not cap:return self.respond("needs_clarification",summary="No caption is selected.",question="Which caption should be changed?",options=[])
            cap["style"]["color"]="#ef4444"; self.commit("style_caption",text,before,{"id":cap["id"],"color":"red"})
            return self.respond("applied",[{"type":"style_caption","id":cap["id"]}],"Changed the referenced caption to red.")
        if low.startswith("cut") or low.startswith("remove"):
            r=self._range(low)
            if "pricing" in low or "cost" in low:
                matches=self._matches("pricing")
                if len(matches)>1:
                    options=[f"{i+1}: {w['start']:.1f}s ({w['text']})" for i,w in enumerate(matches)]+["all"]
                    self.pending={"kind":"content_cut","instruction":text,"matches":matches,"question":"Which pricing mention should be removed?","options":options}
                    return self.respond("needs_clarification",summary="Pricing has multiple content matches.",question=self.pending["question"],options=options)
            if not r and "first" in low:r=(0,30)
            if not r:return self.respond("rejected",summary="Provide a source-time range, for example 0:30-0:40.")
            a,b=r
            if a<0 or b<=a or b>=self.timeline.duration:return self.respond("rejected",summary="The cut range is invalid or would remove the whole source.")
            if any(c["start"]==a and c["end"]==b for c in self.timeline.cuts):return self.respond("rejected",summary="That exact range is already cut.")
            op={"start":a,"end":b,"anchor":"source_range"}; self.timeline.cuts.append(op); self.commit("cut",text,before,op)
            removed=[c["id"] for c in self.timeline.captions if not any(self.timeline.visible(w["start"],w["end"]) for w in self.timeline.transcript if w["id"] in c["anchor_word_ids"])]
            return self.respond("applied",[{"type":"cut",**op}],f"Cut {b-a:.1f} seconds from original time.",warnings=["Caption hidden while its anchored words are cut"] if removed else [])
        if low.startswith("speed up") or low.startswith("slow down"):
            r=self._range(low); factor=re.search(r"(\d+(?:\.\d+)?)x",low)
            if not r or not factor:return self.respond("rejected",summary="Provide a range and factor, for example 1:00 to 1:30 by 2x.")
            f=float(factor.group(1)); f=1/f if low.startswith("slow") else f
            if f>4 or f<.25:return self.respond("rejected",summary="Speed factor must be between 0.25x and 4x.")
            op={"start":r[0],"end":r[1],"factor":f}; self.timeline.speeds.append(op); self.commit("speed",text,before,op)
            return self.respond("applied",[{"type":"speed",**op}],f"Applied speed change using {TIME_POLICY}.")
        if low.startswith("mute") or low.startswith("bleep"):
            effect="bleep" if low.startswith("bleep") else "mute"; r=self._range(low)
            words=[]
            if "word" in low or "say" in low:
                term=re.findall(r"['\"]([^'\"]+)['\"]",text); words=self._matches(term[0].lower()) if term else []
                if len(words)==1:r=(words[0]["start"],words[0]["end"])
            if not r:return self.respond("rejected",summary="Provide a source range or an unambiguous quoted word.")
            op={"type":effect,"start":r[0],"end":r[1],"anchor_word_ids":[w["id"] for w in words]};self.timeline.audio_effects.append(op);self.commit(effect,text,before,op)
            return self.respond("applied",[op],f"Applied {effect} anchored to source content.")
        if "remove filler" in low or "remove ums" in low:
            fillers=[w for w in self.timeline.transcript if w["text"].lower() in {"um","uh"}]
            if not fillers:return self.respond("applied",[],"No removable filler words were found; meaningful uses of 'like' are never removed automatically.")
            ops=[]
            for w in fillers:
                op={"start":w["start"],"end":w["end"],"anchor":"word:"+w["id"],"history_id":""};self.timeline.cuts.append(op);ops.append(op)
            self.commit("remove_filler",text,before,{"word_ids":[w["id"] for w in fillers]})
            for o in ops:o["history_id"]=self.history[-1]["id"]
            return self.respond("applied",[{"type":"cut",**o} for o in ops],"Removed only unambiguous um/uh fillers.")
        if "remove silence" in low:
            return self.respond("rejected",summary="Silence removal requires audio analysis; no audio-analysis result is available for this session.")
        return self.respond("rejected",summary="Unsupported instruction in the deterministic mock parser.")
