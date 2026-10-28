"""Small synthetic files exercise real parsers; native OCR is separately optional."""

import hashlib
import shutil
from datetime import date
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from sqlalchemy import select

from app.document_processing.extraction.chunking import logical_chunks
from app.document_processing.extraction.email import EmailExtractor
from app.document_processing.extraction.formats import (
    DOCXExtractor,
    PDFTextExtractor,
    XLSXExtractor,
)
from app.document_processing.extraction.ocr import ImageExtractor, ScannedPDFExtractor, TesseractOCR
from app.document_processing.extraction.service import DocumentExtractionService
from app.document_processing.extraction.types import ExtractionResult, TextBlock
from app.document_processing.pipeline import STAGES, extraction_result
from app.domain.models import DocumentChunk
from tests.test_processing_pipeline import pipeline  # noqa: F401 - pytest fixture

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"


def fixture(name):
    return (FIXTURES / name).read_bytes()


def test_pdf_native_text_page_numbers_and_coordinates():
    result = PDFTextExtractor().extract(fixture("contract.pdf"))
    assert "Supply concrete" in result.text
    assert {b.page_number for b in result.blocks} == {1, 2}
    for block in result.blocks:
        assert block.location["source"] == "pdf_text"
        assert block.location["unit"] == "point"
        x0, y0, x1, y1 = block.location["bbox"]
        assert 0 <= x0 < x1 <= 612 and 0 <= y0 < y1 <= 792
    parts = logical_chunks(result, "contract")
    assert [p.section for p in parts] == ["1 Scope", "2 Payment"]
    assert [p.page_number for p in parts] == [1, 2]


def test_scanned_pdf_renders_each_page_with_original_number(monkeypatch, tmp_path):
    calls = []

    def render(args, **kwargs):
        calls.append(args)
        Path(args[-1]).with_suffix(".png").write_bytes(fixture("report.png"))
        return SimpleNamespace(returncode=0)

    ocr = Mock()
    ocr.recognize.side_effect = lambda content, page_number=1: [
        TextBlock(text="Daily Report", page_number=page_number, location={"source": "mock_ocr"})
    ]
    monkeypatch.setattr("app.document_processing.extraction.ocr.subprocess.run", render)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    result = ScannedPDFExtractor(ocr).extract(fixture("scanned.pdf"))
    assert result.blocks[0].page_number == 1
    assert calls[0][calls[0].index("-f") + 1] == "1"
    assert "-singlefile" in calls[0]
    ocr.recognize.assert_called_once()


def test_mixed_pdf_only_ocr_scanned_page():
    scanned = Mock()
    scanned.page.return_value = [TextBlock(text="Scanned second page", page_number=2)]
    content = fixture("mixed.pdf")
    result = PDFTextExtractor(scanned).extract(content)
    scanned.page.assert_called_once_with(content, 2)
    assert "Native text must survive" in result.text
    assert result.blocks[-1].page_number == 2
    assert result.blocks[0].location["source"] == "pdf_text"


def test_native_header_does_not_hide_scan_on_same_page():
    scanned = Mock()
    scanned.page.return_value = [TextBlock(text="Daily Report", page_number=1)]
    result = PDFTextExtractor(scanned).extract(fixture("hybrid.pdf"))
    assert "Native header" in result.text and "Daily Report" in result.text
    scanned.page.assert_called_once()


def test_docx_preserves_order_clauses_and_source_metadata():
    result = DOCXExtractor().extract(fixture("contract.docx"))
    texts = [b.text for b in result.blocks]
    assert texts.index("Grade\tC30") < texts.index("2 Payment")
    parts = logical_chunks(result, "contract")
    assert len(parts) == 2
    assert len(parts[0].text) > 500  # a whole clause is not sliced into fixed windows
    assert "Grade\tC30" in parts[0].text
    assert parts[0].author == "Fixture Author"
    assert parts[0].date == date(2026, 1, 15)
    assert parts[0].revision == "3"
    assert parts[0].page_number is None  # no fabricated DOCX pagination
    assert any(span["location"].get("row") == 2 for span in parts[0].locations)


