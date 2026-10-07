from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DocumentType(str, Enum):
    CITIZENSHIP = "citizenship"
    PASSPORT = "passport"
    PAN = "pan"


class VerifyDocumentRequest(Schema):
    image: UploadFile
    document_type: DocumentType
    consent: bool

    @field_validator("consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Consent is required to process the document and face")
        return value


class QualityMetrics(Schema):
    brightness: float
    sharpness: float
    contrast: float
    lbp_entropy: float


class Classification(Schema):
    requested: DocumentType
    predicted: Literal["citizenship", "passport", "pan", "unknown"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    verified: bool
    backend: str


class DocumentResponse(Schema):
    document_id: UUID
    session_token: str
    expires_at: str
    mode: Literal["demo", "model"]
    classification: Classification
    boundary_detected: bool
    quality: QualityMetrics
    corrected_document_preview: str
    document_face_preview: str
    warnings: list[str]


class SessionRequest(Schema):
    document_id: UUID


# Content, signature, decoded length, format, and pixel limits are checked again
# before decoding. This upper bound limits JSON strings even before image decode.
EncodedImage = Annotated[str, Field(min_length=32, max_length=8_388_700, strict=True)]


class LivenessRequest(SessionRequest):
    challenge_id: UUID
    sequence: Annotated[StrictInt, Field(ge=0, le=1000)]
    image_base64: EncodedImage


class VerifyFaceRequest(SessionRequest):
    challenge_id: UUID
    selfie_base64: EncodedImage


class LivenessResponse(Schema):
    challenge_id: UUID
    status: Literal["IN_PROGRESS", "PASSED", "FAILED"]
    challenge_passed: bool
    assurance: Literal["demo", "model"]
    prompt: str
    step: int
    total_steps: int
    progress: float = Field(ge=0, le=1)
    next_sequence: int
    ear: float | None = None
    yaw_ratio: float | None = None
    pad_live_score: float | None = None
    quality: QualityMetrics | None = None
    issue: str | None = None


class ThresholdBreakdown(Schema):
    approve_similarity_gte: float
    reject_similarity_lt: float
    manual_review_interval: list[float]
    continuity_similarity_gte: float
    document_confidence_gte: float
    pad_live_score_gte: float
    calibrated: bool


class VerificationResponse(Schema):
    document_id: UUID
    decision: Literal["APPROVED", "REJECTED", "MANUAL_REVIEW"]
    mode: Literal["demo", "model"]
    embedding_backend: str
    cosine_similarity: float = Field(ge=-1, le=1)
    cosine_distance: float = Field(ge=0, le=2)
    euclidean_distance: float = Field(ge=0, le=2.000001)
    match_percentage: float = Field(ge=0, le=100)
    score_note: str
    continuity_similarity: float = Field(ge=-1, le=1)
    liveness_assurance: Literal["demo", "model"]
    classification: Classification
    thresholds: ThresholdBreakdown
    reasons: list[str]
    completed_at: str


class ErrorDetail(Schema):
    code: str
    message: str
    request_id: str


class ErrorResponse(Schema):
    error: ErrorDetail

