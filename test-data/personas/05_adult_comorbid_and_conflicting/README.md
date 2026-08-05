# 05_adult_comorbid_and_conflicting

Adult with developmental and cross-setting ADHD evidence, clinically significant anxiety, and a university reporter who sees limited outward impairment.

All people, organisations, events, instruments, and values in this folder are fictional. Use them only for software and clinical-workflow testing.

## Run the case

1. Create a case using `case.json`.
2. For every row in `source_manifest.json`, upload the named file and copy the listed source metadata into the upload form.
3. Wait for extraction, then review and verify appropriate evidence. Do not blindly verify every extraction.
4. Add the already-scored fictional values from instrument summary files as instrument summaries and mark them verified after checking the source.
5. Review all 18 criteria, enter a clinician-authored test conclusion, generate a draft, inspect evidence links, and test approval/rendering.
6. Compare behaviour with `expected/clinician_review_oracle.json`. Never upload the expected folder: it is a test oracle, not clinical evidence.

The suggested outcomes are deliberately not included in the upload inputs. They are expectations for testing software behaviour, not diagnoses or clinical advice.
