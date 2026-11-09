"""Pilot import boundaries and deterministic readiness metrics."""

from io import BytesIO
from pathlib import PurePosixPath
from stat import S_ISLNK
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.domain.services.document_files import MAX_SIZE, TYPES

REQUIRED = ("contract", "boq", "drawing")
CHECKLIST = {
    "scope": "Agree pilot scope, project team and success criteria.",
    "evidence": "Collect the signed contract, BOQ and current drawings.",
    "upload": "Upload a ZIP and resolve failed or quarantined files.",
    "review": "Review document types and extracted facts against originals.",
    "risks": "Review risks, missing evidence, exposure and overdue approvals.",
    "signoff": "Export the readiness report and agree next steps with your team.",
}


def inspect_archive(content):
    if len(content) > MAX_SIZE:
        raise HTTPException(413, "ZIP exceeds 50 MiB")
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            files = [e for e in entries if not e.is_dir()]
            if not files or len(entries) > 100:
                raise ValueError("ZIP must contain 1-100 entries")
            total = 0
            names = set()
            result = []
            for entry in files:
                path = PurePosixPath(entry.filename)
                extension = path.suffix.lower().lstrip(".")
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in entry.orig_filename
                    or ":" in entry.filename
                    or S_ISLNK(entry.external_attr >> 16)
                    or entry.flag_bits & 1
                    or extension not in TYPES
                    or extension == "zip"
                    or entry.filename in names
                ):
                    raise ValueError("Unsafe, encrypted, duplicate or unsupported ZIP member")
                names.add(entry.filename)
                total += entry.file_size
                if entry.file_size > MAX_SIZE or total > 200 * 1024 * 1024:
                    raise ValueError("ZIP expanded size exceeds limits")
                if entry.file_size > max(entry.compress_size, 1) * 200:
                    raise ValueError("ZIP compression ratio exceeds limit")
                with archive.open(entry) as member:
                    data = member.read(MAX_SIZE + 1)
                if len(data) > MAX_SIZE:
                    raise ValueError("ZIP member exceeds limit")
                result.append((entry.filename, data))
            return result
    except (BadZipFile, ValueError, RuntimeError, NotImplementedError, EOFError, OSError):
        raise HTTPException(422, "Invalid or unsafe ZIP archive") from None


def summarize(documents):
    reviewed = [
        d
        for d in documents
        if d.get("attributes", {}).get("pilot_review", {}).get("document_type")
        and d.get("classification_result")
    ]
    correct = sum(
        (d.get("classification_result") or {}).get("document_type")
        == d["attributes"]["pilot_review"]["document_type"]
        for d in reviewed
    )
    confidences = [
        float(d["extraction_confidence"])
        for d in documents
        if d.get("extraction_confidence") is not None
    ]
    types = {
        d.get("document_type") for d in documents if d["status"] not in {"failed", "quarantined"}
    }
    return dict(
        documents_total=len(documents),
        documents_processed=sum(d["status"] == "linked" for d in documents),
        classification_reviewed=len(reviewed),
        classification_accuracy=correct / len(reviewed) if reviewed else None,
        extraction_confidence=sum(confidences) / len(confidences) if confidences else None,
        missing_evidence=[t for t in REQUIRED if t not in types],
    )


def render_report(report):
    stream = BytesIO()
    styles = getSampleStyleSheet()
    story = [Paragraph("Pilot readiness report", styles["Title"])]
    for key, value in report.items():
        if key == "project_id":
            continue
        if key in {"classification_accuracy", "extraction_confidence"} and value is not None:
            value = f"{value * 100:.1f}%"
        elif key == "pending_exposure":
            value = (
                ", ".join(f"{currency} {amount}" for currency, amount in value.items())
                or "No known amounts"
            )
        elif key == "missing_evidence":
            value = ", ".join(value) or "None"
        story.extend(
            [
                Paragraph(
                    escape(
                        f"{key.replace('_', ' ').capitalize()}: {value if value is not None else 'Unknown'}"
                    ),
                    styles["BodyText"],
                ),
                Spacer(1, 8),
            ]
        )
    SimpleDocTemplate(stream).build(story)
    return stream.getvalue()
