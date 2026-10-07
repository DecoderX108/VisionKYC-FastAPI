from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from uuid import UUID

import numpy as np

from app.models.schemas import Classification, VerificationResponse
from app.vision.liveness import ChallengeState


@dataclass
class Session:
    id: UUID
    token_hash: str
    expires_at: datetime
    classification: Classification
    document_embedding: np.ndarray | None
    boundary_detected: bool
    warnings: list[str]
    lock: RLock = field(default_factory=RLock)
    challenge: ChallengeState | None = None
    attempts: int = 0
    result: VerificationResponse | None = None
    completed_challenge_id: UUID | None = None
    selfie_digest: str | None = None
    revoked: bool = False

    def clear_biometrics(self) -> None:
        self.document_embedding = None
        self.challenge = None
