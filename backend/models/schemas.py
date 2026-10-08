from typing import Literal

from pydantic import BaseModel, Field, field_validator
from enum import Enum


class MatrixGenerateRequest(BaseModel):
    rows: int = Field(gt=0, le=16384)
    cols: int = Field(gt=0, le=16384)
    seed: int | None = None


class MatrixInfo(BaseModel):
    id: str
    rows: int
    cols: int


class MultiplyRequest(BaseModel):
    matrix_a_id: str
    matrix_b_id: str
    tile_size: int = 256

    @field_validator("tile_size")
    @classmethod
    def validate_tile_size(cls, v: int) -> int:
        if v not in (128, 256, 512, 1024, 2048):
            raise ValueError("tile_size must be 128, 256, 512, 1024, or 2048")
        return v


class JobInfo(BaseModel):
    job_id: str


class TileStatus(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"
    FAILED = "failed"


class TileStatusEvent(BaseModel):
    i: int
    j: int
    k: int
    status: TileStatus
    completed: int
    total: int
    elapsed: float


class PhaseStats(BaseModel):
    total: float
    mean: float
    min: float
    max: float
    count: int


class JobCompleteEvent(BaseModel):
    status: Literal["completed", "failed"]
    completed: int
    total: int
    elapsed: float
    phase_timings: dict[str, PhaseStats] | None = None


class VerificationResult(BaseModel):
    max_abs_error: float
    mean_abs_error: float
    passed: bool
    tolerance: float


class VerifyRequest(BaseModel):
    tolerance: float | None = Field(default=None, gt=0)
