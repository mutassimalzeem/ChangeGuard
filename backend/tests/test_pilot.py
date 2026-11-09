from io import BytesIO
from zipfile import ZipFile, ZipInfo

import pytest
from fastapi import HTTPException

from app.domain.services.pilot import inspect_archive, render_report, summarize


def archive(entries):
    out = BytesIO()
    with ZipFile(out, "w") as z:
        for name, data in entries:
            info = ZipInfo("placeholder")
            info.filename = name
            z.writestr(info, data)
    return out.getvalue()


@pytest.mark.parametrize(
    "name", ["../bad.pdf", "/bad.pdf", "C:/bad.pdf", "a\\bad.pdf", "nested.zip"]
)
def test_unsafe_archive(name):
    with pytest.raises(HTTPException):
        inspect_archive(archive([(name, b"x")]))


def test_archive_members():
    assert inspect_archive(archive([("folder/a.pdf", b"data")])) == [("folder/a.pdf", b"data")]


def test_empty_and_invalid_archive():
    for value in [b"bad", archive([])]:
        with pytest.raises(HTTPException):
            inspect_archive(value)


def test_report_unknown_and_reviewed_accuracy():
    docs = [
        dict(
            status="linked",
            document_type="contract",
            extraction_confidence=0.6,
            classification_result={"document_type": "rfi"},
            attributes={"pilot_review": {"document_type": "contract"}},
        )
    ]
    result = summarize(docs)
    assert result["documents_processed"] == 1
    assert result["classification_accuracy"] == 0
    assert result["classification_reviewed"] == 1
    assert result["extraction_confidence"] == 0.6
    assert summarize([])["classification_accuracy"] is None
    assert "boq" in result["missing_evidence"]


def test_pdf_contains_report():
    from pypdf import PdfReader

    report = summarize([])
    report.update(
        project_name="<Pilot & Co>",
        generated_at="2026-11-09",
        risks_detected=0,
        overdue_approvals=0,
        pending_exposure={},
        unknown_exposure_count=0,
    )
    content = render_report(report)
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(content)).pages)
    assert "<Pilot & Co>" in text
    assert "Classification accuracy" in text


def test_archive_entry_and_expansion_limits(monkeypatch):
    from zipfile import ZIP_DEFLATED

    from app.domain.services import pilot

    with pytest.raises(HTTPException):
        inspect_archive(archive([(f"{i}.pdf", b"x") for i in range(101)]))
    out = BytesIO()
    with ZipFile(out, "w", compression=ZIP_DEFLATED) as z:
        z.writestr("bomb.pdf", b"x" * 1000000)
    with pytest.raises(HTTPException):
        inspect_archive(out.getvalue())
    monkeypatch.setattr(pilot, "MAX_SIZE", 10)
    with pytest.raises(HTTPException) as exc:
        inspect_archive(b"x" * 11)
    assert exc.value.status_code == 413


def test_archive_symlink_rejected():
    out = BytesIO()
    info = ZipInfo("link.pdf")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with ZipFile(out, "w") as z:
        z.writestr(info, b"target")
    with pytest.raises(HTTPException):
        inspect_archive(out.getvalue())
