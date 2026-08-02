from typing import Literal

from pydantic import BaseModel, Field

InputKind = Literal["chords", "tab"]


class JobResponse(BaseModel):
    id: str
    status: Literal["queued", "processing", "complete", "failed"]
    source_kind: InputKind = "chords"
    error: str | None = None


class ReviewRequest(BaseModel):
    decision: Literal["approved", "dismissed", "ignored"]


class AnalysisEvent(BaseModel):
    kind: str | None = None
    pitch: int
    onset_seconds: float
    duration_seconds: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    token: str | None = None
    string: str | None = None
    fret: int | None = Field(default=None, ge=0)
    source_line: int | None = None
    source_start: int | None = None


class Finding(BaseModel):
    id: str
    measure_number: int
    type: Literal[
        "wrong_pitch",
        "wrong_chord",
        "missing_note",
        "extra_note",
        "timing_deviation",
    ]
    confidence: float = Field(ge=0, le=1)
    expected: AnalysisEvent | None = None
    detected: AnalysisEvent | None = None
    message: str
    correction: str | None = None
    audio_start_seconds: float | None = Field(default=None, ge=0)
    audio_end_seconds: float | None = Field(default=None, ge=0)


class MeasureResult(BaseModel):
    number: int
    start_seconds: float
    end_seconds: float
    score: float = Field(ge=0, le=1)
    expected_events: list[AnalysisEvent]
    detected_events: list[AnalysisEvent]


class AnalysisResult(BaseModel):
    source_kind: InputKind
    source_text: str
    measures: list[MeasureResult]
    findings: list[Finding]
    transcription_engine: str
    timing_basis: str
    suggested_text: str | None = None
