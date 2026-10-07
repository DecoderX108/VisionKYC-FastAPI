# Deployment and operation

## Docker deployment

1. Install Docker Engine + Compose v2 on the host.
2. Extract the project, copy `backend/.env.example` to `backend/.env`, and choose
   demo or configured model mode.
3. Run `docker compose up --build -d` from the project root.
4. Check `docker compose ps`, then visit `http://localhost:8080`.
5. Inspect `docker compose logs -f --tail=200` for startup and request errors.

The API container runs as UID 10001. Both application ports bind to loopback.
Model files mount read-only. The demo requires no persistent volume or database.
One Uvicorn worker is intentional because session state is in memory. If a
container restarts during verification, the user must restart the flow.

For an environment without a camera, you can still inspect OpenAPI, upload a
document and run tests. A real webcam session must be tested in a normal browser.

## HTTPS and browser permissions

`getUserMedia` requires a secure browser context. Localhost works for development;
a plain `http://192.168...` or public HTTP URL may not expose `mediaDevices`.
Terminate HTTPS at your existing reverse proxy and forward to
`http://127.0.0.1:8080`. Serve API and frontend through that same origin. For
example, a Caddy site block after replacing the domain and configuring DNS:

```caddyfile
kyc.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Use your organization's existing TLS/auth gateway where available. The included
nginx serves HTTP behind that gateway; it does not provision a certificate.
The frontend's production security headers allow its own camera, deny microphone
access, and disallow framing. Open it as a top-level page. If you intentionally
embed it, review the parent iframe `allow="camera"`, permissions policy and frame
policy together; do not remove unrelated protections blindly.

Nginx rate limits uploads and frames by the address it observes. Behind another
proxy, this may be the proxy address. Configure trusted real-IP forwarding with
explicit trusted proxy ranges before relying on per-user rate limits. Never
trust arbitrary internet-supplied forwarded IP headers.

## Public deployment integration

The included random session bearer credential prevents cross-session access but
does not authenticate a customer. Gate session creation using your existing
customer authentication and consent process, enforce account-level quotas, and
bind the verification session to that customer on the backend. Do not put a
private service key into `VITE_*` variables; those become public frontend code.

The app's approval is a scoped face/document decision. Integrate document
authenticity checks and your broader KYC policy separately. Decide how manual
reviews are routed and how users appeal false rejections. Calibrate models
before enabling automatic decisions; demo mode must remain clearly visible.

## Model deployment

Follow [MODELS.md](MODELS.md), install optional runtime dependencies and build
with `INSTALL_VISION=true`. Missing files or incorrect tensor contracts fail
startup. Paths are evaluated from `/app` in Docker (`weights/...` is correct).
Grant the container read access to files without making a model directory
world-writable. Use trusted model artifacts and record their versions/hashes.

## Logging

```bash
docker compose logs -f --tail=200
docker compose logs -f --tail=200 backend
docker compose logs --since=1h --no-log-prefix backend
```

JSON app events include request ID, route template, status and elapsed time.
They do not include raw face/document images, base64, embeddings, tokens, input
filenames, or query strings. Successful result events include mode and decision,
but no document UUID. API errors return the request ID for correlation. A raw
traceback/input dump is not enabled; instrument any deeper diagnostics with
appropriate redaction. Docker may also show normal Uvicorn lifecycle lines.

Logs are an operational trace, not an immutable compliance audit trail. Add a
separate audit system with defined access/retention if your service requires it.

## Troubleshooting

| Symptom | Check |
|---|---|
| Camera permission denied | Browser site settings; allow camera, close another app using it, retry |
| Camera API unavailable | HTTPS or localhost; open top-level page rather than a restricted preview iframe |
| Upload rejected | Portrait side, all corners, no glare, bright lighting, one face, >=160 px sides |
| PAN has no portrait | A face match requires a portrait-bearing document; route to another process |
| Multiple document faces | The largest detected crop is previewed and manual review is required; confirm it is the main portrait or improve the detector |
| Low light/blur prompt | Improve even lighting; clean lens; pause motion; allow autofocus |
| Blink never passes | Model mode and valid landmarks required; face forward, open eyes first, blink slowly; inspect frame latency |
| Wrong turn behavior | Capture is unmirrored; verify model pose proxy and left/right calibration for your deployment |
| 401 | Correct session token and document UUID; session may be lost after restart |
| 403 | Check upstream gateway/proxy auth; the sample's bearer failures are 401 |
| CORS | Exact allowed origin with protocol/port; prefer supplied same-origin proxy |
| Sequence/replay error | Await frame responses; restart challenge rather than resending an old frame |
| 429 attempt limit | Restart from document upload; max 3 attempts per session |
| All results manual review | Expected in demo or when thresholds are uncalibrated/document gates uncertain |
| Model startup failure | All four files, optional dependencies, expected tensor outputs and compatible runtime |
| Sessions disappear randomly | Ensure exactly one backend worker/process; add shared state before scaling |
