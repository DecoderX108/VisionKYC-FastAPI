# API contracts

Interactive schemas: `http://localhost:8000/docs` during local development.
Versioned application routes are under `/api/v1/kyc`.

## 1. Document

```bash
curl -X POST http://localhost:8000/api/v1/kyc/verify-document \
  -F 'document_type=passport' \
  -F 'consent=true' \
  -F 'image=@/absolute/path/to/document.jpg'
```

`document_type`: `citizenship`, `passport`, or `pan`. A single still JPEG/PNG/WebP
file is required, up to 6 MiB and 16 million decoded pixels; at least 160 px per
side. PDFs, animated images and corrupt bytes are rejected. File extensions or
client MIME values are not trusted. Consent must be true.

Returns `document_id`, `session_token`, `expires_at`, `mode`, `classification`,
`boundary_detected`, `quality`, two JPEG data-URL previews and `warnings`.

The classifier's `predicted` value may be `unknown`; in demo its confidence is
null and `verified` is false. A user's selected type is only `requested`.

## 2. Start challenge

Use the returned UUID/token; placeholders below are not valid credentials:

```http
POST /api/v1/kyc/liveness/start
Authorization: Bearer <session_token>
Content-Type: application/json

{"document_id":"<document_uuid>"}
```

Returns a server-generated `challenge_id`, `status`, `prompt`, `step`,
`total_steps`, `progress`, `next_sequence`, and `assurance`. Starting a new attempt
invalidates the preceding attempt. Maximum 3 attempts per document session.

## 3. Send each frame in order

```http
POST /api/v1/kyc/liveness-check
Authorization: Bearer <session_token>
Content-Type: application/json

{
  "document_id":"<document_uuid>",
  "challenge_id":"<challenge_uuid>",
  "sequence":0,
  "image_base64":"data:image/jpeg;base64,<encoded_frame>"
}
```

Await each response before sending the next frame. Use the returned
`next_sequence`; never increment optimistically or retry a frame blindly.
Response fields include `ear`, `yaw_ratio`, `pad_live_score`, `quality` and
`issue`. In demo, EAR/yaw/PAD score remain null. A quality issue usually returns
200 with a prompt and consumes the sequence. No-face frames reset partial
evidence. `challenge_passed` indicates completion of the configured mode's
challenge, not a claim of identity or certified liveness.

## 4. Final selfie

```http
POST /api/v1/kyc/verify-face
Authorization: Bearer <session_token>
Content-Type: application/json

{
  "document_id":"<document_uuid>",
  "challenge_id":"<challenge_uuid>",
  "selfie_base64":"data:image/jpeg;base64,<fresh_high_resolution_frame>"
}
```

Use a fresh frame from the active stream after the challenge passes, at least
480 px per side. Submit within 20 seconds of server pass. Model mode rechecks PAD
and identity continuity with initial/last challenge embeddings. Final results
include decision, both distances, cosine similarity, `match_percentage`,
thresholds, reasons, and `completed_at`. Identical retries return the cached
result; substituting another selfie into a completed session is rejected.

## 5. Delete session

```http
DELETE /api/v1/kyc/sessions/<document_uuid>
Authorization: Bearer <session_token>
```

Returns 204. Data expires automatically if the browser closes without deletion.

## Errors

```json
{
  "error": {
    "code": "no_document_face",
    "message": "No portrait found on the document. Upload the portrait side with no glare",
    "request_id": "<diagnostic_reference>"
  }
}
```

| Status | Typical cause | Recovery |
|---|---|---|
| 401 | Missing/wrong session bearer token | Start over if token was lost |
| 409 | Replay, bad sequence, failed/missing challenge, replaced selfie | Restart challenge/session as prompted |
| 410 | Session/challenge/capture expiry | Restart challenge, or re-upload if session expired |
| 413 | Image or HTTP body too large | Resize/compress upload |
| 415 | Unsupported image format | Use still JPEG/PNG/WebP |
| 422 | Invalid schema, corrupt/no-face/low-quality image | Correct fields or recapture |
| 429 | Frame rate or attempt limit; proxy rate limit | Wait, or start a fresh verification |
| 500 | Unexpected model/inference failure | Use request reference to inspect backend logs |
| 503 | In-flight or session capacity exhausted | Retry after load falls or sessions expire |

The sample API does not return 403 for face endpoints: it uses 401 for session
authorization and 409 for workflow state failures. A 403 from a deployment may
come from an upstream auth/proxy layer. Browser camera permissions are separate
from HTTP API authorization. CORS failures are visible in browser DevTools and
should not be solved by disabling session authorization.

