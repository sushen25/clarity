from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

from app.parsers import DocumentRejected, validate_and_extract


def test_txt_and_docx_parsing(tmp_path):
    txt = tmp_path / "source.txt"
    txt.write_text("Patient reported difficulty sustaining attention at work.", encoding="utf-8")
    text, mime = validate_and_extract(txt, "source.txt")
    assert "sustaining attention" in text
    assert mime == "text/plain"

    docx = tmp_path / "source.docx"
    document = Document()
    document.add_paragraph("Parent reported distractibility at home.")
    document.save(docx)
    text, mime = validate_and_extract(docx, "source.docx")
    assert "distractibility" in text
    assert "wordprocessingml" in mime


def test_rejects_scanned_encrypted_and_macro_files(tmp_path):
    blank_pdf = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with blank_pdf.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(DocumentRejected, match="no extractable text"):
        validate_and_extract(blank_pdf, "blank.pdf")

    fake = tmp_path / "macro.docx"
    with zipfile.ZipFile(fake, "w") as package:
        package.writestr("word/document.xml", "<document/>")
        package.writestr("word/vbaProject.bin", b"unsafe")
    with pytest.raises(DocumentRejected, match="Macro-enabled"):
        validate_and_extract(fake, "macro.docx")


def test_rejects_spoofed_extension(tmp_path):
    path = tmp_path / "spoof.pdf"
    path.write_text("not really a PDF")
    with pytest.raises(DocumentRejected, match="not a valid PDF"):
        validate_and_extract(path, "spoof.pdf")


def test_deidentified_adult_and_adolescent_fixtures_are_extractable():
    fixture_dir = Path(__file__).parent / "fixtures"
    for filename in ("adult_transcript.txt", "adolescent_collateral.txt"):
        text, mime = validate_and_extract(fixture_dir / filename, filename)
        assert "difficulty" in text.lower()
        assert mime == "text/plain"
