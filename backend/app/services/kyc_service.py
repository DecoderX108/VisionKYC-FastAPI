from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
import time
from uuid import UUID, uuid4

import numpy as np

from app.core.config import Settings
from app.core.errors import KycError
from app.models.schemas import (DocumentResponse, DocumentType, LivenessRequest, LivenessResponse,
                                ThresholdBreakdown, VerificationResponse, VerifyFaceRequest)
from app.models.state import Session
from app.services.decision import decide
from app.services.session_store import SessionStore, token_digest
from app.vision.document_processor import DocumentProcessor
from app.vision.face_verifier import FaceDetector, FaceVerifier
from app.vision.image_io import decode_base64, decode_image, preview_url
from app.vision.liveness import ChallengeState, LivenessAnalyzer

logger = logging.getLogger("kyc")


class KycService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.detector = FaceDetector()
        self.documents = DocumentProcessor(settings, self.detector)
        self.faces = FaceVerifier(settings, self.detector)
        self.liveness = LivenessAnalyzer(settings, self.detector)
        self.store = SessionStore(settings.max_sessions)

    def close(self) -> None:
        self.store.clear()
        self.liveness.close()

    def verify_document(self, data: bytes, document_type: DocumentType) -> DocumentResponse:
        document = self.documents.process(decode_image(data, self.settings), document_type)
        embedding = self.faces.embed(document.face)
        token = secrets.token_urlsafe(32)
        session = Session(
            id=uuid4(), token_hash=token_digest(token),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.settings.session_ttl_seconds),
            classification=document.classification, document_embedding=embedding,
            boundary_detected=document.boundary_detected, warnings=document.warnings,
        )
        response = DocumentResponse(
            document_id=session.id, session_token=token, expires_at=session.expires_at.isoformat(),
            mode=self.settings.mode, classification=document.classification,
            boundary_detected=document.boundary_detected, quality=document.quality,
            corrected_document_preview=preview_url(document.corrected),
            document_face_preview=preview_url(document.face, 256), warnings=document.warnings,
        )
        self.store.put(session)
        logger.info("document_processed", extra={"event": "document_processed", "mode": self.settings.mode})
        return response

    def start_challenge(self, document_id: UUID, token: str) -> LivenessResponse:
        with self.store.authorized(document_id, token) as session:
            if session.result is not None:
                raise KycError("session_completed", "This session has already been completed", 409)
            if session.attempts >= 3:
                raise KycError("attempt_limit", "Three attempts used. Start with a new document upload", 429)
            session.attempts += 1
            session.challenge = ChallengeState(self.settings.mode)
            return session.challenge.response()

    def check_liveness(self, payload: LivenessRequest, token: str) -> LivenessResponse:
        with self.store.authorized(payload.document_id, token) as session:
            challenge = session.challenge
            if challenge is None or challenge.id != payload.challenge_id:
                raise KycError("invalid_challenge", "Start a valid liveness challenge first", 409)
            image = decode_base64(payload.image_base64, self.settings)
            now = time.monotonic()
            challenge.validate_frame(image, payload.sequence, self.settings, now)
            try:
                observation = self.liveness.analyze(image)
                embedding = self.faces.embed(observation.face)
            except KycError as error:
                challenge.reset_partial()
                challenge.last_observation = None
                challenge.issue = error.message
                return challenge.response()
            if challenge.initial_embedding is None:
                # The reference is anchored only on a frame accepted by PAD.
                if self.settings.mode == "demo" or (observation.pad is not None and observation.pad >= self.settings.pad_live_threshold):
                    challenge.initial_embedding = embedding
            elif self.settings.mode == "model":
                continuity = self.faces.similarity(challenge.initial_embedding, embedding)
                if continuity < self.settings.continuity_similarity:
                    challenge.status = "FAILED"
                    challenge.issue = "Face continuity was lost. Restart the challenge."
                    return challenge.response()
            challenge.advance(observation, self.settings, now)
            if challenge.issue is None:
                challenge.last_embedding = embedding
            return challenge.response()

    def verify_face(self, payload: VerifyFaceRequest, token: str) -> VerificationResponse:
        with self.store.authorized(payload.document_id, token) as session:
            digest = hashlib.sha256(payload.selfie_base64.encode()).hexdigest()
            if session.result is not None:
                if digest != session.selfie_digest or payload.challenge_id != session.completed_challenge_id:
                    raise KycError("session_consumed", "This session was completed using another selfie", 409)
                return session.result
            challenge = session.challenge
            if challenge is None or challenge.id != payload.challenge_id or challenge.status != "PASSED":
                raise KycError("liveness_required", "Complete this session's liveness challenge first", 409)
            if challenge.passed_at is None or time.monotonic()-challenge.passed_at > self.settings.selfie_window_seconds:
                raise KycError("selfie_expired", "Selfie capture window expired. Restart the challenge", 410)
            selfie = decode_base64(payload.selfie_base64, self.settings)
            if min(selfie.shape[:2]) < 480:
                raise KycError("selfie_resolution", "Capture a selfie with at least 480 pixels on each side")
            observation = self.liveness.analyze(selfie)
            embedding = self.faces.embed(observation.face)
            if challenge.last_embedding is None or challenge.initial_embedding is None:
                raise KycError("missing_liveness_evidence", "Challenge evidence is missing. Restart", 409)
            continuity = min(self.faces.similarity(embedding, challenge.last_embedding),
                             self.faces.similarity(embedding, challenge.initial_embedding))
            if self.settings.mode == "model":
                if continuity < self.settings.continuity_similarity:
                    challenge.status = "FAILED"
                    raise KycError("selfie_continuity", "Selfie does not match the challenge participant", 409)
                if observation.pad is None or observation.pad < self.settings.pad_live_threshold:
                    challenge.status = "FAILED"
                    raise KycError("selfie_presentation", "Selfie did not pass the presentation check", 409)
            assert session.document_embedding is not None
            scores = self.faces.compare_embeddings(session.document_embedding, embedding)
            # Decide on full precision; rounding is for display only.
            similarity = self.faces.similarity(session.document_embedding, embedding)
            decision, reasons = decide(self.settings, session.classification, similarity,
                                       session.boundary_detected, session.warnings)
            thresholds = ThresholdBreakdown(
                approve_similarity_gte=self.settings.approve_similarity,
                reject_similarity_lt=self.settings.reject_similarity,
                manual_review_interval=[self.settings.reject_similarity, self.settings.approve_similarity],
                continuity_similarity_gte=self.settings.continuity_similarity,
                document_confidence_gte=self.settings.document_confidence,
                pad_live_score_gte=self.settings.pad_live_threshold,
                calibrated=self.settings.thresholds_calibrated,
            )
            result = VerificationResponse(
                document_id=session.id, decision=decision, mode=self.settings.mode,
                embedding_backend=self.faces.backend, **scores,
                score_note="100 × max(0, cosine similarity); a display score, not a calibrated identity probability.",
                continuity_similarity=round(continuity, 6), liveness_assurance=self.settings.mode,
                classification=session.classification, thresholds=thresholds, reasons=reasons,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            session.result, session.selfie_digest = result, digest
            session.completed_challenge_id = challenge.id
            session.clear_biometrics()
            logger.info("verification_completed", extra={"event": "verification_completed", "decision": decision, "mode": self.settings.mode})
            return result
