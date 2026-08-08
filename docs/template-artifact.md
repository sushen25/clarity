# ADHD report template distillation contract

## Reference evidence

- Retained reference: `/Users/sushensatturu/Downloads/Edited_ ADHD Report.docx`
- SHA-256: `0efe70a6fbdcf04d66dc5588b3a8e65b65b8f84b1507f3ce064334cf3ced802f`
- Render: 20 A4 portrait pages; one section.
- Section geometry: A4 8.26 × 11.69 inches; 0.75-inch left/right and 1-inch top/bottom margins.
- Typography audit: Arial Narrow accounts for 44,096 characters. Most formatting is direct rather than semantic.
- Visual review: compact clinician report, circular practice mark near the upper left, pale teal horizontal section bars, a blue textured left rail, compact tables, and report charts in appendices.

## Clean template system

- The implementation template is newly constructed from the visual tokens below. No text, custom XML, metadata, comments, headers, footers, images, or other package parts are copied from the patient report.
- Page: A4 portrait, 0.75-inch left/right, 1.15-inch top and 0.8-inch bottom; 0.35-inch header/footer distance. The increased top clearance prevents the recurring header from overlapping continuation text.
- Normal: Arial Narrow 10 pt, dark slate, 1.08 line spacing, 3 pt after.
- Title: Arial Narrow 15 pt, bold, centered, dark slate, 10 pt after.
- Heading 1: Arial Narrow 10.5 pt, bold, uppercase, dark slate, kept with the following teal rule.
- Tables: 6.6-inch content width, narrative columns sized to content, light teal header fill where applicable, no fixed row heights.
- Diagnostic criteria: deterministic A1 and A2 tables on a new page, with a wide criterion column, compact clinician-outcome column, repeating teal headers, non-splitting rows, and explicit `Met`, `Not met`, `Insufficient evidence`, or `Not reviewed` states. Only clinician-set criterion outcomes are rendered; the model does not control this table.
- Header: generic `CLINICAL PSYCHOLOGY` / `ADHD ASSESSMENT` text and teal rule; no copied practice logo or patient-bearing artwork. A paragraph-based header is used so LibreOffice repeats it reliably on overflow pages.
- Footer: confidentiality notice and PAGE field.
- Page-style compatibility: the generator mirrors the default header and footer into explicit even-page and first-page parts so LibreOffice and Word render identical page furniture throughout the report.

## Content flow and slots

- Title and metadata slots: initials, cohort, assessment dates, instruments, clinician.
- Ordered repeatable section slot: heading plus zero or more clinically supported paragraphs. The model synthesises verified evidence into the prose using natural reporter and setting attribution; evidence identifiers, filenames, and source locations remain internal and are not printed in the final report.
- Diagnostic-criteria slot: all 18 criterion labels and clinician outcomes rendered independently of model-authored prose.
- Empty sections use an explicit “not supplied or not yet verified” message.
- Final review record: clinician, registration, draft version, model, prompt version, and approval state.
- Optional profile charts remain source attachments in the POC and are not embedded automatically.

## Fidelity and privacy gates

- Generated documents must remain A4 portrait with the stated margins and recurring header/footer.
- All pages must render without clipping, overlap, boundary-hugging table text, or orphaned headings.
- The repository template/package must contain none of the patient names, initials, dates, narrative, practitioner identity, or registration number from the reference.
- The original reference must remain byte-for-byte unchanged.
