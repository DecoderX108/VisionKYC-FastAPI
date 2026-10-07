"""Measured EAR, pose proxy and optional learned PAD; texture is diagnostic only."""
from dataclasses import dataclass, field
import hashlib
import secrets
from threading import Lock
import time
from uuid import UUID, uuid4

import cv2
import numpy as np

from app.core.config import Settings
from app.core.errors import KycError
from app.models.schemas import LivenessResponse, QualityMetrics
from app.vision.face_verifier import FaceDetector
from app.vision.image_io import resize_max
from app.vision.model_loader import TorchModel, softmax
from app.vision.quality import measure_quality, require_quality


def eye_aspect_ratio(points: np.ndarray) -> float:
    """Six ordered eye points: corners 0/3; upper 1/2; lower 5/4."""
    if points.shape != (6, 2):
        raise ValueError("EAR requires six 2-D eye landmarks")
    horizontal = float(np.linalg.norm(points[0] - points[3]))
    if horizontal < 1e-6:
        raise KycError("invalid_landmarks", "Keep your eyes visible to the camera")
    return float((np.linalg.norm(points[1]-points[5]) + np.linalg.norm(points[2]-points[4])) / (2*horizontal))


@dataclass
class Observation:
    face: np.ndarray
    quality: QualityMetrics
    center: np.ndarray
    ear: float | None
    yaw: float | None
    pad: float | None


class LivenessAnalyzer:
    def __init__(self, settings: Settings, detector: FaceDetector) -> None:
        self.settings, self.detector = settings, detector
        self.landmarker = None
        self.pad = None
        self.lock = Lock()
        if settings.mode == "model":
            import mediapipe as mp

            self.mp = mp
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(settings.landmark_model_path)),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                num_faces=2,
                min_face_detection_confidence=0.6,
                min_face_presence_confidence=0.6,
            )
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
            assert settings.pad_model_path is not None
            self.pad = TorchModel(settings.pad_model_path, settings.device)
            softmax(self.pad.predict(np.zeros((224, 224, 3), np.uint8), 224, "imagenet"), 2)

    def close(self) -> None:
        if self.landmarker is not None:
            self.landmarker.close()

    def analyze(self, image: np.ndarray) -> Observation:
        image = resize_max(image, 1280)
        face, (x, y, w, h) = self.detector.single_face(image, min_size=70)
        if w / image.shape[1] < 0.12:
            raise KycError("face_too_far", "Move closer to the camera")
        quality = measure_quality(face)
        require_quality(quality, self.settings)
        ear = yaw = pad = None
        if self.landmarker is not None:
            rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            with self.lock:
                result = self.landmarker.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb))
            if len(result.face_landmarks) != 1:
                raise KycError("landmark_face_count", "Keep exactly one face visible")
            # Use pixel coordinates: normalized x/y have different scales on a
            # non-square image and would distort the eye-aspect ratio.
            points = np.array([(p.x * image.shape[1], p.y * image.shape[0]) for p in result.face_landmarks[0]])
            left = eye_aspect_ratio(points[[33, 160, 158, 133, 153, 144]])
            right = eye_aspect_ratio(points[[362, 385, 387, 263, 373, 380]])
            ear = (left + right) / 2
            eye_midpoint = (points[33] + points[263]) / 2
            eye_width = float(np.linalg.norm(points[33]-points[263]))
            if eye_width < 10:
                raise KycError("invalid_landmarks", "Move closer to the camera")
            # Dimensionless yaw proxy relative to the eye midpoint, NOT degrees.
            yaw = float((points[1, 0] - eye_midpoint[0]) / eye_width)
            assert self.pad is not None
            pad = float(softmax(self.pad.predict(face, 224, "imagenet"), 2)[1])
        center = np.array([(x+w/2)/image.shape[1], (y+h/2)/image.shape[0], w/image.shape[1]])
        return Observation(face, quality, center, ear, yaw, pad)


