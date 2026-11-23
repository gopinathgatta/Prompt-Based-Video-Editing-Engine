from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class TranscriptWord:
    id: str
    text: str
    start_s: float
    end_s: float
    speaker: str = "speaker_1"
    confidence: float = 1.0
    filler: bool = False

    def __post_init__(self) -> None:
        if not self.id or self.start_s < 0 or self.end_s <= self.start_s:
            raise ValueError("word requires an id and a valid positive source-time range")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass
class Segment:
    id: str
    source_start_s: float
    source_end_s: float
    speed: float = 1.0

    @property
    def duration_s(self) -> float:
        return (self.source_end_s - self.source_start_s) / self.speed


@dataclass
class Caption:
    id: str
    text: str
    word_ids: list[str]
    color: str = "white"
    minimum_duration_s: float = 0.7


@dataclass
class EditStep:
    id: str
    instruction: str
    operation: dict[str, Any]
    before_hash: str
    after_hash: str
    active: bool = True


@dataclass
class Timeline:
    source_sha256: str
    source_duration_s: float
    frame_rate: float
    words: list[TranscriptWord]
    segments: list[Segment]
    captions: list[Caption] = field(default_factory=list)
    overlays: list[dict[str, Any]] = field(default_factory=list)
    audio_effects: list[dict[str, Any]] = field(default_factory=list)
    background_music: dict[str, Any] | None = None
    history: list[EditStep] = field(default_factory=list)
    redo_stack: list[dict[str, Any]] = field(default_factory=list)
    deliberate_pauses: list[tuple[float, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rendering: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"
    time_policy: Literal["current_timeline_seconds"] = "current_timeline_seconds"

    @property
    def duration_s(self) -> float:
        return sum(s.duration_s for s in self.segments)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
