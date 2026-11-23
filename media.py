"""Immutable media intake and FFprobe metadata extraction."""
import hashlib, json, os, shutil, subprocess
from pathlib import Path

def _bin(): return os.getenv("FFPROBE_BIN") or shutil.which("ffprobe") or "ffprobe"

def inspect(path):
    raw=Path(path).read_bytes()
    meta={"path":str(path),"sha256":hashlib.sha256(raw).hexdigest(),"size_bytes":len(raw),"probe_warning":None}
    try:
        cmd=[_bin(),"-v","error","-show_entries","format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,time_base","-of","json",str(path)]
        data=json.loads(subprocess.check_output(cmd,text=True,timeout=30))
        video=next((s for s in data.get("streams",[]) if s.get("codec_type")=="video"),{})
        audio=next((s for s in data.get("streams",[]) if s.get("codec_type")=="audio"),{})
        meta.update(duration_s=float(data.get("format",{}).get("duration",0) or 0),width=video.get("width"),height=video.get("height"),frame_rate=video.get("r_frame_rate"),time_base=video.get("time_base"),video_codec=video.get("codec_name"),audio_codec=audio.get("codec_name"),has_audio=bool(audio))
    except Exception as exc: meta["probe_warning"]=str(exc)
    return meta
