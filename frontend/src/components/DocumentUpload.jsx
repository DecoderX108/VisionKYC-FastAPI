import { useEffect, useRef, useState } from 'react';

const accepted = ['image/jpeg', 'image/png', 'image/webp'];

export default function DocumentUpload({onSubmit, busy}) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [type, setType] = useState('citizenship');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);
  const input = useRef(null);

  useEffect(() => {
    if (!file) {setPreview(''); return;}
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFile(selected) {
    setError('');
    if (!selected) return;
    if (!accepted.includes(selected.type)) {setError('Choose a JPEG, PNG, or WebP photo.'); return;}
    if (!selected.size || selected.size > 6 * 1024 * 1024) {setError('Choose a non-empty image under 6 MB.'); return;}
    setFile(selected);
  }

  return <form onSubmit={event => {event.preventDefault(); if (file && consent && !busy) onSubmit(file, type);}}>
    <div className="eyebrow">STEP 01 / DOCUMENT</div>
    <h2>Start with your identity document.</h2>
    <p className="muted mt-3">Use a clear photo of the side containing your portrait. Keep all four corners visible.</p>
    <label className="field-label mt-7" htmlFor="document-type">Document type</label>
    <select id="document-type" value={type} onChange={event => setType(event.target.value)} disabled={busy}>
      <option value="citizenship">Citizenship</option><option value="passport">Passport</option><option value="pan">PAN card</option>
    </select>
    <input ref={input} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="Select document photo" disabled={busy}
      onChange={event => {selectFile(event.target.files?.[0]); event.target.value = '';}} />
    <button type="button" disabled={busy} onClick={() => input.current?.click()}
      onDragOver={event => {event.preventDefault(); if (!busy) setDragging(true);}}
      onDragLeave={() => setDragging(false)}
      onDrop={event => {event.preventDefault(); setDragging(false); if (!busy) selectFile(event.dataTransfer.files?.[0]);}}
      className={`dropzone ${dragging ? 'dragging' : ''}`}>
      {preview ? <img src={preview} alt="Selected document preview" className="max-h-64 max-w-full rounded-lg object-contain" /> : <>
        <span className="upload-icon" aria-hidden="true">↑</span><strong>Drop your document here</strong><span>or click to choose a photo</span>
      </>}
      <span className="text-xs muted">{file ? `${file.name} · Click to replace` : 'JPEG, PNG or WebP · Up to 6 MB'}</span>
    </button>
    {error && <p role="alert" className="error-box">{error}</p>}
    <label className="flex items-start gap-3 text-sm mt-6 leading-6">
      <input type="checkbox" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)} className="mt-1" />
      <span>I consent to processing my document and face for this verification session. Images are processed in memory and session data expires after 10 minutes by default.</span>
    </label>
    <button className="primary mt-7 w-full" disabled={!file || !consent || busy}>{busy ? 'Analyzing document…' : 'Analyze document →'}</button>
  </form>;
}

