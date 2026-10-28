"""Select an ExtractionService without coupling format logic to Celery or AI."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from app.document_processing.extraction.email import EmailExtractor, OutlookExtractor
from app.document_processing.extraction.formats import (
    DOCXExtractor,
    PDFTextExtractor,
    XLSXExtractor,
)
from app.document_processing.extraction.ocr import ImageExtractor, ScannedPDFExtractor
from app.document_processing.extraction.types import ExtractionResult, ExtractionService, ImageOCR
from app.domain.services.document_files import MAX_SIZE, validate_document


class DocumentExtractionService:
    def __init__(self, ocr: ImageOCR, *, dpi: int = 300):
        self.scanned = ScannedPDFExtractor(ocr, dpi=dpi)
        self.extractors: dict[str, ExtractionService] = {
            "pdf": PDFTextExtractor(self.scanned),
            "docx": DOCXExtractor(),
            "xlsx": XLSXExtractor(),
            "png": ImageExtractor(ocr),
            "jpg": ImageExtractor(ocr),
            "jpeg": ImageExtractor(ocr),
            "eml": EmailExtractor(),
            "msg": OutlookExtractor(),
        }

    def extract(self, content: bytes, extension: str) -> ExtractionResult:
        if not content or len(content) > MAX_SIZE:
            raise ValueError("Empty or oversized extraction input")
        extension = extension.lower().lstrip(".")
        if extension == "zip":
            return self.archive(content)
        if extension not in self.extractors:
            raise ValueError("Unsupported extraction format")
        result = self.extractors[extension].extract(content)
        if not result.text.strip() or len(result.text) > 2_000_000:
            raise ValueError("Empty or oversized extracted text")
        return result

    def archive(self, content):
        validate_document("archive.zip", content)
        blocks, total = [], 0
        with ZipFile(BytesIO(content)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) > 100:
                raise ValueError("Archive processing file limit exceeded")
            for member in members:
                extension = Path(member.filename).suffix.lower().lstrip(".")
                if extension not in self.extractors:
                    raise ValueError("Unsupported or nested archive member")
                payload = archive.read(member)
                validate_document(member.filename, payload)
                result = self.extract(payload, extension)
                total += len(result.text)
                if total > 2_000_000:
                    raise ValueError("Archive text limit exceeded")
                for block in result.blocks:
                    block.location = {**block.location, "archive_member": member.filename}
                    blocks.append(block)
        return ExtractionResult(blocks=blocks)
