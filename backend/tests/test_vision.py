import base64
import io

import cv2
import numpy as np
from PIL import Image
import pytest

from app.core.config import Settings
from app.core.errors import KycError
from app.models.schemas import Classification, DocumentType
from app.services.decision import decide
from app.vision.document_processor import DocumentProcessor, order_quad, warp_document
from app.vision.face_verifier import FaceDetector
from app.vision.image_io import decode_base64, decode_image
from app.vision.liveness import eye_aspect_ratio
from app.vision.quality import measure_quality, require_quality


def test_perspective_correction_preserves_corner_order():
    image = np.zeros((500, 700, 3), dtype=np.uint8)
    points = np.float32([[90, 60], [600, 90], [580, 400], [70, 420]])
    colors = [(255,0,0),(0,255,0),(0,0,255),(255,255,255)]
    cv2.fillConvexPoly(image, points.astype(int), (100,100,100))
    for point, color in zip(points, colors):
        cv2.circle(image, tuple(point.astype(int)), 30, color, -1)
    corrected = warp_document(image, points[[2,0,3,1]])
    corners = [corrected[5,5], corrected[5,-6], corrected[-6,-6], corrected[-6,5]]
    for actual, expected in zip(corners, colors):
        np.testing.assert_allclose(actual, expected, atol=3)
    assert len(np.unique(order_quad(points), axis=0)) == 4


def test_ear_open_and_closed():
    opened = np.float32([[0,0],[1,-1],[3,-1],[4,0],[3,1],[1,1]])
    closed = opened.copy(); closed[:,1] *= 0.1
    assert eye_aspect_ratio(opened) == pytest.approx(0.5)
    assert eye_aspect_ratio(closed) == pytest.approx(0.05)


def test_no_face_and_multiple_faces(monkeypatch):
    detector = FaceDetector()
    image = np.zeros((480,640,3), np.uint8)
    with pytest.raises(KycError, match="No clear face"):
        detector.single_face(image)
    monkeypatch.setattr(detector, "boxes", lambda *_: [(0,0,100,100), (120,0,100,100)])
    with pytest.raises(KycError, match="exactly one"):
        detector.single_face(image)


@pytest.mark.parametrize("secondary_size", [70, 135])
def test_extra_document_face_candidates_require_review(monkeypatch, secondary_size):
    settings = Settings(_env_file=None)
    detector = FaceDetector()
    processor = DocumentProcessor(settings, detector)
    image = np.random.default_rng(7).integers(55, 210, (480, 640, 3), dtype=np.uint8)
    largest = (65, 95, 150, 165)
    secondary = (400, 100, secondary_size, secondary_size)
    monkeypatch.setattr(processor, "detect_boundary", lambda _image: None)
    monkeypatch.setattr(detector, "boxes", lambda _image: [secondary, largest])

    result = processor.process(image, DocumentType.PASSPORT)

    np.testing.assert_array_equal(result.face, detector.crop_box(image, largest))
    assert any("Multiple face candidates" in warning for warning in result.warnings)
    classified = Classification(requested=DocumentType.PASSPORT, predicted="passport",
                                confidence=.99, verified=True, backend="test")
    calibrated = settings.model_copy(update={"mode": "model", "thresholds_calibrated": True})
    assert decide(calibrated, classified, .95, True, result.warnings)[0] == "MANUAL_REVIEW"


def test_low_light_and_blur():
    settings = Settings(_env_file=None)
    with pytest.raises(KycError, match="brighter"):
        require_quality(measure_quality(np.zeros((256,256,3), np.uint8)), settings)
    with pytest.raises(KycError, match="focus"):
        require_quality(measure_quality(np.full((256,256,3), 120, np.uint8)), settings)


def test_bad_base64_and_pixels():
    settings = Settings(_env_file=None)
    with pytest.raises(KycError, match="base64"):
        decode_base64("bad%" * 50, settings)
    output = io.BytesIO()
    Image.new("RGB", (401,400)).save(output, format="PNG")
    with pytest.raises(KycError, match="pixel"):
        decode_image(output.getvalue(), settings.model_copy(update={"max_pixels":100000}))
