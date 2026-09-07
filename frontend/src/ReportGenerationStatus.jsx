import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, LoaderCircle } from 'lucide-react';
import { generationElapsed } from './reportGeneration';

export default function ReportGenerationStatus({ state, draft }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!state.active) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [state.active, state.job?.id]);
  if (state.phase === 'idle') return null;
  const failed = state.phase === 'failed';
  const Icon = state.active ? LoaderCircle : failed ? AlertTriangle : Check;
  const elapsed = state.job && generationElapsed(state.job.created_at, now);
  const delayed = state.active && state.job && now - new Date(state.job.created_at).getTime() > 120000;
  const detail = {
    submitting: 'Sending your request. This page will update automatically.',
    queued: state.job?.attempts > 0
      ? 'A temporary interruption occurred. Another attempt is scheduled automatically.'
      : 'Waiting to start. You can visit other sections or return to this case later.',
    running: 'Preparing report sections from your verified evidence. This may take a few minutes.',
    finalising: 'The report text has been saved. Preparing the Word document and available PDF preview.',
    completed: 'The latest report is shown below. Review the content and any warnings before approval.',
    failed: state.hasNewDraft
      ? 'The report text was saved, but generation did not finish. You can review the saved text below or retry to create a new version.'
      : 'No new report was saved. Retry generation; if it fails again, contact your administrator.',
  }[state.phase];
  return <div className={`generation-status ${failed ? 'failed' : state.active ? 'active' : 'completed'}`}>
    <Icon className={state.active ? 'generation-spinner' : ''} size={23} aria-hidden="true"/>
    <div className="generation-copy">
      <div role={failed ? 'alert' : 'status'} aria-live={failed ? 'assertive' : 'polite'} aria-atomic="true"><strong>{state.title}</strong><p>{detail}</p></div>
      {state.active && <>
        <ol className="generation-steps" aria-label="Report generation progress">
          {['Queued', 'Generating', 'Preparing downloads'].map((label, index) => {
            const current = { submitting: 0, queued: 0, running: 1, finalising: 2 }[state.phase];
            return <li key={label} className={index < current ? 'done' : index === current ? 'current' : ''} aria-current={index === current ? 'step' : undefined}>{index < current ? <Check size={13}/> : <span>{index + 1}</span>}{label}</li>;
          })}
        </ol>
        <small>{elapsed}{elapsed && ' · '}Updates automatically. You can leave this page and return later.</small>
        {draft && state.phase !== 'finalising' && <p>Version {draft.version} is shown below for reference while the new version is generated.</p>}
        {delayed && <p>This is taking longer than usual. You do not need to submit another request.{state.phase === 'queued' && ' If it remains queued, ask your administrator to check the background worker.'}</p>}
      </>}
      {failed && state.job?.last_error && <details><summary>Error details</summary><code>{state.job.last_error}</code></details>}
    </div>
  </div>;
}
