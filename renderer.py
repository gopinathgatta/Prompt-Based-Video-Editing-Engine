"""FFmpeg renderer. It always writes a new output and never modifies the input."""
import json, os, shutil, subprocess, tempfile
from pathlib import Path

def ffmpeg_bin(): return os.getenv("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"
def render(timeline, source_path, output_path):
    source=Path(source_path); out=Path(output_path); out.parent.mkdir(parents=True,exist_ok=True)
    if not source.exists(): raise FileNotFoundError("Original media is unavailable for rendering")
    cuts=sorted(timeline.cuts,key=lambda c:c["start"]); duration=timeline.duration; spans=[]; cursor=0.0
    for cut in cuts:
        if cut["start"]>cursor: spans.append((cursor,min(cut["start"],duration)))
        cursor=max(cursor,cut["end"])
    if cursor<duration: spans.append((cursor,duration))
    if not spans: raise ValueError("Timeline has no renderable video")
    filters=[]; labels=[]
    for i,(start,end) in enumerate(spans):
        speed=next((s for s in timeline.speeds if s["start"]<=start and end<=s["end"]),None); factor=speed["factor"] if speed else 1
        v=f"[0:v]trim=start={start}:end={end},setpts=(PTS-STARTPTS)/{factor}[v{i}]";a=f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS"
        # atempo is limited to 0.5..2; engine only admits factors this renderer can chain.
        tempo=factor
        while tempo>2: a+=",atempo=2";tempo/=2
        while tempo<.5: a+=",atempo=0.5";tempo/=0.5
        a+=f",atempo={tempo}[a{i}]";filters += [v,a];labels += [f"[v{i}][a{i}]"]
    filters.append("".join(labels)+f"concat=n={len(spans)}:v=1:a=1[v][a]")
    cmd=[ffmpeg_bin(),"-y","-i",str(source),"-filter_complex",";".join(filters),"-map","[v]","-map","[a]","-c:v","libx264","-c:a","aac",str(out)]
    run=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
    if run.returncode: raise RuntimeError(run.stderr[-1600:])
    manifest={"output":str(out),"source_sha256":timeline.source["sha256"],"timeline_hash":timeline.hash(),"renderer":"ffmpeg","warnings":["Captions and text overlays are represented in the timeline but not burned in this renderer yet."]}
    Path(str(out)+".manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")
    return manifest
