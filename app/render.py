from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .timeline.engine import TimelineEngine

FONT_FILE = os.environ.get("PS2_FONT_FILE", r"C:/Windows/Fonts/arial.ttf")


def _font_filter() -> str:
    path = FONT_FILE.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return f"fontfile='{path}':"


def probe(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("No video stream was found")
    rate = video.get("avg_frame_rate", "0/1").split("/")
    fps = float(rate[0]) / max(float(rate[1]), 1.0)
    return {
        "duration_s": float(data.get("format", {}).get("duration", video.get("duration", 0))),
        "frame_rate": fps,
        "width": int(video.get("width", 0)), "height": int(video.get("height", 0)),
        "video_codec": video.get("codec_name"),
        "audio": any(s.get("codec_type") == "audio" for s in streams),
        "streams": streams,
    }


def _tool_version(command: str) -> str:
    try:
        result = subprocess.run([command, "-version"], capture_output=True, text=True, check=True)
        return result.stdout.splitlines()[0].strip()
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}"


def _escape_drawtext(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def render(engine: TimelineEngine, source: str, output: str) -> dict:
    timeline = engine.timeline
    if not timeline.segments:
        raise ValueError("Timeline has no video segments")
    metadata = probe(source)
    started = time.perf_counter()
    filters: list[str] = []
    has_audio = metadata["audio"]
    vlabels, alabels = [], []
    if len(timeline.segments) > 1:
        filters.append(f"[0:v:0]split={len(timeline.segments)}" + "".join(f"[vsrc{i}]" for i in range(len(timeline.segments))))
        if has_audio:
            filters.append(f"[0:a:0]asplit={len(timeline.segments)}" + "".join(f"[asrc{i}]" for i in range(len(timeline.segments))))
    for i, segment in enumerate(timeline.segments):
        a, b, speed = segment.source_start_s, segment.source_end_s, segment.speed
        vsrc = f"[vsrc{i}]" if len(timeline.segments) > 1 else "[0:v:0]"
        asrc = f"[asrc{i}]" if len(timeline.segments) > 1 else "[0:a:0]"
        filters.append(f"{vsrc}trim=start={a:.9f}:end={b:.9f},setpts=(PTS-STARTPTS)/{speed:.9f}[v{i}]")
        vlabels.append(f"[v{i}]")
        if has_audio:
            factors = []
            remaining = speed
            while remaining > 2.0:
                factors.append("atempo=2.0"); remaining /= 2.0
            while remaining < 0.5:
                factors.append("atempo=0.5"); remaining /= 0.5
            factors.append(f"atempo={remaining:.9f}")
            filters.append(f"{asrc}atrim=start={a:.9f}:end={b:.9f},asetpts=PTS-STARTPTS,{','.join(factors)}[a{i}]")
            alabels.append(f"[a{i}]")
    if has_audio:
        paired = "".join(f"[v{i}][a{i}]" for i in range(len(vlabels)))
        filters.append(f"{paired}concat=n={len(vlabels)}:v=1:a=1[vcat][acat]")
    else:
        filters.append(f"{''.join(vlabels)}concat=n={len(vlabels)}:v=1:a=0[vcat]")
    video_label = "vcat"
    positions = engine.word_positions()
    for i, caption in enumerate(timeline.captions):
        spans = [positions[word_id] for word_id in caption.word_ids if word_id in positions]
        if not spans:
            continue
        start = min(s[0] for s in spans)
        end = max(s[1] for s in spans)
        end = max(end, start + caption.minimum_duration_s)
        color = caption.color if caption.color in {"white", "black", "red", "green", "blue", "yellow", "cyan", "magenta"} else "white"
        filters.append(
            f"[{video_label}]drawtext={_font_filter()}text='{_escape_drawtext(caption.text)}':fontcolor={color}:fontsize=36:"
            f"x=(w-text_w)/2:y=h-text_h-40:enable='between(t,{start:.6f},{end:.6f})'[vcap{i}]"
        )
        video_label = f"vcap{i}"
    for i, overlay in enumerate(timeline.overlays):
        anchors = overlay.get("word_ids", [])
        spans = [positions[word_id] for word_id in anchors if word_id in positions]
        if anchors and not spans:
            continue
        start = min(s[0] for s in spans) if spans else float(overlay.get("start_s", 0))
        end = max(s[1] for s in spans) if spans else float(overlay.get("end_s", start))
        out_label = f"voverlay{i}"
        filters.append(
            f"[{video_label}]drawtext={_font_filter()}text='{_escape_drawtext(overlay.get('text', ''))}':"
            f"fontcolor=white:fontsize=32:x=(w-text_w)/2:y=40:enable='between(t,{start:.6f},{end:.6f})'[{out_label}]"
        )
        video_label = out_label
    audio_label = "acat"
    if has_audio:
        mute_index = 0
        for effect in timeline.audio_effects:
            if effect.get("type") != "mute":
                raise ValueError(f"Rendering audio effect {effect.get('type')} is not supported safely yet")
            for word_id in effect.get("word_ids", []):
                span = positions.get(word_id)
                if span:
                    out_label = f"amute{mute_index}"
                    filters.append(f"[{audio_label}]volume=0:enable='between(t,{span[0]:.6f},{span[1]:.6f})'[{out_label}]")
                    audio_label = out_label
                    mute_index += 1
    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", source, "-filter_complex", ";".join(filters), "-map", f"[{video_label}]"]
    if has_audio:
        cmd += ["-map", f"[{audio_label}]"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "160k"]
    cmd += ["-movflags", "+faststart", output]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr[-4000:])
    actual = probe(output)
    expected = timeline.duration_s
    video_stream = next(s for s in actual["streams"] if s.get("codec_type") == "video")
    audio_stream = next((s for s in actual["streams"] if s.get("codec_type") == "audio"), None)
    av_offset_frames = None
    if audio_stream is not None:
        av_offset_frames = abs(float(video_stream.get("start_time", 0)) - float(audio_stream.get("start_time", 0))) * metadata["frame_rate"]
    manifest = {
        "source_sha256": timeline.source_sha256,
        "output_path": os.path.abspath(output),
        "output_sha256": __import__("hashlib").sha256(Path(output).read_bytes()).hexdigest(),
        "timeline_duration_s": expected,
        "rendered_duration_s": actual["duration_s"],
        "duration_error_frames": abs(actual["duration_s"] - expected) * metadata["frame_rate"],
        "av_start_offset_frames": av_offset_frames,
        "frame_rate": metadata["frame_rate"], "audio_present": actual["audio"],
        "render_seconds": time.perf_counter() - started,
        "versions": {"ffmpeg": _tool_version("ffmpeg"), "ffprobe": _tool_version("ffprobe")},
        "render_settings": {
            "video_encoder": "libx264", "preset": "veryfast", "crf": 20,
            "pixel_format": "yuv420p", "audio_encoder": "aac" if has_audio else None,
            "audio_bitrate": "160k" if has_audio else None,
            "font_file": FONT_FILE,
            "timestamp_policy": timeline.time_policy,
        },
        "warnings": ["No automatic transcription was performed.", "A/V start offset is a stream timestamp comparison; perceptual sync was not measured."],
        "models": [], "cost": "No external model/service cost; local FFmpeg runtime not monetized.",
        "rights": "Input-media rights are the uploader's responsibility; FFmpeg distribution/build licensing must be verified before commercial deployment.",
        "licenses": {"application": "pre-existing timeline code provenance is unverified; see SOURCES.md", "ffmpeg": "host build is GPL-enabled; see SOURCES.md", "font": "font licensing depends on configured PS2_FONT_FILE; see SOURCES.md"},
    }
    Path(output + ".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