@dataclass
class ChallengeState:
    mode: str
    started: float = field(default_factory=time.monotonic)
    id: UUID = field(default_factory=uuid4)
    stages: list[str] = field(default_factory=list)
    step: int = 0
    sequence: int = 0
    status: str = "IN_PROGRESS"
    seen: set[str] = field(default_factory=set)
    last_received: float = 0
    stable_count: int = 0
    last_center: np.ndarray | None = None
    open_count: int = 0
    closed_at: float | None = None
    baseline_yaw: float = 0
    passed_at: float | None = None
    initial_embedding: np.ndarray | None = None
    last_embedding: np.ndarray | None = None
    last_observation: Observation | None = None
    issue: str | None = None
    pad_failures: int = 0

    def __post_init__(self) -> None:
        if not self.stages:
            if self.mode == "demo":
                self.stages = ["hold_still"]
            else:
                turn = secrets.choice(["turn_left", "turn_right"])
                actions = ["blink", turn] if secrets.randbelow(2) else [turn, "blink"]
                self.stages = ["center", *actions, "hold_still"]

    def reset_partial(self) -> None:
        self.stable_count = self.open_count = 0
        self.closed_at = None
        self.last_center = None

    def validate_frame(self, image: np.ndarray, sequence: int, settings: Settings, now: float) -> None:
        if self.status != "IN_PROGRESS":
            raise KycError("challenge_finished", "Start a new challenge before submitting more frames", 409)
        if now - self.started > settings.challenge_ttl_seconds:
            self.status = "FAILED"
            raise KycError("challenge_expired", "Challenge expired. Start a new attempt", 410)
        if sequence != self.sequence:
            raise KycError("frame_sequence", "Frame order is invalid. Restart the challenge", 409)
        if self.last_received and now - self.last_received < 0.04:
            raise KycError("frame_rate", "Frames arrived too quickly", 429)
        tiny = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (64, 64))
        digest = hashlib.sha256((tiny // 4).tobytes()).hexdigest()
        if digest in self.seen:
            raise KycError("replayed_frame", "Repeated frame detected. Restart using a live camera", 409)
        if len(self.seen) >= 900:
            self.status = "FAILED"
            raise KycError("frame_limit", "Frame limit reached. Restart the challenge", 409)
        self.seen.add(digest)
        self.sequence += 1
        if self.last_received and now - self.last_received > 1.5:
            self.reset_partial()
        self.last_received = now

    def advance(self, observation: Observation, settings: Settings, now: float) -> None:
        self.issue = None
        self.last_observation = observation
        if self.mode == "model" and (observation.pad is None or observation.pad < settings.pad_live_threshold):
            self.reset_partial()
            self.pad_failures += 1
            self.issue = "Presentation check failed. Remove obstructions and use a live camera."
            if self.pad_failures >= 3:
                self.status = "FAILED"
            return
        self.pad_failures = 0
        stage = self.stages[self.step]
        centered = observation.yaw is not None and abs(observation.yaw - self.baseline_yaw) < 0.09
        complete = False
        if stage == "center":
            self.stable_count = self.stable_count + 1 if observation.yaw is not None and abs(observation.yaw) < 0.12 else 0
            complete = self.stable_count >= 3
            if complete:
                self.baseline_yaw = float(observation.yaw)
        elif stage == "blink":
            if not centered or observation.ear is None:
                self.reset_partial()
                self.issue = "Face forward, then blink slowly once."
                return
            if observation.ear >= settings.ear_open:
                if self.closed_at is not None:
                    duration = now - self.closed_at
                    complete = 0.08 <= duration <= 1.5
                    self.closed_at = None
                    self.open_count = 0
                else:
                    self.open_count += 1
            elif observation.ear <= settings.ear_closed and self.open_count >= 2:
                if self.closed_at is None:
                    self.closed_at = now
            if self.closed_at is not None and now - self.closed_at > 1.5:
                self.reset_partial()
        elif stage.startswith("turn_"):
            # An unmirrored capture: the user's left maps to positive image x.
            delta = (observation.yaw or 0) - self.baseline_yaw
            correct = delta >= settings.turn_ratio if stage == "turn_left" else delta <= -settings.turn_ratio
            self.stable_count = self.stable_count + 1 if correct else 0
            complete = self.stable_count >= 2
        elif stage == "hold_still":
            steady = self.last_center is not None and np.linalg.norm(observation.center-self.last_center) < 0.04
            acceptable = self.mode == "demo" or (centered and observation.ear is not None and observation.ear >= settings.ear_open)
            self.stable_count = self.stable_count + 1 if steady and acceptable else 0
            self.last_center = observation.center
            complete = self.stable_count >= 3 and now - self.started >= 1.2
        if complete:
            self.step += 1
            self.reset_partial()
            if self.step == len(self.stages):
                self.status = "PASSED"
                self.passed_at = now

    def response(self) -> LivenessResponse:
        prompts = {
            "center": "Face the camera with your eyes open",
            "blink": "Blink slowly once",
            "turn_left": "Turn your head slightly to your left",
            "turn_right": "Turn your head slightly to your right",
            "hold_still": "Face forward and hold still",
        }
        if self.status == "PASSED":
            prompt = "Hold still — capturing your selfie"
        elif self.status == "FAILED":
            prompt = "Challenge failed. Please retry."
        else:
            prompt = prompts[self.stages[self.step]]
        if self.mode == "demo" and self.status == "IN_PROGRESS":
            prompt += " · demo quality check"
        obs = self.last_observation
        return LivenessResponse(
            challenge_id=self.id, status=self.status, challenge_passed=self.status == "PASSED",
            assurance=self.mode, prompt=self.issue or prompt, step=self.step,
            total_steps=len(self.stages), progress=self.step/len(self.stages), next_sequence=self.sequence,
            ear=obs.ear if obs else None, yaw_ratio=obs.yaw if obs else None,
            pad_live_score=obs.pad if obs else None, quality=obs.quality if obs else None, issue=self.issue,
        )