def test_xlsx_chunks_boq_rows_preserves_cells_and_uncached_formula():
    result = XLSXExtractor().extract(fixture("boq.xlsx"))
    parts = logical_chunks(result, "boq")
    items = [p for p in parts if p.kind == "boq_item"]
    assert len(items) == 2
    assert "Includes placing and curing" in items[0].text
    assert "=C2*E2" in items[0].text
    assert items[0].locations[0]["location"]["cells"] == ["A2", "B2", "C2", "D2", "E2", "F2"]
    assert items[0].locations[0]["location"]["sheet"] == "BOQ"
    assert items[0].author == "Fixture QS"
    assert items[0].date == date(2026, 1, 16)
    assert items[0].revision == "2"
    assert all(p.page_number is None for p in items)


def test_image_ocr_tsv_returns_pixel_locations(monkeypatch, tmp_path):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    run = Mock(return_value=SimpleNamespace(stdout=fixture("report.tsv")))
    monkeypatch.setattr("app.document_processing.extraction.ocr.subprocess.run", run)
    result = ImageExtractor(TesseractOCR()).extract(fixture("report.png"))
    assert result.blocks[0].text == "Daily Report"
    assert result.blocks[0].location["bbox"] == [40, 50, 270, 98]
    assert result.blocks[0].location["confidence"] == 97
    assert result.blocks[0].page_number == 1
    assert run.call_args.args[0][-1] == "tsv"
    assert [p.kind for p in logical_chunks(result, "daily_report")] == ["daily_report_section"] * 3


def test_email_thread_messages_have_distinct_metadata():
    result = EmailExtractor().extract(fixture("thread.eml"))
    parts = logical_chunks(result, "correspondence")
    assert len(parts) == 2
    assert parts[0].kind == "email_thread_message"
    assert parts[0].author == "Site Engineer <site@example.test>"
    assert parts[0].date == date(2026, 1, 15)
    assert parts[0].language == "en"
    assert parts[1].author is None and parts[1].date is None
    assert parts[1].locations[0]["location"]["quoted"] is True


def test_email_html_alternative_and_attached_message_not_duplicated():
    outer = EmailMessage()
    outer["From"], outer["Subject"] = "outer@example.test", "Outer"
    outer.set_content("Plain text preferred")
    outer.add_alternative("<p>Duplicate HTML</p>", subtype="html")
    inner = EmailMessage()
    inner["From"], inner["Subject"] = "inner@example.test", "Inner"
    inner.set_content("Forwarded text")
    outer.add_attachment(inner)
    result = EmailExtractor().extract(outer.as_bytes())
    assert len(result.blocks) == 2
    assert "Duplicate HTML" not in result.text
    assert result.blocks[1].author == "inner@example.test"
    html = EmailMessage()
    html.set_content(
        "<style>hidden</style><p>Visible &amp; safe</p><script>secret</script>", subtype="html"
    )
    result = EmailExtractor().extract(html.as_bytes())
    assert "Visible & safe" in result.text and "secret" not in result.text


@pytest.mark.parametrize(
    "kind,text,expected",
    [
        (
            "rfi",
            "Question:\nConfirm footing level.\nResponse:\nUse revised drawing.",
            "rfi_section",
        ),
        ("daily_report", "Weather:\nClear.\nActivities:\nConcrete works.", "daily_report_section"),
        ("boq", "1.01 Concrete 10 m3\nIncludes curing.\n1.02 Rebar 2 t", "boq_item"),
    ],
)
def test_logical_business_sections(kind, text, expected):
    parts = logical_chunks(ExtractionResult(blocks=[TextBlock(text=text)]), kind)
    assert len(parts) == 2
    assert all(p.kind == expected for p in parts)


def test_clause_can_span_pages_and_retain_all_source_locations():
    result = ExtractionResult(
        blocks=[
            TextBlock(text="1 Scope\nFirst page text.", page_number=1),
            TextBlock(text="Continuation of the same clause.", page_number=2),
            TextBlock(text="2 Payment\nPay on completion.", page_number=2),
        ]
    )
    parts = logical_chunks(result, "contract")
    assert len(parts) == 2
    assert {s["page_number"] for s in parts[0].locations} == {1, 2}
    assert parts[0].page_number == 1


