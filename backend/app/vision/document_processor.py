from dataclasses import dataclass

import cv2
import numpy as np

from app.core.config import Settings
from app.core.errors import KycError
from app.models.schemas import Classification, DocumentType, QualityMetrics
from app.vision.face_verifier import FaceDetector
from app.vision.image_io import resize_max
from app.vision.model_loader import TorchModel, softmax
from app.vision.quality import measure_quality, require_quality


@dataclass
class ProcessedDocument:
    corrected: np.ndarray
    face: np.ndarray
    boundary_detected: bool
    classification: Classification
    quality: QualityMetrics
    warnings: list[str]


def order_quad(points: np.ndarray) -> np.ndarray:
    points = points.reshape(4, 2).astype(np.float32)
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1]-center[1], points[:, 0]-center[0])
    ordered = points[np.argsort(angles)]
    return np.roll(ordered, -int(np.argmin(ordered.sum(axis=1))), axis=0)


def warp_document(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = order_quad(quad)
    width = int(max(np.linalg.norm(tr-tl), np.linalg.norm(br-bl)))
    height = int(max(np.linalg.norm(bl-tl), np.linalg.norm(br-tr)))
    if min(width, height) < 160:
        raise KycError("document_too_small", "Move closer so the document fills more of the frame")
    target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
    matrix = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]), target)
    return cv2.warpPerspective(image, matrix, (width, height))


class DocumentProcessor:
    def __init__(self, settings: Settings, detector: FaceDetector) -> None:
        self.settings, self.detector = settings, detector
        self.classifier = None
        if settings.mode == "model":
            assert settings.document_model_path is not None
            self.classifier = TorchModel(settings.document_model_path, settings.device)
            softmax(self.classifier.predict(np.zeros((224, 224, 3), np.uint8), 224, "imagenet"), 4)

    def detect_boundary(self, image: np.ndarray) -> np.ndarray | None:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 140)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area = image.shape[0] * image.shape[1]
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
            polygon = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
            if len(polygon) == 4 and cv2.isContourConvex(polygon) and cv2.contourArea(polygon) > area * 0.25:
                return polygon.reshape(4, 2)
        return None

    def classify(self, image: np.ndarray, requested: DocumentType) -> Classification:
        if self.classifier is None:
            # Never echo a user-selected type as though a model verified it.
            return Classification(requested=requested, predicted="unknown", confidence=None,
                                  verified=False, backend="placeholder")
        labels = ["citizenship", "passport", "pan", "unknown"]
        probabilities = softmax(self.classifier.predict(image, 224, "imagenet"), 4)
        index = int(probabilities.argmax())
        confidence = float(probabilities[index])
        predicted = labels[index]
        return Classification(requested=requested, predicted=predicted, confidence=confidence,
                              verified=predicted == requested.value and confidence >= self.settings.document_confidence,
                              backend="torchscript")

    def process(self, image: np.ndarray, requested: DocumentType) -> ProcessedDocument:
        image = resize_max(image, 1800)
        boundary = self.detect_boundary(image)
        corrected = warp_document(image, boundary) if boundary is not None else image
        warnings = [] if boundary is not None else ["Document boundary uncertain; manual review required."]
        quality = measure_quality(corrected)
        require_quality(quality, self.settings)
        face = None
        for rotation in range(4):
            candidate = np.ascontiguousarray(np.rot90(corrected, rotation))
            boxes = self.detector.boxes(candidate)
            if boxes:
                # Haar can fire on stamps, printed text, or a faint ghost
                # portrait. Keep the largest candidate visible to the user,
                # but require manual review whenever the selection is unsure.
                box = max(boxes, key=lambda item: item[2] * item[3])
                corrected = candidate
                face = self.detector.crop_box(candidate, box)
                if len(boxes) > 1:
                    warnings.append(
                        "Multiple face candidates detected. The largest is shown; "
                        "manual review is required to confirm the portrait."
                    )
                if min(box[2:]) < 80:
                    warnings.append("Document portrait has limited resolution; manual review required.")
                break
        if face is None:
            raise KycError("no_document_face", "No portrait found on the document. Upload the portrait side with no glare")
        require_quality(measure_quality(face), self.settings)
        classification = self.classify(corrected, requested)
        if self.classifier is None:
            warnings.append("Demo mode: document type has not been verified.")
        return ProcessedDocument(corrected, face, boundary is not None, classification, quality, warnings)
