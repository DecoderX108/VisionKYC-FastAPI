from dataclasses import replace

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models.schemas import Classification, DocumentType, QualityMetrics
from app.services.decision import decide
from app.vision.liveness import ChallengeState, Observation


def model_settings():
    # Test state and policy without downloading/inferencing real weights.
    return Settings(_env_file=None).model_copy(update={"mode":"model", "thresholds_calibrated":True})


def observation(ear=0.3, yaw=0.0, pad=0.99):
    return Observation(np.zeros((100,100,3), np.uint8),
                       QualityMetrics(brightness=120,sharpness=100,contrast=40,lbp_entropy=6),
                       np.array([0.5,0.5,0.3]), ear, yaw, pad)


def test_blink_requires_open_closed_open_and_timeout():
    settings = model_settings()
    state = ChallengeState("model", started=0, stages=["blink"])
    state.advance(observation(ear=0.1), settings, 1)
    state.advance(observation(ear=0.3), settings, 1.2)
    assert state.status == "IN_PROGRESS"  # starting closed is not a blink
    state.advance(observation(ear=0.3), settings, 1.4)
    state.advance(observation(ear=0.1), settings, 1.6)
    state.advance(observation(ear=0.3), settings, 1.9)
    assert state.status == "PASSED"
    state = ChallengeState("model", started=0, stages=["blink"])
    for ear, now in [(0.3,1),(.3,1.2),(.1,1.4),(.1,3.2),(.3,3.4)]:
        state.advance(observation(ear=ear), settings, now)
    assert state.status == "IN_PROGRESS"


def test_turn_direction_center_and_pad():
    settings = model_settings()
    state = ChallengeState("model", started=0, stages=["turn_left", "hold_still"])
    for now in [1,1.2,1.4]:
        state.advance(observation(yaw=-0.2), settings, now)
    assert state.step == 0
    state.advance(observation(yaw=.2), settings, 1.6)
    state.advance(observation(yaw=.2), settings, 1.8)
    assert state.step == 1
    for now in [2,2.2,2.4,2.6]:
        state.advance(observation(yaw=.2), settings, now)
    assert state.status == "IN_PROGRESS"  # must return to center
    for now in [3,3.2,3.4]:
        state.advance(observation(pad=0.01), settings, now)
    assert state.status == "FAILED"


def test_policy_boundaries_and_demo_never_auto_decides():
    settings = model_settings()
    classified = Classification(requested=DocumentType.PASSPORT, predicted="passport", confidence=.99, verified=True, backend="test")
    assert decide(settings, classified, .70, True, [])[0] == "APPROVED"
    assert decide(settings, classified, .45, True, [])[0] == "MANUAL_REVIEW"
    assert decide(settings, classified, .449, True, [])[0] == "REJECTED"
    assert decide(settings, classified, .99, False, [])[0] == "MANUAL_REVIEW"
    assert decide(settings.model_copy(update={"thresholds_calibrated":False}), classified, .99, True, [])[0] == "MANUAL_REVIEW"
    for similarity in [-1,.1,.7,1]:
        assert decide(Settings(_env_file=None), classified, similarity, True, [])[0] == "MANUAL_REVIEW"


def test_model_mode_fails_without_weights():
    with pytest.raises(ValidationError, match="local model"):
        Settings(_env_file=None, mode="model")

