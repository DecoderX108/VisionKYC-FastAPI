import cv2
import numpy as np

from app.core.config import Settings
from app.core.errors import KycError
from app.models.schemas import QualityMetrics


def local_binary_pattern(gray: np.ndarray) -> np.ndarray:
    center = gray[1:-1, 1:-1]
    code = np.zeros_like(center, dtype=np.uint8)
    neighbors = [gray[:-2, :-2], gray[:-2, 1:-1], gray[:-2, 2:], gray[1:-1, 2:],
                 gray[2:, 2:], gray[2:, 1:-1], gray[2:, :-2], gray[1:-1, :-2]]
    for bit, neighbor in enumerate(neighbors):
        code |= ((neighbor >= center).astype(np.uint8) << bit)
    return code


def measure_quality(image: np.ndarray) -> QualityMetrics:
    gray = cv2.cvtColor(cv2.resize(image, (256, 256)), cv2.COLOR_BGR2GRAY)
    hist = np.bincount(local_binary_pattern(gray).ravel(), minlength=256).astype(float)
    probabilities = hist / max(hist.sum(), 1)
    nonzero = probabilities[probabilities > 0]
    return QualityMetrics(
        brightness=round(float(gray.mean()), 3),
        sharpness=round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 3),
        contrast=round(float(gray.std()), 3),
        lbp_entropy=round(float(-(nonzero * np.log2(nonzero)).sum()), 3),
    )


def require_quality(metrics: QualityMetrics, settings: Settings) -> None:
    if metrics.brightness < settings.min_brightness:
        raise KycError("low_light", "Move to brighter, even lighting")
    if metrics.brightness > 245:
        raise KycError("overexposed", "Reduce glare and avoid a bright light behind you")
    if metrics.sharpness < settings.min_sharpness:
        raise KycError("blurred_image", "Hold still and let the camera focus")

