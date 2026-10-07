from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="KYC_", extra="ignore")

    mode: Literal["demo", "model"] = "demo"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    session_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    challenge_ttl_seconds: int = Field(default=90, ge=15, le=180)
    selfie_window_seconds: int = Field(default=20, ge=5, le=60)
    max_sessions: int = Field(default=100, ge=1, le=1000)
    max_image_bytes: int = Field(default=6 * 1024 * 1024, ge=1024)
    max_request_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_pixels: int = Field(default=16_000_000, ge=100_000)
    min_brightness: float = Field(default=40, ge=0, le=255)
    min_sharpness: float = Field(default=25, ge=0)
    approve_similarity: float = Field(default=0.70, gt=-1, le=1)
    reject_similarity: float = Field(default=0.45, ge=-1, lt=1)
    continuity_similarity: float = Field(default=0.65, ge=-1, le=1)
    document_confidence: float = Field(default=0.85, ge=0, le=1)
    pad_live_threshold: float = Field(default=0.90, ge=0, le=1)
    ear_closed: float = Field(default=0.18, gt=0, lt=1)
    ear_open: float = Field(default=0.23, gt=0, lt=1)
    turn_ratio: float = Field(default=0.12, gt=0, lt=0.5)
    thresholds_calibrated: bool = False
    face_model_path: Path | None = None
    document_model_path: Path | None = None
    pad_model_path: Path | None = None
    landmark_model_path: Path | None = None
    device: str = "cpu"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def validate_settings(self) -> Self:
        if self.reject_similarity >= self.approve_similarity:
            raise ValueError("reject_similarity must be below approve_similarity")
        if self.ear_closed >= self.ear_open:
            raise ValueError("ear_closed must be below ear_open")
        if "*" in self.cors_origins:
            raise ValueError("Specify explicit CORS origins")
        if self.mode == "model":
            for key in ("face_model_path", "document_model_path", "pad_model_path", "landmark_model_path"):
                path = getattr(self, key)
                if path is None or not path.is_file():
                    raise ValueError(f"{key} must point to a local model file in model mode")
        return self

