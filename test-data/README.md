# Synthetic test data

The `personas` directory contains reproducible, entirely fictional assessment cases for exercising Clarity. No file is derived from a real person, the supplied example report, or a proprietary questionnaire.

Generate or refresh the fixture library with:

```sh
python scripts/generate_test_personas.py
```

Each persona contains:

- `case.json`: fields for case creation;
- `source_manifest.json`: upload order and metadata;
- `inputs/`: supported TXT, DOCX, and text-based PDF source documents;
- `expected/clinician_review_oracle.json`: expected warnings, contradictions, and suggested criterion outcomes;
- `README.md`: a case-specific test procedure.

Never upload the `expected` directory. It is a test oracle and would contaminate the evidence ledger with the expected result.

The instrument names and values are intentionally fictional. The fixtures do not reproduce proprietary questions, calculate scores, or provide clinical advice.
