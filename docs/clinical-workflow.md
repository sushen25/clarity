# Clinical workflow and safeguards

## Intended use

Clarity assists registered clinicians drafting Australian adult and adolescent ADHD assessment reports. It organises supplied evidence and prepares editable prose. It does not diagnose, independently establish facts, score instruments, select a final diagnostic outcome, or sign a report.

The workflow reflects the core principle that diagnosis combines clinical and psychosocial assessment, developmental, medical, and mental-health history, observer evidence, functional impairment across settings, differential considerations, strengths, and appropriately interpreted rating scales. Rating scales are supporting evidence, never a sufficient basis on their own.

## Case lifecycle

### 1. Create the case

The clinician chooses `adult` or `adolescent` and records demographics, referral question, assessment dates, clinician details, and instruments administered. The cohort selects a separately versioned clinical schema and report template contract.

Before any Bedrock operation, the clinician must acknowledge that the patient privacy notice and consent permit AI processing in Australia. With Bedrock disabled, the local development organiser may be used on synthetic or approved de-identified material.

### 2. Add source material

Supported inputs are:

- UTF-8 text files;
- ordinary DOCX files without macros;
- text-based PDFs;
- authorised, already-scored instrument result exports.

Each upload is limited to 25 MB by default. Executables, macro-enabled Word documents, encrypted or malformed documents, spoofed formats, and unsupported types are rejected. A scanned PDF without extractable text is reported as a gap; OCR and audio transcription are outside the POC.

For every source, capture its type, reporter, setting, date, and instrument where relevant. A source with an unknown reporter or setting can be stored, but will contribute to completeness warnings.

### 3. Review the evidence ledger

Extraction proposes evidence items with:

- clinical domain;
- reporter and setting;
- source page or paragraph location;
- a short supporting passage;
- extraction confidence;
- possible contradiction status.

The clinician corrects these fields and explicitly verifies useful evidence. Conflicting accounts are preserved and surfaced rather than silently reconciled. Low confidence indicates extraction uncertainty, not the strength or credibility of the clinical evidence.

The domain must be one of `referral`, `strengths`, `developmental`, `medical`, `mental_health`, `family_social`, `education_work`, `inattention`, `hyperactivity_impulsivity`, `impairment`, `observations`, `differential`, `instrument`, `recommendation`, or `other`. The extraction prompt supplies a definition for every value and tells the model to choose the most specific applicable domain. `other` is reserved for relevant evidence that genuinely fits none of the defined clinical domains. Clinicians can correct the domain from each evidence card before verification.

During drafting, paragraphs containing unknown evidence identifiers or no verified evidence link are blocked rather than causing the entire draft to be discarded. The only evidence-free paragraph allowed is an exact copy of the clinician-entered diagnostic conclusion in the summary. Each blocked paragraph adds a visible validation warning; its clinical text is not written to logs.

### 4. Verify instrument summaries

The clinician enters or verifies the instrument name and version, respondent, supplied scale or index values, and clinical interpretation. The application does not reproduce proprietary questions, derive scores from raw responses, or treat thresholds as a diagnosis. Any discrepancy between a supplied export and a draft must be corrected before approval.

### 5. Decide diagnostic criteria

All 18 ADHD criteria are presented for clinician review. The model may propose linked evidence and draft explanatory text, but the clinician sets the outcome and notes for every criterion. Evidence links retain reporter, setting, and impairment context.

The Report review screen and generated DOCX include deterministic A1 and A2 criteria tables. Each row reports the clinician-set outcome as `Met`, `Not met`, `Insufficient evidence`, or `Not reviewed`; the model cannot add, remove, or change a criterion-table decision. Regenerating or rendering a draft refreshes the DOCX table from the current criterion assessments.

The final diagnostic conclusion is a separate clinician-entered decision. It may be positive, negative, provisional, or another clinically appropriate conclusion represented by the available schema; it is never inferred solely from a criterion count or rating scale.

### 6. Resolve completeness warnings

The application checks for:

- developmental history;
- medical assessment and relevant health history;
- mental-health and psychosocial history;
- impairment evidence;
- differential or comorbid considerations;
- strengths and protective factors;
- evidence across at least two settings;
- collateral or observer evidence where expected, especially for adolescents;
- verified source evidence;
- consent for Australian AI processing when Bedrock is used.

A warning is not automatically evidence that a diagnosis is invalid. It is a visible prompt for clinician review. Unresolved warnings require explicit acknowledgement and remain in the approved snapshot.

### 7. Draft and edit the report

The current report template maps reviewed material into:

1. referral and presenting concerns;
2. relevant background and developmental history;
3. ADHD interview findings;
4. behavioural or clinical observations;
5. instrument results and clinician interpretations;
6. cognitive findings when supplied;
7. diagnostic criteria, impairment, and differential considerations;
8. diagnostic summary and clinician conclusion;
9. recommendations grounded in verified information; and
10. a clinical review record containing draft provenance and approval state.

Strengths and protective factors are currently incorporated into background information. The drafting prompt requires verified evidence to be interwoven into cohesive clinical prose, with natural attribution to the patient, collateral reporters, clinician observations, or instruments and with supplied examples, settings, functional impacts, uncertainties, and contradictions retained. Evidence identifiers, filenames, and source locations remain available inside the review workflow but are not printed in the final DOCX. Authorised profile-chart appendices remain a planned extension and are not automatically embedded by the POC.

Each generated paragraph retains internal evidence identifiers. The prompt requires unsupported sections to remain empty instead of adding generic or transitional prose; any claims still returned without verified support are blocked and visibly flagged. Recommendations must be framed for clinician review and grounded in the case record; the model cannot invent medication instructions, referrals, scores, history, or risk statements.

### 8. Approve and export

Approval is unavailable until:

- the draft is marked review-ready;
- the clinician has set a final conclusion;
- all 18 criteria have clinician-set outcomes;
- at least one evidence item is verified;
- required AI consent is recorded where applicable; and
- the clinician acknowledges all unresolved completeness warnings.

Approval records an immutable snapshot. Later edits create a new draft version rather than changing the approved record. DOCX output remains editable, so any changes made outside Clarity are outside its audit trail and should follow the practice’s document-control process.

## Human-review rules

- Never copy a generated conclusion into a clinical record without checking it against sources.
- Open the linked evidence for every material clinical claim.
- Reconcile instrument names, versions, respondents, dates, values, and interpretation with the authorised export.
- Review contradictions and missing settings explicitly.
- Check recommendations for relevance, scope of practice, feasibility, and risk.
- Inspect the final DOCX and preview for omissions, pagination, table clipping, and accidental identifying data.
- The approving clinician remains responsible for the assessment, diagnosis, and signed report.
