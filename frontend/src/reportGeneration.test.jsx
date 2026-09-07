import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { reportGenerationState, generationElapsed } from './reportGeneration';
import ReportGenerationStatus from './ReportGenerationStatus';

const job = { id: 'job-2', job_type: 'generate_draft', status: 'queued', attempts: 0, created_at: '2026-09-03T01:00:00Z' };
const previous = { version: 1, created_at: '2026-09-03T00:00:00Z' };
const next = { version: 2, created_at: '2026-09-03T01:01:00Z' };

describe('report generation lifecycle', () => {
  it('shows immediate feedback before the job request returns', () => {
    expect(reportGenerationState([], previous, true)).toMatchObject({ phase: 'submitting', active: true });
  });
  it('keeps the existing report visibly busy until downloads are finished', () => {
    expect(reportGenerationState([job], previous)).toMatchObject({ phase: 'queued', active: true });
    expect(reportGenerationState([{ ...job, status: 'running' }], previous)).toMatchObject({ phase: 'running', active: true });
    expect(reportGenerationState([{ ...job, status: 'running' }], next)).toMatchObject({ phase: 'finalising', active: true });
    expect(reportGenerationState([{ ...job, status: 'completed' }], next)).toMatchObject({ phase: 'completed', active: false, title: 'Version 2 is ready for review' });
  });
  it('does not announce an older draft as a newly completed version', () => {
    expect(reportGenerationState([{ ...job, status: 'completed' }], previous).phase).toBe('idle');
  });
  it('ignores historical failures and unrelated extraction jobs', () => {
    const old = { ...job, id: 'old', status: 'failed', created_at: '2026-09-02T00:00:00Z' };
    const extraction = { ...job, job_type: 'extract_source', created_at: '2026-09-04T00:00:00Z' };
    expect(reportGenerationState([old, extraction, { ...job, status: 'completed' }], next).phase).toBe('completed');
  });
  it('distinguishes automatic retries from terminal failures, including partial saves', () => {
    expect(reportGenerationState([{ ...job, attempts: 1 }], previous).title).toBe('Retrying report generation…');
    expect(reportGenerationState([{ ...job, status: 'failed' }], previous)).toMatchObject({ active: false, phase: 'failed', hasNewDraft: false });
    expect(reportGenerationState([{ ...job, status: 'failed' }], next).hasNewDraft).toBe(true);
  });
  it('renders accessible status and progress with a previous report present', () => {
    const html = renderToStaticMarkup(<ReportGenerationStatus state={reportGenerationState([job], previous)} draft={previous}/>);
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-current="step"');
    expect(html).toContain('Version 1 is shown below');
    expect(html).not.toContain('aria-valuenow');
  });
  it('never claims a failed export discarded the saved report', () => {
    const html = renderToStaticMarkup(<ReportGenerationStatus state={reportGenerationState([{ ...job, status: 'failed' }], next)} draft={next}/>);
    expect(html).toContain('role="alert"');
    expect(html).toContain('report text was saved');
    expect(html).not.toContain('No new report was saved');
  });
  it('formats elapsed time safely without inventing percent completion', () => {
    expect(generationElapsed(job.created_at, Date.parse(job.created_at) + 125000)).toBe('2m 5s elapsed');
    expect(generationElapsed(job.created_at, Date.parse(job.created_at) - 1000)).toBe('0s elapsed');
    expect(generationElapsed('invalid')).toBe('');
  });
});
