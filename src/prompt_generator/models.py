"""Domain models for Prompt Generator subsystem."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional


class SceneStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RATE_LIMITED = "RATE_LIMITED"


class BatchStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RATE_LIMITED = "RATE_LIMITED"


class QueueState(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    RETRYING = "RETRYING"
    RATE_LIMITED = "RATE_LIMITED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


@dataclass
class Scene:
    scene_number: int
    raw_text: str
    status: SceneStatus = SceneStatus.PENDING
    generated_prompt: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "scene_number": self.scene_number,
            "raw_text": self.raw_text,
            "status": self.status.value,
            "generated_prompt": self.generated_prompt,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Scene":
        return cls(
            scene_number=data["scene_number"],
            raw_text=data.get("raw_text", ""),
            status=SceneStatus(data.get("status", SceneStatus.PENDING.value)),
            generated_prompt=data.get("generated_prompt"),
            error=data.get("error"),
        )


@dataclass
class Batch:
    batch_id: str
    batch_index: int
    scenes: List[Scene]
    status: BatchStatus = BatchStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Batch":
        scenes = [Scene.from_dict(s) for s in data.get("scenes", [])]
        return cls(
            batch_id=data["batch_id"],
            batch_index=data.get("batch_index", 1),
            scenes=scenes,
            status=BatchStatus(data.get("status", BatchStatus.PENDING.value)),
            attempts=data.get("attempts", 0),
            error=data.get("error"),
        )

    @property
    def scene_numbers(self) -> List[int]:
        return [s.scene_number for s in self.scenes]

    def is_complete(self) -> bool:
        return self.status == BatchStatus.SUCCESS and all(
            s.status == SceneStatus.SUCCESS and s.generated_prompt for s in self.scenes
        )


@dataclass
class PromptJob:
    job_id: str
    input_file: Path
    output_file: Path
    batches: List[Batch] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    state: QueueState = QueueState.IDLE
    error_message: Optional[str] = None

    @property
    def total_scenes(self) -> int:
        return sum(len(b.scenes) for b in self.batches)

    @property
    def completed_scenes(self) -> int:
        return sum(
            1 for b in self.batches for s in b.scenes if s.status == SceneStatus.SUCCESS
        )
