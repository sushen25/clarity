export function reportGenerationState(jobs = [], draft, submitting = false) {
  const reportJobs = jobs.filter(job => job.job_type === 'generate_draft')
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  const job = reportJobs.find(job => ['queued', 'running'].includes(job.status)) || reportJobs[0];
  const hasNewDraft = !!(draft && job && new Date(draft.created_at) >= new Date(job.created_at));
  if (submitting) return { phase: 'submitting', active: true, title: 'Requesting your report…', job };
  if (!job) return { phase: 'idle', active: false };
  if (job.status === 'queued') return {
    phase: 'queued', active: true, job,
    title: job.attempts > 0 ? 'Retrying report generation…' : 'Your report is queued',
  };
  if (job.status === 'running') return {
    phase: hasNewDraft ? 'finalising' : 'running', active: true, job,
    title: hasNewDraft ? 'Preparing report downloads…' : 'Generating your report…',
  };
  if (job.status === 'failed') return { phase: 'failed', active: false, job, hasNewDraft, title: 'Report generation could not finish' };
  if (job.status === 'completed' && hasNewDraft) return {
    phase: 'completed', active: false, job, title: `Version ${draft.version} is ready for review`,
  };
  return { phase: 'idle', active: false };
}

export function generationElapsed(createdAt, now = Date.now()) {
  const seconds = Math.max(0, Math.floor((now - new Date(createdAt).getTime()) / 1000));
  if (!Number.isFinite(seconds)) return '';
  return seconds < 60 ? `${seconds}s elapsed` : `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed`;
}
