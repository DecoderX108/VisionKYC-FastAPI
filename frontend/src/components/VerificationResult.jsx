export default function VerificationResult({result, onRestart}) {
  const approved = result.decision === 'APPROVED';
  const rejected = result.decision === 'REJECTED';
  const label = approved ? 'Verification approved' : rejected ? 'Verification rejected' : 'Manual review required';
  const t = result.thresholds;
  return <section>
    <div className="eyebrow">STEP 03 / RESULT</div>
    <div className={`result-badge ${approved ? 'approved' : rejected ? 'rejected' : ''}`} aria-hidden="true">{approved ? '✓' : rejected ? '×' : '↗'}</div>
    <h2>{label}</h2>
    <ul className="muted mt-4 space-y-2">{result.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
    <div className="score-card mt-7"><div><span className="eyebrow">{result.mode === 'demo' ? 'DEMO SIMILARITY' : 'FACE SIMILARITY'}</span><div className="score">{result.match_percentage.toFixed(1)}<span>%</span></div></div><span className="mode-pill">{result.mode.toUpperCase()}</span></div>
    <p className="text-xs muted mt-3">{result.score_note}</p>
    <dl className="metrics mt-6"><div><dt>Cosine similarity</dt><dd>{result.cosine_similarity.toFixed(4)}</dd></div><div><dt>Cosine distance</dt><dd>{result.cosine_distance.toFixed(4)}</dd></div><div><dt>Euclidean distance</dt><dd>{result.euclidean_distance.toFixed(4)}</dd></div><div><dt>Document classification</dt><dd>{result.classification.verified ? result.classification.predicted : 'Unverified'}</dd></div></dl>
    <details className="mt-5"><summary className="cursor-pointer font-semibold text-sm">Threshold breakdown</summary>
      <div className="overflow-x-auto"><table className="mt-3 w-full text-sm"><thead><tr><th>Check</th><th>Threshold</th></tr></thead><tbody>
        <tr><td>Approve face score</td><td>≥ {t.approve_similarity_gte}</td></tr>
        <tr><td>Review face score</td><td>≥ {t.reject_similarity_lt} and &lt; {t.approve_similarity_gte}</td></tr>
        <tr><td>Reject face score</td><td>&lt; {t.reject_similarity_lt}</td></tr>
        <tr><td>Face continuity</td><td>≥ {t.continuity_similarity_gte}</td></tr>
        <tr><td>Document confidence</td><td>≥ {t.document_confidence_gte}</td></tr>
        <tr><td>PAD live score</td><td>≥ {t.pad_live_score_gte}</td></tr>
        <tr><td>Calibrated deployment</td><td>{t.calibrated ? 'Yes' : 'No — manual review'}</td></tr>
      </tbody></table></div><p className="text-xs muted mt-3">Approval also requires every document, presentation and challenge gate to pass.</p>
    </details>
    <button className="primary mt-7 w-full" onClick={onRestart}>Start a new verification</button>
  </section>;
}

