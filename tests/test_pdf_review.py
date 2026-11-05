"""Original PDF fixture verifies real text extraction and page provenance."""
import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from evidence.domain import extract


PDF = Path(__file__).resolve().parents[1] / 'fixtures/pdf/original-two-pages.pdf'


def test_original_text_pdf_preserves_page_evidence():
    sections = extract(PDF.name, PDF.read_bytes())
    assert len(sections) == 2
    assert sections[0][0] == 'Page 1'
    assert 'review travel receipts within seven days' in sections[0][1]
    assert sections[1][0] == 'Page 2'
    assert 'lost access badge' in sections[1][1]


def test_encrypted_pdf_is_rejected_before_indexing():
    writer = PdfWriter()
    writer.append(PdfReader(PDF))
    writer.encrypt('synthetic-test-password')
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match='unencrypted'):
        extract('encrypted.pdf', buffer.getvalue())
