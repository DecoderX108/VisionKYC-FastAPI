Place local model files here to enable `KYC_MODE=model`. Demo mode needs none.

| File | Contract |
|---|---|
| `facenet.ts` | TorchScript; `[1,3,160,160]` RGB standardized `(x-127.5)/128`; `[1,512]` embeddings |
| `document.ts` | TorchScript; `[1,3,224,224]` ImageNet-normalized RGB; `[1,4]` logits in citizenship / passport / pan / unknown order |
| `pad.ts` | TorchScript; same image input contract as document model; `[1,2]` logits in spoof / live order |
| `face_landmarker.task` | MediaPipe Tasks Face Landmarker bundle |

Only load trusted model artifacts: model formats can contain executable code.
These are exact adapter contracts, not arbitrary checkpoint formats. See
`../../docs/MODELS.md` for preparation, calibration and deployment gates.

