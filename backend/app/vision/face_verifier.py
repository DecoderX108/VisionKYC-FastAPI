from threading import Lock

import cv2
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.core.config import Settings
from app.core.errors import KycError
from app.vision.image_io import resize_max
from app.vision.model_loader import TorchModel


class FaceDetector:
    def __init__(self) -> None:
        self.cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.eyes = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml")
        self.lock = Lock()
        if self.cascade.empty() or self.eyes.empty():
            raise RuntimeError("OpenCV Haar cascade files are unavailable")

    def boxes(self, image: np.ndarray, min_size: int = 40) -> list[tuple[int, int, int, int]]:
        gray = cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))
        with self.lock:
            boxes = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(min_size, min_size))
        return [tuple(map(int, box)) for box in boxes]

    def crop_box(self, image: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
        x, y, width, height = box
        margin = int(max(width, height) * 0.12)
        crop = image[max(0, y-margin):min(image.shape[0], y+height+margin),
                     max(0, x-margin):min(image.shape[1], x+width+margin)].copy()
        return resize_max(crop, 512)

    def single_face(self, image: np.ndarray, min_size: int = 40) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        boxes = self.boxes(image, min_size)
        if not boxes:
            raise KycError("no_face", "No clear face found. Face the camera and improve lighting")
        if len(boxes) != 1:
            raise KycError("multiple_faces", "Use an image containing exactly one clear face")
        return self.crop_box(image, boxes[0]), boxes[0]

    def align(self, face: np.ndarray) -> np.ndarray:
        """Correct eye-line roll only; this is not an MTCNN alignment replacement."""
        gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
        with self.lock:
            boxes = self.eyes.detectMultiScale(gray[:int(gray.shape[0] * 0.65)], 1.1, 5, minSize=(12, 12))
        if len(boxes) != 2:
            return face
        centers = sorted([(x+w/2, y+h/2) for x, y, w, h in boxes])
        left, right = np.array(centers)
        if right[0] - left[0] < face.shape[1] * 0.2:
            return face
        angle = float(np.degrees(np.arctan2(right[1]-left[1], right[0]-left[0])))
        if abs(angle) > 30:
            return face
        matrix = cv2.getRotationMatrix2D(tuple((left+right)/2), angle, 1)
        return cv2.warpAffine(face, matrix, (face.shape[1], face.shape[0]), borderMode=cv2.BORDER_REPLICATE)


class FaceVerifier:
    def __init__(self, settings: Settings, detector: FaceDetector) -> None:
        self.detector = detector
        self.backend = "demo_dct_descriptor"
        self.model = None
        if settings.mode == "model":
            assert settings.face_model_path is not None
            self.model = TorchModel(settings.face_model_path, settings.device)
            self.backend = "torchscript_facenet"
            # Validate the model contract at startup, before accepting a session.
            self.embed(np.full((160, 160, 3), 128, np.uint8))

    def embed(self, face: np.ndarray) -> np.ndarray:
        aligned = self.detector.align(face)
        if self.model is not None:
            vector = self.model.predict(aligned, 160, "facenet")
            if vector.shape != (512,):
                raise RuntimeError("FaceNet adapter requires 512-dimensional embeddings")
        else:
            # A deterministic wiring demo, NOT a biometric embedding model.
            gray = cv2.cvtColor(cv2.resize(aligned, (32, 32)), cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray).astype(np.float32) / 255
            vector = cv2.dct(gray)[:16, :16].flatten()
            vector[0] = 0  # remove the mean intensity coefficient
        norm = float(np.linalg.norm(vector))
        if not np.isfinite(vector).all() or norm < 1e-8:
            raise KycError("invalid_embedding", "Cannot extract useful features from this face")
        return (vector / norm).astype(np.float32)

    @staticmethod
    def similarity(first: np.ndarray, second: np.ndarray) -> float:
        return float(np.clip(cosine_similarity(first.reshape(1, -1), second.reshape(1, -1))[0, 0], -1, 1))

    def compare_embeddings(self, first: np.ndarray, second: np.ndarray) -> dict[str, float]:
        similarity = self.similarity(first, second)
        return {
            "cosine_similarity": round(similarity, 6),
            "cosine_distance": round(1 - similarity, 6),
            "euclidean_distance": round(float(np.linalg.norm(first-second)), 6),
            # Requested display percentage, not a probability of same identity.
            "match_percentage": round(max(0.0, similarity) * 100, 2),
        }

