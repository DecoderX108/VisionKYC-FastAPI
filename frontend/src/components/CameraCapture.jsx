import { useEffect, useRef, useState } from 'react';
import { checkFrame, errorMessage, startChallenge, verifyFace } from '../api';

function cameraError(error) {
  if (error.name === 'NotAllowedError') return 'Camera access was denied. Allow camera access in your browser site settings, then retry.';
  if (error.name === 'NotFoundError') return 'No camera was found. Connect a camera and retry.';
  if (error.name === 'NotReadableError') return 'Your camera may be in use by another app. Close it and retry.';
  if (error.name === 'OverconstrainedError') return 'This camera cannot supply the requested resolution. Try another camera.';
  return errorMessage(error);
}

export function captureFrame(video, maxWidth) {
  if (!video?.videoWidth || video.readyState < 2) throw new Error('The camera is not ready yet.');
  const scale = Math.min(1, maxWidth / video.videoWidth);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  // Mirror the preview with CSS only; backend pixels remain unmirrored.
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', maxWidth > 640 ? 0.93 : 0.80);
}

export default function CameraCapture({session, onComplete, onRestart}) {
  const video = useRef(null);
  const stream = useRef(null);
  const controller = useRef(null);
  const mounted = useRef(true);
  const running = useRef(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState('');
  const [cameraAttempt, setCameraAttempt] = useState(0);

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    let ownedStream = null;
    setError(''); setReady(false); setCameraReady(false);
    async function openCamera() {
      try {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
          throw new Error('Camera access requires HTTPS or localhost. Open this page in a secure browser tab.');
        }
        ownedStream = await navigator.mediaDevices.getUserMedia({audio: false, video: {
          facingMode: 'user', width: {ideal: 1920}, height: {ideal: 1080}, frameRate: {ideal: 24},
        }});
        if (cancelled) {ownedStream.getTracks().forEach(track => track.stop()); return;}
        stream.current = ownedStream;
        video.current.srcObject = ownedStream;
        await video.current.play();
        if (!cancelled) setCameraReady(true);
      } catch (failure) {
        ownedStream?.getTracks().forEach(track => track.stop());
        if (!cancelled) setError(cameraError(failure));
      }
    }
    openCamera();
    return () => {
      cancelled = true; mounted.current = false;
      controller.current?.abort();
      ownedStream?.getTracks().forEach(track => track.stop());
    };
  }, [cameraAttempt]);

  async function runChallenge() {
    if (running.current) return;
    running.current = true;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError(''); setStatus(null);
    try {
      let state = await startChallenge(session, abort.signal);
      const challengeId = state.challenge_id;
      if (mounted.current) setStatus(state);
      const started = performance.now();
      // Await each request; setInterval would overlap frames and race sequences.
      while (!abort.signal.aborted && state.status === 'IN_PROGRESS') {
        if (performance.now() - started > 180000) throw new Error('Challenge timed out. Please retry.');
        if (document.hidden) throw new Error('Keep this tab visible during the camera check. Please retry.');
        state = await checkFrame(session, challengeId, state.next_sequence, captureFrame(video.current, 640), abort.signal);
        if (mounted.current) setStatus(state);
        if (state.status === 'IN_PROGRESS') await new Promise(resolve => setTimeout(resolve, 100));
      }
      if (abort.signal.aborted) return;
      if (!state.challenge_passed) throw new Error(state.issue || 'Challenge failed. Please try again.');
      // A fresh full-resolution frame from the same active MediaStream.
      const selfie = captureFrame(video.current, 1920);
      const result = await verifyFace(session, challengeId, selfie, abort.signal);
      stream.current?.getTracks().forEach(track => track.stop());
      if (mounted.current) onComplete(result);
    } catch (failure) {
      if (!abort.signal.aborted && mounted.current) setError(errorMessage(failure));
    } finally {
      running.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  return <section>
    <div className="eyebrow">STEP 02 / LIVE CAPTURE</div>
    <h2>A quick check. A clear selfie.</h2>
    <p className="muted mt-3">Face the camera in even light. Follow each prompt and keep this tab open.</p>
    {session.mode === 'demo' && <p className="notice mt-5">Demo mode checks framing and image quality. It does not establish liveness or verify identity.</p>}
    <div className="camera-panel mt-6">
      <video ref={video} autoPlay muted playsInline onLoadedData={() => setReady(true)} className="camera-video" aria-label="Live camera preview" />
      <div className="face-guide" aria-hidden="true" />
      <div className="camera-prompt" role="status" aria-live="polite">{status?.prompt || (ready ? 'Position your face inside the guide' : 'Connecting to your camera…')}</div>
    </div>
    <div className="progress-track mt-4" role="progressbar" aria-label="Liveness challenge progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((status?.progress || 0)*100)}>
      <div style={{width: `${(status?.progress || 0)*100}%`}} />
    </div>
    {status?.quality && <div className="flex gap-5 text-xs muted mt-3"><span>Brightness {Math.round(status.quality.brightness)}/255</span><span>Focus {Math.round(status.quality.sharpness)}</span><span>{status.step}/{status.total_steps} steps</span></div>}
    {error && <p className="error-box mt-4" role="alert">{error}</p>}
    <div className="flex flex-wrap gap-3 mt-6">
      {cameraReady ? <button className="primary flex-1" disabled={!ready || busy} onClick={runChallenge}>{busy ? 'Checking…' : status ? 'Retry camera check' : 'Start camera check →'}</button>
        : <button className="primary flex-1" onClick={() => setCameraAttempt(value => value+1)}>Retry camera access</button>}
      <button className="secondary" disabled={busy} onClick={onRestart}>Start over</button>
    </div>
    <p className="text-xs muted mt-4">Your camera turns off after completion or when you leave this step.</p>
  </section>;
}

