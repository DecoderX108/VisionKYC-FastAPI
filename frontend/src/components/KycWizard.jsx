import { useCallback, useEffect, useRef, useState } from 'react';
import { api, deleteSession, errorMessage, uploadDocument } from '../api';
import CameraCapture from './CameraCapture';
import DocumentUpload from './DocumentUpload';
import VerificationResult from './VerificationResult';

export default function KycWizard() {
  const [session, setSession] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  const uploadController = useRef(null);
  const inFlight = useRef(false);
  const step = result ? 2 : session ? 1 : 0;
  useEffect(() => {
    const abort = new AbortController();
    api.get('/health', {signal: abort.signal}).then(response => setHealth(response.data)).catch(() => {});
    return () => {abort.abort(); uploadController.current?.abort();};
  }, []);

  async function submitDocument(file, type) {
    if (inFlight.current) return;
    inFlight.current = true;
    const abort = new AbortController();
    uploadController.current = abort;
    setBusy(true); setError('');
    try {setSession(await uploadDocument(file, type, abort.signal));}
    catch (failure) {if (!abort.signal.aborted) setError(errorMessage(failure));}
    finally {inFlight.current = false; if (!abort.signal.aborted) setBusy(false);}
  }
  const restart = useCallback(async () => {
    setBusy(true); setError('');
    try {
      await deleteSession(session);
      setSession(null); setResult(null);
    } catch (failure) {
      if ([401, 410].includes(failure.response?.status)) {setSession(null); setResult(null);}
      else setError(errorMessage(failure));
    } finally {setBusy(false);}
  }, [session]);

  return <div className="min-h-screen">
    <header className="page-header"><a href="/" className="brand"><span className="brand-mark" aria-hidden="true">V</span>Vision<span className="font-normal opacity-60">KYC</span></a><span className="header-label">IDENTITY VERIFICATION</span><span className="mode-pill">{health ? `${health.mode} mode` : 'Connecting…'}</span></header>
    <main className="page-main">
      <aside className="intro">
        <span className="eyebrow">A CLEARER WAY TO VERIFY</span>
        <h1>Your identity.<br/>One simple flow.</h1>
        <p className="intro-copy">A document, a live capture, and a transparent verification result.</p>
        <ol className="steps" aria-label="Verification steps">{['Upload document', 'Live camera check', 'View result'].map((label, index) => <li key={label} className={step === index ? 'active' : step > index ? 'done' : ''} aria-current={step === index ? 'step' : undefined}><span>{step > index ? '✓' : `0${index+1}`}</span><div><strong>{label}</strong><small>{['Citizenship, passport or PAN card', 'Follow the prompts on screen', 'Scores, checks and next steps'][index]}</small></div></li>)}</ol>
        <div className="privacy-note"><span aria-hidden="true">◇</span><p>Processed in memory.<br/><strong>No image files saved by this app.</strong></p></div>
      </aside>
      <div className="workspace-card">
        {error && <p className="error-box mb-5" role="alert">{error}</p>}
        {result ? <VerificationResult result={result} onRestart={busy ? () => {} : restart} />
          : session ? <><div className="document-summary"><img src={session.document_face_preview} alt="Portrait extracted from your document"/><div><strong>Document received</strong><p>{session.classification.requested} · {session.classification.verified ? 'Type verified' : 'Type unverified'}</p></div><span aria-hidden="true">✓</span></div>
            {session.warnings.length > 0 && <details className="mb-6 text-sm muted"><summary className="cursor-pointer">Document notes ({session.warnings.length})</summary><ul className="mt-2 space-y-2">{session.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></details>}
            <CameraCapture session={session} onComplete={setResult} onRestart={restart} /></>
          : <DocumentUpload onSubmit={submitDocument} busy={busy} />}
      </div>
    </main>
    <footer>Vision KYC Framework <span>Document → Capture → Verify</span></footer>
  </div>;
}

