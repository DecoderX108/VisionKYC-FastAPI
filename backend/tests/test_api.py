from datetime import datetime, timedelta, timezone
import time
from uuid import UUID, uuid4

import pytest

from conftest import data_url, image_bytes, upload

BASE = "/api/v1/kyc"


def finish_challenge(client, document, headers):
    response = client.post(BASE+"/liveness/start", json={"document_id": document["document_id"]}, headers=headers)
    assert response.status_code == 200
    state = response.json()
    session = client.app.state.kyc.store.sessions[UUID(document["document_id"])]
    session.challenge.started = time.monotonic() - 3
    for seed in range(2, 6):
        session.challenge.last_received = time.monotonic() - 0.2
        response = client.post(BASE+"/liveness-check", headers=headers, json={
            "document_id": document["document_id"], "challenge_id": state["challenge_id"],
            "sequence": state["next_sequence"], "image_base64": data_url(seed),
        })
        assert response.status_code == 200, response.text
        state = response.json()
    assert state["status"] == "PASSED", state
    return state


def test_full_demo_workflow_and_one_use_result(synthetic_client):
    client = synthetic_client
    document, headers = upload(client)
    assert document["classification"]["predicted"] == "unknown"
    assert not document["classification"]["verified"]
    before = client.post(BASE+"/verify-face", headers=headers, json={
        "document_id": document["document_id"], "challenge_id": str(uuid4()), "selfie_base64": data_url(),
    })
    assert before.status_code == 409
    state = finish_challenge(client, document, headers)
    payload = {"document_id": document["document_id"], "challenge_id": state["challenge_id"], "selfie_base64": data_url(10)}
    result = client.post(BASE+"/verify-face", headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["decision"] == "MANUAL_REVIEW"
    assert 0 <= result.json()["match_percentage"] <= 100
    assert client.post(BASE+"/verify-face", headers=headers, json=payload).json() == result.json()
    assert client.post(BASE+"/verify-face", headers=headers, json={**payload, "challenge_id": str(uuid4())}).status_code == 409
    assert client.post(BASE+"/verify-face", headers=headers, json={**payload, "selfie_base64": data_url(11)}).status_code == 409
    stored = client.app.state.kyc.store.sessions[UUID(document["document_id"])]
    assert stored.document_embedding is None and stored.challenge is None
    assert client.delete(BASE+"/sessions/"+document["document_id"], headers=headers).status_code == 204
    assert client.post(BASE+"/liveness/start", headers=headers, json={"document_id": document["document_id"]}).status_code == 401


def test_auth_and_cross_session_binding(synthetic_client):
    document, headers = upload(synthetic_client)
    other, other_headers = upload(synthetic_client)
    payload = {"document_id": document["document_id"]}
    assert synthetic_client.post(BASE+"/liveness/start", json=payload).status_code == 401
    assert synthetic_client.post(BASE+"/liveness/start", json=payload, headers=other_headers).status_code == 401
    challenge = synthetic_client.post(BASE+"/liveness/start", json=payload, headers=headers).json()
    response = synthetic_client.post(BASE+"/liveness-check", headers=other_headers, json={
        "document_id": other["document_id"], "challenge_id": challenge["challenge_id"],
        "sequence": 0, "image_base64": data_url(2),
    })
    assert response.status_code == 409


def test_replay_sequence_and_strict_schema(synthetic_client):
    document, headers = upload(synthetic_client)
    state = synthetic_client.post(BASE+"/liveness/start", json={"document_id": document["document_id"]}, headers=headers).json()
    payload = {"document_id": document["document_id"], "challenge_id": state["challenge_id"], "sequence": 0, "image_base64": data_url(2)}
    assert synthetic_client.post(BASE+"/liveness-check", headers=headers, json={**payload, "sequence": "0"}).status_code == 422
    assert synthetic_client.post(BASE+"/liveness-check", headers=headers, json={**payload, "passed": True}).status_code == 422
    assert synthetic_client.post(BASE+"/liveness-check", headers=headers, json={**payload, "sequence": 1}).status_code == 409
    assert synthetic_client.post(BASE+"/liveness-check", headers=headers, json=payload).status_code == 200
    session = synthetic_client.app.state.kyc.store.sessions[UUID(document["document_id"])]
    session.challenge.last_received = time.monotonic() - 1
    replay = synthetic_client.post(BASE+"/liveness-check", headers=headers, json={**payload, "sequence": 1})
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "replayed_frame"


def test_expiry_and_attempt_limit(synthetic_client):
    document, headers = upload(synthetic_client)
    for _ in range(3):
        assert synthetic_client.post(BASE+"/liveness/start", headers=headers, json={"document_id": document["document_id"]}).status_code == 200
    assert synthetic_client.post(BASE+"/liveness/start", headers=headers, json={"document_id": document["document_id"]}).status_code == 429
    session = synthetic_client.app.state.kyc.store.sessions[UUID(document["document_id"])]
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert synthetic_client.post(BASE+"/liveness/start", headers=headers, json={"document_id": document["document_id"]}).status_code == 410
    synthetic_client.app.state.kyc.store.prune()
    assert not synthetic_client.app.state.kyc.store.sessions
    assert session.document_embedding is None


@pytest.mark.parametrize("data", [{"document_type":"passport", "consent":"false"},
                                  {"document_type":"invalid", "consent":"true"},
                                  {"document_type":"passport", "consent":"true", "force":"true"}])
def test_document_form_validation(client, data):
    assert client.post(BASE+"/verify-document", data=data, files={"image": ("photo.jpg", image_bytes(), "image/jpeg")}).status_code == 422


def test_unreadable_and_request_limit(client):
    response = client.post(BASE+"/verify-document", data={"document_type":"pan", "consent":"true"},
                           files={"image": ("photo.jpg", b"not an image", "image/jpeg")})
    assert response.json()["error"]["code"] == "unreadable_image"
    response = client.post(BASE+"/verify-document", content=b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert response.headers["x-request-id"]
    assert "no-store" in response.headers["cache-control"]


def test_validation_does_not_echo_input(client):
    secret = "private-image-" * 10
    response = client.post(BASE+"/verify-face", json={"document_id": secret, "selfie_base64": secret}, headers={"Authorization":"Bearer bad"})
    assert response.status_code == 422
    assert secret not in response.text


def test_cors_preflight(client):
    response = client.options(BASE+"/liveness-check", headers={
        "Origin":"http://localhost:5173", "Access-Control-Request-Method":"POST",
        "Access-Control-Request-Headers":"authorization,content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


@pytest.mark.parametrize("failure", ["identity", "pad", "expired"])
def test_final_selfie_gates(synthetic_client, monkeypatch, failure):
    import numpy as np
    from app.models.schemas import QualityMetrics
    from app.vision.liveness import Observation

    client = synthetic_client
    document, headers = upload(client)
    state = finish_challenge(client, document, headers)
    service = client.app.state.kyc
    session = service.store.sessions[UUID(document["document_id"])]
    # Exercise the real-mode gates with controlled model outputs; this is not
    # a real-weight accuracy test.
    service.settings = service.settings.model_copy(update={"mode":"model"})
    anchor = np.zeros(256, np.float32); anchor[0] = 1
    current = np.zeros(256, np.float32); current[1 if failure == "identity" else 0] = 1
    session.challenge.initial_embedding = session.challenge.last_embedding = anchor
    if failure == "expired":
        session.challenge.passed_at = time.monotonic() - 21
    obs = Observation(np.zeros((160,160,3), np.uint8),
        QualityMetrics(brightness=120, sharpness=100, contrast=40, lbp_entropy=6),
        np.array([0.5,0.5,0.3]), .3, 0, 0.01 if failure == "pad" else .99)
    monkeypatch.setattr(service.liveness, "analyze", lambda image: obs)
    monkeypatch.setattr(service.faces, "embed", lambda face: current)
    response = client.post(BASE+"/verify-face", headers=headers, json={
        "document_id":document["document_id"], "challenge_id":state["challenge_id"], "selfie_base64":data_url(20),
    })
    assert response.status_code == (410 if failure == "expired" else 409)
    assert session.result is None

