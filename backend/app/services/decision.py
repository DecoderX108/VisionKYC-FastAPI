from app.core.config import Settings
from app.models.schemas import Classification


def decide(settings: Settings, classification: Classification, similarity: float,
           boundary_detected: bool, warnings: list[str]) -> tuple[str, list[str]]:
    """Called only after server-verified challenge, PAD and continuity gates."""
    if settings.mode == "demo":
        return "MANUAL_REVIEW", [
            "Demo descriptors are not biometric identity evidence.",
            "Document classification and liveness assurance require trained models.",
        ]
    if not settings.thresholds_calibrated:
        return "MANUAL_REVIEW", ["Thresholds have not been validated for this deployment."]
    confidence = classification.confidence or 0
    if confidence >= settings.document_confidence and classification.predicted not in {classification.requested.value, "unknown"}:
        return "REJECTED", ["The detected document type does not match the selected type."]
    if not classification.verified or not boundary_detected or warnings:
        return "MANUAL_REVIEW", ["Document classification, crop, or portrait quality needs review."]
    if similarity < settings.reject_similarity:
        return "REJECTED", ["Face similarity is below the rejection threshold."]
    if similarity >= settings.approve_similarity:
        return "APPROVED", ["Document, challenge, continuity and face-match gates passed."]
    return "MANUAL_REVIEW", ["Face similarity falls within the review interval."]

