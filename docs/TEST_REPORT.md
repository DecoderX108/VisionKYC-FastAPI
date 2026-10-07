# Validation report

## Executed successfully

| Check | Result |
|---|---|
| Backend editable installation, including declared test dependencies | Passed |
| Full backend suite before the portrait-selection update | **22 passed** |
| Updated `tests/test_vision.py` after the change | **7 passed**, including two new multiple-detection cases |
| `npm test` | **3 passed** |
| `npm run build` | Passed; Vite production assets generated |
| Real Uvicorn process launch and HTTP `/health` request | Passed; demo mode, status ok |
| HTTP `/openapi.json` from that process | Passed; 6 documented paths |

The current full backend rerun stalled while opening Starlette's test-client
lifespan in this restricted execution environment; no HTTP assertions ran in
that attempt. The focused vision suite completed successfully. The previously
completed full run covered these HTTP paths:

Backend tests exercise multipart consent/type/extra-field validation, corrupt
images, size limits, CORS preflight, bearer ownership, cross-session challenge
binding, ordered frames, duplicate frames, expiry, attempt limits, a full demo
HTTP flow, idempotent final retries, one-use result protection, and evidence
release. Controlled model outputs exercise selfie substitution, PAD failure,
capture expiry, and approval/rejection/review boundaries. Vision tests check
perspective corner mapping, EAR geometry, dark/blurred images, no/multiple faces,
bad base64, pixel limits, and multiple document face candidate handling. Liveness tests check blink chronology, closure
duration, turn direction, return to center and PAD failures.

Frontend tests verify document-file validation and the consent gate, explain a
camera permission denial, and stop media tracks when an asynchronous permission
request resolves after component unmount. The production bundle compiles React,
Axios and Tailwind successfully.

## Environment

- Python 3.12.14; Node 24.19.0; npm 11.9.0.
- OpenCV headless 4.14.0.94, NumPy 2.2.6, FastAPI 0.142.2,
  Pydantic 2.13.5, Pillow 12.3.0, sklearn 1.8.0.
- Exact main backend versions: `backend/constraints-tested.txt`.
- Exact frontend resolution: `frontend/package-lock.json`.
- Starlette 1.7 emits one test-client deprecation warning about its httpx adapter.
  The tests pass; this does not affect the application request paths.

## Not executed / not established

- No physical webcam session or real identity document was used in validation.
  Synthetic HTTP flow tests replace only face detection; they do not prove
  detector accuracy on real citizenship/passport/PAN documents.
- No trained FaceNet, document classifier, MediaPipe bundle or PAD artifact was
  executed. The optional model adapter/export code is supplied, but its inference
  and accuracy must be validated with the artifacts you select.
- No biometric accuracy, spoof resistance, false match/non-match rate, latency
  service level or demographic performance claim is made by these tests.
- Docker/Compose were unavailable in the execution environment, so container
  builds were not executed. Dockerfiles/Compose are included for local use; the
  non-container backend installation, server startup and frontend build were run.
- HTTPS deployment, GPU operation, multi-worker storage, customer authentication,
  document authenticity checks and manual-review routing were not deployed.

The default demo is an executable integration reference. Enabling automatic
decisions requires real models, calibrated thresholds and deployment-specific
validation, as described in `MODELS.md` and `DEPLOYMENT.md`.
