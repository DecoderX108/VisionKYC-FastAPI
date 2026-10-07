import base64

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def image_bytes(seed: int = 1, width: int = 640, height: int = 480) -> bytes:
    image = np.random.default_rng(seed).integers(55, 215, (height, width, 3), dtype=np.uint8)
    ok, output = cv2.imencode(".jpg", image)
    assert ok
    return output.tobytes()


def data_url(seed: int = 1) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes(seed)).decode()


@pytest.fixture
def client():
    with TestClient(create_app(Settings(_env_file=None, log_level="ERROR"))) as test_client:
        yield test_client


@pytest.fixture
def synthetic_client(client, monkeypatch):
    # Synthetic images have no humans. Stub only detection so HTTP, decoding,
    # quality, descriptors, challenge state, ownership and policy still execute.
    detector = client.app.state.kyc.detector
    monkeypatch.setattr(detector, "boxes", lambda image, min_size=40: [
        (image.shape[1]//3, image.shape[0]//4, image.shape[1]//3, image.shape[0]//2)
    ])
    monkeypatch.setattr(detector, "align", lambda face: face)
    return client


def upload(client):
    response = client.post("/api/v1/kyc/verify-document",
                           files={"image": ("document.jpg", image_bytes(), "image/jpeg")},
                           data={"document_type": "passport", "consent": "true"})
    assert response.status_code == 200, response.text
    body = response.json()
    return body, {"Authorization": "Bearer " + body["session_token"]}

