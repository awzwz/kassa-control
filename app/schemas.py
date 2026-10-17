"""Формат ответа ровно по §10 кейса. Лишних полей внутри violations быть не должно."""
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceFrame(BaseModel):
    timestamp_sec: float
    image_base64: str  # «сырой» base64 JPEG, начинается с /9j/


class Violation(BaseModel):
    type: str
    timecode_sec: float
    description: str
    evidence_frames: list[EvidenceFrame] = Field(min_length=1, max_length=3)


class JobProcessing(BaseModel):
    job_id: str
    status: Literal["processing"] = "processing"


class JobFailed(BaseModel):
    job_id: str
    status: Literal["failed"] = "failed"
    error: str


class JobDone(BaseModel):
    job_id: str
    status: Literal["done"] = "done"
    verdict: Literal["violation", "no_violation"]
    violations: list[Violation]


class AnalyzeAccepted(BaseModel):
    job_id: str
    status: Literal["processing"] = "processing"