def test_oversized_clause_sentence_fallback_keeps_section_offsets_and_hashes():
    result = ExtractionResult(
        blocks=[TextBlock(text="1 Scope\n" + "Supply concrete. " * 100, page_number=1)]
    )
    parts = logical_chunks(result, "contract", max_chars=120)
    assert len(parts) > 1
    assert all(p.section == "1 Scope" and len(p.text) <= 120 for p in parts)
    assert all(p.chunk_hash == hashlib.sha256(p.text.encode()).hexdigest() for p in parts)
    assert [p.chunk_hash for p in parts] == [
        p.chunk_hash for p in logical_chunks(result, "contract", max_chars=120)
    ]
    assert all(0 <= s["start"] < s["end"] <= len(p.text) for p in parts for s in p.locations)
    with pytest.raises(ValueError):
        logical_chunks(result, "contract", max_chars=120, limit=1)


def test_legacy_pipeline_checkpoint_remains_readable():
    result = extraction_result("1 Scope\nLegacy text checkpoint")
    assert result.blocks[0].location == {"source": "legacy_text"}
    assert logical_chunks(result, "contract")[0].section == "1 Scope"


def test_archive_members_keep_separate_provenance():
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("first.eml", fixture("thread.eml"))
        archive.writestr("second.eml", fixture("thread.eml"))
    result = DocumentExtractionService(Mock()).extract(stream.getvalue(), "zip")
    assert {b.location["archive_member"] for b in result.blocks} == {"first.eml", "second.eml"}


def test_metadata_and_archive_boundaries_never_merge_unrelated_text():
    result = ExtractionResult(
        blocks=[
            TextBlock(text="1 Scope\nFirst file", location={"archive_member": "a.pdf"}, author="A"),
            TextBlock(text="Second file", location={"archive_member": "b.pdf"}, author="B"),
        ]
    )
    parts = logical_chunks(result, "contract")
    assert len(parts) == 2
    assert parts[1].section == "document" and parts[1].author == "B"


def test_native_extraction_adapter_needs_no_llm_provider():
    from app.document_processing.providers import Services

    result = Services().extraction(fixture("contract.pdf"), "pdf")
    assert result.blocks[0].author == "Fixture Engineer"
    assert "Supply concrete" in result.text


@pytest.mark.parametrize(
    "kind,text",
    [
        ("rfi", "Question\nConfirm footing level.\nResponse\nUse revised drawing."),
        ("daily_report", "Weather\nClear.\nActivities\nConcrete works."),
    ],
)
def test_unpunctuated_business_headings(kind, text):
    parts = logical_chunks(ExtractionResult(blocks=[TextBlock(text=text)]), kind)
    assert len(parts) == 2


async def test_real_fixture_pipeline_persists_chunk_fields(pipeline, test_session):  # noqa: F811
    document = pipeline.document
    content = fixture("contract.docx")
    document.filename, document.file_type = "contract.docx", "docx"
    document.checksum = hashlib.sha256(content).hexdigest()
    document.access_level = "restricted"
    pipeline.storage.download_file.return_value = content
    pipeline.services.extraction.side_effect = DocumentExtractionService(Mock()).extract
    await test_session.commit()
    for _ in STAGES:
        await pipeline.step()
    rows = list(
        await test_session.scalars(select(DocumentChunk).order_by(DocumentChunk.chunk_index))
    )
    assert len(rows) == 2
    for row in rows:
        assert row.document_id == document.id and row.project_id == document.project_id
        assert row.tenant_id == document.tenant_id
        assert row.section in {"1 Scope", "2 Payment"}
        assert row.revision == "3" and row.date == date(2026, 1, 15)
        assert row.author == "Fixture Author" and row.access_level == "restricted"
        assert row.language == "en-US" and row.page_number is None
        assert row.chunk_hash == hashlib.sha256(row.text.encode()).hexdigest()
        assert row.embedding_model == "text-embedding-3-small" and row.embedding is not None
        assert row.attributes["locations"]
    assert await pipeline.step() is None


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Install Tesseract to run native OCR")
def test_native_tesseract_small_image():
    result = ImageExtractor(TesseractOCR()).extract(fixture("report.png"))
    assert "Daily Report" in result.text
    assert all(b.location["unit"] == "pixel" for b in result.blocks)


@pytest.mark.skipif(
    not shutil.which("tesseract") or not shutil.which("pdftoppm"),
    reason="Install Tesseract and Poppler",
)
def test_native_scanned_pdf_ocr():
    result = ScannedPDFExtractor(TesseractOCR()).extract(fixture("scanned.pdf"))
    assert "Daily Report" in result.text
    assert all(b.page_number == 1 for b in result.blocks)
