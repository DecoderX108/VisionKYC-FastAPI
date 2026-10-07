# Vision KYC Framework

A complete modular **FastAPI + React** implementation of document intake,
perspective correction, portrait extraction, a server-controlled camera challenge,
and face comparison. The default **demo mode runs without model downloads**.

**Demo results always return `MANUAL_REVIEW`.** Its DCT image descriptor is not a
trained face recognizer; its hold-still check is not proof of liveness; the
document classifier explicitly reports `unknown`. Real inference adapters and
challenge logic are implemented, but trained document/PAD weights and deployment
calibration must be supplied before automatic decisions are enabled.

This verifies a document image against a presented face. It does not establish
document authenticity, perform OCR/MRZ or registry validation, screen sanctions,
or implement a human review queue. `MANUAL_REVIEW` is a decision to route to your
own review system, not a claim that a reviewer has received the case.

## Quick start — Docker

Requires Docker Engine and Compose v2. From the extracted project directory:

```bash
cp backend/.env.example backend/.env
docker compose up --build -d
```

- App: <http://localhost:8080>
- API / interactive Swagger: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Both published ports bind to localhost. Model weights are unnecessary for demo.
The initial build downloads Python/Node dependencies. Subsequent demo startup
does not download models. Try an actual clear portrait-bearing document; malformed,
dark, blurred, no-face, and multiple-face images are intentionally rejected even
in demo mode. Do not use test fakes to verify real people.

## Local development — Python and Node

Use Python **3.11 or 3.12** and Node **22.12+**. Python 3.12 is the Docker baseline.
OpenCV's headless wheel includes its Haar cascades, so no GUI toolkit or separate
Haar download is needed.

Terminal 1, Bash / Zsh:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Fish (including CachyOS): use `source .venv/bin/activate.fish` for activation.
If CachyOS's system Python is newer than the supported range, use an installed
Python 3.12 (`python3.12 -m venv .venv`) or the Docker route above.

Windows PowerShell, from `backend`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Terminal 2, from the project root:

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` and `/health` to port 8000, so
requests use the same browser origin. Axios sends each opaque session token in
the `Authorization` header; no shared API secret belongs in React environment
variables. `frontend/.env.example` is optional when using the proxy.

## Directory architecture

```text
kyc-framework/
├── README.md
├── compose.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── MODELS.md
│   ├── DEPLOYMENT.md
│   └── TEST_REPORT.md
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py
│   │   ├── api/routes.py
│   │   ├── core/{config,errors,middleware}.py
│   │   ├── models/{schemas,state}.py
│   │   ├── services/{kyc_service,session_store,decision}.py
│   │   └── vision/
│   │       ├── document_processor.py
│   │       ├── face_verifier.py
│   │       ├── liveness.py
│   │       ├── model_loader.py
│   │       ├── quality.py
│   │       └── image_io.py
│   ├── scripts/export_facenet.py
│   ├── weights/README.md
│   └── tests/
└── frontend/
    ├── package.json / package-lock.json
    ├── vite.config.js
    ├── tailwind.config.js / postcss.config.js
    ├── Dockerfile / nginx.conf
    └── src/
        ├── main.jsx / api.js / styles.css
        ├── components/
        │   ├── DocumentUpload.jsx
        │   ├── CameraCapture.jsx
        │   ├── KycWizard.jsx
        │   └── VerificationResult.jsx
        └── test/
