from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


TEAL = "6EB7C3"


def _shade(cell, fill: str) -> None:
    props = cell._tc.get_or_add_tcPr()
    node = props.find(qn("w:shd"))
    if node is None:
        node = OxmlElement("w:shd")
        props.append(node)
    node.set(qn("w:fill"), fill)


def _heading(doc: Document, text: str, page_break_before: bool = False) -> None:
    paragraph = doc.add_paragraph(style="Heading 1")
    paragraph.paragraph_format.keep_with_next = True
    paragraph.paragraph_format.page_break_before = page_break_before
    run = paragraph.add_run(text.upper())
    run.bold = True
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    table.columns[0].width = Inches(6.6)
    cell = table.cell(0, 0)
    _shade(cell, TEAL)
    cell.text = ""
    cell.height = Pt(4)


def generate_docx(template_path: Path, output_path: Path, case: dict, draft: dict,
                  clinician: dict, evidence_by_id: dict[str, dict]) -> None:
    doc = Document(template_path)
    body = doc._element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("CONFIDENTIAL ASSESSMENT REPORT")
    run.bold = True
    run.font.size = Pt(15)
    run.font.color.rgb = RGBColor.from_string("173A44")

    metadata = doc.add_table(rows=0, cols=2)
    metadata.autofit = False
    values = [
        ("NAME / INITIALS", case["patient_initials"]),
        ("COHORT", case["cohort"].title()),
        ("DATES ASSESSED", ", ".join(case.get("assessment_dates", []))),
        ("ASSESSMENT INSTRUMENTS", ", ".join(case.get("instruments", []))),
        ("ASSESSMENT CONDUCTED BY", f"{clinician['full_name']}, Psychologist"),
    ]
    for label, value in values:
        cells = metadata.add_row().cells
        cells[0].width, cells[1].width = Inches(1.7), Inches(4.9)
        cells[0].paragraphs[0].add_run(label).bold = True
        cells[1].text = value or "Not provided"
    doc.add_paragraph()

    for section in draft["sections"]:
        _heading(doc, section["heading"])
        if not section.get("paragraphs"):
            paragraph = doc.add_paragraph("Information not supplied or not yet verified.")
            paragraph.runs[0].italic = True
            paragraph.runs[0].font.color.rgb = RGBColor(100, 100, 100)
            continue
        for item in section["paragraphs"]:
            paragraph = doc.add_paragraph(item["text"])
            paragraph.paragraph_format.space_after = Pt(7)
            ids = item.get("evidence_ids", [])
            if ids:
                sources = []
                for evidence_id in ids:
                    evidence = evidence_by_id.get(evidence_id)
                    if evidence:
                        sources.append(f"{evidence.get('original_filename','source')} — {evidence.get('source_location','')}")
                if sources:
                    citation = doc.add_paragraph(style="Evidence Citation")
                    citation.add_run("Evidence: " + "; ".join(sources))

    _heading(doc, "Clinical Review Record", page_break_before=True)
    doc.add_paragraph(
        "This document was generated as a clinician drafting aid. The diagnostic conclusion and criterion decisions "
        "remain the responsibility of the approving clinician."
    )
    review = doc.add_table(rows=0, cols=2)
    for label, value in [
        ("Clinician", clinician["full_name"]),
        ("Registration", clinician.get("registration_number") or "Not provided"),
        ("Draft version", str(draft["version"])),
        ("Model", draft["model_id"]),
        ("Prompt version", draft["prompt_version"]),
        ("Approval state", draft["state"]),
    ]:
        cells = review.add_row().cells
        cells[0].paragraphs[0].add_run(label).bold = True
        cells[1].text = value

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)


def render_preview(docx_path: Path, preview_dir: Path, soffice: str) -> Path | None:
    preview_dir.mkdir(parents=True, exist_ok=True)
    binary = shutil.which(soffice)
    if not binary:
        return None
    profile = preview_dir / ".lo-profile"
    profile.mkdir(exist_ok=True)
    command = [binary, "--headless", f"-env:UserInstallation=file://{profile}", "--convert-to", "pdf",
               "--outdir", str(preview_dir), str(docx_path)]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    pdf = preview_dir / f"{docx_path.stem}.pdf"
    if completed.returncode != 0 or not pdf.exists():
        return None
    return pdf
