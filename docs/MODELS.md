# Model integration

## Two modes

`KYC_MODE=demo` needs no model weights, PyTorch, TensorFlow or MediaPipe. It uses
OpenCV and a deterministic DCT image descriptor so the complete API/UI flow can
run immediately after dependency installation. Every final decision is
`MANUAL_REVIEW`; untrained logic is never used to approve/reject identity.

`KYC_MODE=model` requires **all four** trusted local model artifacts. Installing
libraries alone does not supply document classification or PAD models. This
project does not invent a universal citizenship/passport/PAN classifier or claim
that random weights perform verification. You must train or acquire these two
models for your supported document layouts and presentation attack set.

## Runtime installation

In the backend Python 3.11/3.12 virtual environment:

```bash
python -m pip install -e '.[vision,test]'
```

This selects PyTorch, not TensorFlow. For a CPU-only PyTorch distribution, install
the appropriate CPU wheel using PyTorch's official installation selector before
the command above. For CUDA, select a wheel compatible with the deployed driver
and set `KYC_DEVICE=cuda`; CPU remains the default.

MediaPipe distributions can bring an OpenCV contrib wheel. Avoid independently
mixing arbitrary OpenCV wheel versions in an existing environment; build and
freeze a clean model-runtime environment and run `python -m pip check`. The demo
needs only `opencv-python-headless`.

## FaceNet export

The included script exports upstream **InceptionResnetV1 pretrained on VGGFace2**
to a local TorchScript adapter. The upstream `facenet-pytorch` package has tighter
torch/torchvision/NumPy constraints than the runtime; use a separate export
environment. A compatible export environment for its 2.6.0 release is:

```bash
cd backend
python3.11 -m venv .export-venv
source .export-venv/bin/activate
python -m pip install 'facenet-pytorch==2.6.0'
python scripts/export_facenet.py --output weights/facenet.ts
deactivate
```

The explicit export downloads the VGGFace2 checkpoint. Review upstream model and
dataset license/usage terms. The API itself never fetches a checkpoint. This
adapter expects `[1,3,160,160]` RGB float input standardized by `(pixel-127.5)/128`,
and returns `[1,512]`. Its output is L2-normalized again by the verifier.

The reference detector uses Haar crops with eye-line roll correction if two
clear eyes are found; this differs from upstream's recommended MTCNN cropping.
For a deployed FaceNet pipeline, replace `FaceDetector` with your validated
detector/alignment implementation, keep preprocessing identical for enrollment
and selfie, and recalibrate all face thresholds. An off-the-shelf LFW accuracy
number is not a KYC ID-to-selfie accuracy measurement.

## MediaPipe facial landmarks

Download the Face Landmarker `.task` bundle linked in the official MediaPipe
Face Landmarker guide and place it at `weights/face_landmarker.task`:

https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python

The adapter uses Tasks API `RunningMode.IMAGE` under a lock to avoid mixing
per-user video-tracker state. The application's temporal state is per session.
It requests up to two faces and rejects any result with a face count other than
one. Blink thresholds and the nose-to-eye pose proxy need validation across
camera positions, eyewear and participant conditions.

## Document classifier

Export your trained PyTorch classifier as a TorchScript module:

```python
# model is your already-trained torch.nn.Module; no random weights are supplied.
model = model.cpu().eval()
example = torch.randn(1, 3, 224, 224)
torch.jit.trace(model, example).save('weights/document.ts')
```

Input preprocessing is RGB, resized to 224×224, scaled to `[0,1]`, then normalized
using mean `[0.485,0.456,0.406]` and std `[0.229,0.224,0.225]`. Output must be logits
`[1,4]`, in this exact order:

| Index | Label |
|---|---|
| 0 | citizenship |
| 1 | passport |
| 2 | pan |
| 3 | unknown |

Train/validate on your actual accepted jurisdictions and document versions,
including unknown documents, blank images, photographs and confusing layouts.
Nepali PAN/citizenship layouts are not interchangeable with cards from other
countries. Softmax confidence is a model score, not proof of authenticity.

## Presentation attack detection (PAD)

`weights/pad.ts` must accept the cropped face under the same 224×224 RGB ImageNet
normalization and emit `[1,2]` logits in **spoof / live** order. If your trained PAD
model uses a larger context crop, different color spaces, multiple modalities,
or different normalization, adapt `LivenessAnalyzer` and `TorchModel.predict`
to that documented contract. Renaming an arbitrary checkpoint is insufficient.

The model is applied to each challenge observation and to the final selfie.
Three consecutive low PAD scores fail the challenge. Only passing PAD frames
anchor continuity or advance the challenge. OpenCV LBP entropy is exposed as a
quality diagnostic; it does not replace a trained PAD model.

## Enable inference

Edit `backend/.env`:

```dotenv
KYC_MODE=model
KYC_FACE_MODEL_PATH=weights/facenet.ts
KYC_DOCUMENT_MODEL_PATH=weights/document.ts
KYC_PAD_MODEL_PATH=weights/pad.ts
KYC_LANDMARK_MODEL_PATH=weights/face_landmarker.task
KYC_DEVICE=cpu
KYC_THRESHOLDS_CALIBRATED=false
```

Restart the backend. All four files are required, and tensor contracts are
checked at startup. A bad model fails startup; it does not fall back to demo.
Leave `KYC_THRESHOLDS_CALIBRATED=false` while evaluating to force final manual
review even with valid models. It still enforces challenge, PAD and continuity.

For Docker, use the same `.env`, put model files in `backend/weights`, and rebuild:

```bash
INSTALL_VISION=true docker compose up --build -d
```

Fish: `env INSTALL_VISION=true docker compose up --build -d`.
Windows PowerShell: `$env:INSTALL_VISION='true'; docker compose up --build -d`.

## Calibration and promotion

Use a held-out, consented set of genuine document/selfie pairs, impostor pairs,
screen/print attacks and relevant capture conditions. Split by identity and
capture session to avoid training/test leakage. Measure false match/non-match
rates and presentation attack errors at candidate thresholds. Choose separate
approval and rejection cutoffs, a review interval, PAD cutoff, continuity cutoff,
and quality thresholds based on the service's tolerated errors and review load.

Keep model versions, hashes, preprocessing, threshold settings and validation
results together. Check performance across supported document types and capture
conditions. Then set `KYC_THRESHOLDS_CALIBRATED=true` in a controlled deployment.
The flag is a deployment gate, not a substitute for that evidence.

The packaged tests validate code paths and contracts, not the accuracy of your
weights. Real-weight inference, GPU packaging and biometric/PAD performance
require validation with your chosen artifacts.