```

## Workflow

1. **Upload + consent.** Submit JPEG/PNG/WebP with selected document type. The
   backend verifies decoded size, pixels and quality; detects a quadrilateral;
   orders its corners; uses `getPerspectiveTransform` and `warpPerspective`;
   tries cardinal orientations; and selects the largest Haar portrait candidate.
   If Haar finds others, the selected face is shown for inspection and automatic
   approval is blocked pending manual review.
   If the boundary is uncertain, the whole image is retained and final approval
   is blocked. Type predictions come only from the trained classifier.
2. **Session.** The API returns a document UUID and a random bearer credential.
   The server retains the embedding, metadata and temporary challenge evidence.
   The browser retains the token in component memory, not localStorage.
3. **Camera.** `getUserMedia` requests a front camera with an ideal 1920×1080
   stream. The CSS preview is mirrored; transmitted pixels are unmirrored.
   The server chooses the challenge order and turn direction. Model mode uses
   center → randomized blink/turn → hold still, with PAD and face-continuity
   checks. Demo mode uses only framing/quality/hold-still checks.
4. **Frame analysis.** The browser submits frames sequentially at up to roughly
   10 fps, bounded by inference latency. The server enforces sequence, attempt
   UUID, expiry, and duplicate-frame checks. Low light or a missing face returns
   a corrective prompt. A model blink requires open → closed → open over time.
5. **Selfie.** After a server-confirmed pass, React captures a fresh high-quality
   JPEG from that same stream. The server requires at least 480 px per side,
   verifies the challenge window, repeats quality/PAD checks, and compares the
   selfie to the initial and last accepted challenge embeddings in model mode.
6. **Decision.** Face embeddings are L2-normalized and compared with sklearn
   `cosine_similarity`. The API returns cosine/Euclidean distances, a display
   percentage, reasons, and threshold gates. Biometric evidence is released
   after completion. Identical final retries return the cached result.

## Endpoints

| Method | Endpoint | Input | Purpose |
|---|---|---|---|
| POST | `/api/v1/kyc/verify-document` | Multipart `image`, `document_type`, `consent` | Create document session |
| POST | `/api/v1/kyc/liveness/start` | JSON `document_id` + bearer | Issue/reset a challenge; max 3 attempts |
| POST | `/api/v1/kyc/liveness-check` | JSON document/challenge IDs, sequence, frame + bearer | Evaluate one ordered frame |
| POST | `/api/v1/kyc/verify-face` | JSON document/challenge IDs, selfie + bearer | Consume passed challenge and compare |
| DELETE | `/api/v1/kyc/sessions/{document_id}` | Bearer | Revoke/delete session |
| GET | `/health` | None | Mode and readiness |

See [API.md](docs/API.md) for request examples and errors. Schemas forbid unknown
fields, bound images, validate UUIDs/enums, and require actual JSON integers for
frame sequence. Multipart booleans are parsed from strings as required by forms.

## Scores and thresholds

For normalized embeddings **u** and **v**:

```text
similarity = cosine_similarity(u, v)
cosine_distance = 1 - similarity
euclidean_distance = ||u - v||₂ = sqrt(2 - 2 × similarity)
match_percentage = 100 × max(0, similarity)
```

The percentage is a similarity display, **not an identity probability**. Defaults
are illustrative and should not be represented as validated KYC thresholds:

| Gate | Default |
|---|---|
| Approve face similarity | `>= 0.70` |
| Reject face similarity | `< 0.45` |
| Face review interval | `[0.45, 0.70)` |
| Challenge/selfie continuity | `>= 0.65` |
| Document confidence | `>= 0.85` |
| PAD live score | `>= 0.90` |

Automatic decisions additionally require model mode and
`KYC_THRESHOLDS_CALIBRATED=true`. Approval requires the requested type to be
verified, a detected document boundary, no document-quality warnings, and all
challenge/PAD/continuity gates. Missing models make model-mode startup fail;
there is no silent fallback to random weights.

## View all logs

Docker, live logs from both services:

```bash
docker compose logs -f --tail=200
```

Backend only, all retained output:

```bash
docker compose logs --no-log-prefix backend
```

Capture local API logs, Bash/Zsh:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log 2>&1 | tee kyc.log
```

Fish:

```fish
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log &| tee kyc.log
```

PowerShell: append `2>&1 | Tee-Object -FilePath kyc.log` to the Python command.
Every application request has an `X-Request-ID`; errors display the same reference
in the UI. Search a captured file using `rg 'REQUEST_ID' kyc.log`. Events include
`startup`, `http_request`, `document_processed`, `request_error`, and
`verification_completed`. Logs contain route templates, status, timing and error
codes; images, embeddings, tokens and uploaded filenames are excluded. Docker
rotates each container log at 10 MB and retains 3 files, so “all” means all
currently retained logs. Browser DevTools Console and Network show client errors.

## Test and build

```bash
cd backend
python -m pytest -q
```

```bash
cd frontend
npm test
npm run build
```

The test suite uses synthetic images and explicit detector doubles for HTTP flow
tests; it does not measure face-recognition or spoof-detection accuracy. See
[TEST_REPORT.md](docs/TEST_REPORT.md) for executed checks and remaining limits.

`backend/constraints-tested.txt` records the main tested dependency versions.
To reproduce that demo dependency set in a clean environment, use
`python -m pip install -c constraints-tested.txt -e '.[test]'` from `backend`.
The optional model environment needs its own validated dependency lock.

## Real models and deployment

- [Model contracts, FaceNet export and calibration](docs/MODELS.md)
- [Architecture and threat boundaries](docs/ARCHITECTURE.md)
- [HTTPS, Docker deployment and troubleshooting](docs/DEPLOYMENT.md)

The reference session store is **single-process, ephemeral memory**. Run one
Uvicorn worker. Restarts invalidate sessions. Use a shared session store with
atomic locking/updates before adding replicas or workers. Bind sessions to your
existing authenticated customer and policy engine before exposing automated KYC
decisions to a real customer flow.

## Primary references

- FastAPI forms/files: https://fastapi.tiangolo.com/tutorial/request-forms-and-files/
- Pydantic form models: https://fastapi.tiangolo.com/tutorial/request-form-models/
- OpenCV geometric transforms: https://docs.opencv.org/4.x/da/d54/group__imgproc__transform.html
- MediaPipe Face Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python
- FaceNet PyTorch implementation: https://github.com/timesler/facenet-pytorch
- Browser camera security/permissions: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia

## Authors & Maintainers
- **Prasanna Sen Thakuri** — project lead ([@DecoderX108](https://github.com/DecoderX108))
- **Shovit Kafle** — team member
- **Samyog Rajbhandari** — team member

Contact: prasanna_25126469@sunway.edu.np
