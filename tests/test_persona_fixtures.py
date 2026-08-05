from __future__ import annotations

import json
from pathlib import Path

from app.parsers import validate_and_extract


ROOT = Path(__file__).resolve().parents[1] / "test-data" / "personas"


def test_synthetic_persona_library_is_complete_and_parseable():
    catalog = json.loads((ROOT / "catalog.json").read_text())
    assert len(catalog) == 5
    assert {item["cohort"] for item in catalog} == {"adult", "adolescent"}

    upload_count = 0
    seen_formats = set()
    for catalog_item in catalog:
        case_dir = ROOT / catalog_item["folder"]
        case = json.loads((case_dir / "case.json").read_text())
        sources = json.loads((case_dir / "source_manifest.json").read_text())
        oracle = json.loads((case_dir / "expected" / "clinician_review_oracle.json").read_text())

        assert case["cohort"] == catalog_item["cohort"]
        assert case["patient_initials"]
        assert case["referral_question"]
        assert case["cloud_consent"] is True
        assert len(sources) == catalog_item["source_count"]
        assert oracle["do_not_upload"] is True
        assert len(oracle["criterion_outcomes"]) == 18
        assert set(oracle["criterion_outcomes"]) == {
            *{f"A1.{index}" for index in range(1, 10)},
            *{f"A2.{index}" for index in range(1, 10)},
        }

        for expected_order, source in enumerate(sources, start=1):
            assert source["upload_order"] == expected_order
            assert set(("filename", "source_type", "reporter", "setting", "instrument")) <= set(source)
            path = (case_dir / source["filename"]).resolve()
            assert path.is_relative_to((case_dir / "inputs").resolve())
            assert path.is_file()
            text, _mime = validate_and_extract(path, path.name)
            assert len(text) >= 80
            assert "synthetic" in text.lower() or "fictional" in text.lower()
            seen_formats.add(path.suffix)
            upload_count += 1

    assert upload_count == 23
    assert seen_formats == {".txt", ".docx", ".pdf"}
