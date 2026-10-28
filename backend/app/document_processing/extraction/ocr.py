"""Local OCR returns TSV word locations; text-only providers remain injectable."""

import csv
import subprocess
from collections import OrderedDict
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from app.document_processing.extraction.types import ExtractionResult, ImageOCR, TextBlock


class TesseractOCR:
    def __init__(self, languages: list[str] | None = None):
        self.languages = languages or ["eng"]

    def recognize(self, content: bytes, *, page_number: int = 1) -> list[TextBlock]:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(content)) as image:
            width, height = image.size
        with TemporaryDirectory(prefix="changeguard-ocr-") as folder:
            source = Path(folder) / "image.png"
            source.write_bytes(content)
            result = subprocess.run(
                ["tesseract", str(source), "stdout", "-l", "+".join(self.languages), "tsv"],
                check=True,
                capture_output=True,
                timeout=90,
            )
        blocks = self.parse_tsv(result.stdout.decode("utf-8"), page_number)
        for block in blocks:
            block.location.update(
                {
                    "image_width": width,
                    "image_height": height,
                    "recognition_languages": self.languages,
                }
            )
        return blocks

    def parse_tsv(self, output: str, page_number: int) -> list[TextBlock]:
        groups = OrderedDict()
        for row in csv.DictReader(StringIO(output), delimiter="\t", quoting=csv.QUOTE_NONE):
            if row["level"] != "5" or not row.get("text", "").strip():
                continue
            key = (row["block_num"], row["par_num"], row["line_num"])
            groups.setdefault(key, []).append(row)
        blocks = []
        for key, words in groups.items():
            x0 = min(int(w["left"]) for w in words)
            y0 = min(int(w["top"]) for w in words)
            x1 = max(int(w["left"]) + int(w["width"]) for w in words)
            y1 = max(int(w["top"]) + int(w["height"]) for w in words)
            blocks.append(
                TextBlock(
                    text=" ".join(w["text"] for w in words),
                    page_number=page_number,
                    location={
                        "source": "ocr",
                        "unit": "pixel",
                        "bbox": [x0, y0, x1, y1],
                        "origin": "top-left",
                        "line": list(key),
                        "confidence": min(float(w["conf"]) for w in words),
                    },
                    # Recognition language is recorded separately; it is not language detection.
                )
            )
        return blocks


class TextOnlyOCR:
    """Compatibility adapter for vision services without trustworthy coordinates."""

    def __init__(self, recognize):
        self.recognize_text = recognize

    def recognize(self, content: bytes, *, page_number: int = 1) -> list[TextBlock]:
        text = self.recognize_text(content, "png")
        return (
            [
                TextBlock(
                    text=text,
                    page_number=page_number,
                    location={"source": "ocr", "coordinates_available": False},
                )
            ]
            if text.strip()
            else []
        )


class ImageExtractor:
    def __init__(self, ocr: ImageOCR):
        self.ocr = ocr

    def extract(self, content: bytes) -> ExtractionResult:
        # Normalize image formats before handing bytes to either OCR implementation.
        from io import BytesIO

        from PIL import Image, ImageOps

        with Image.open(BytesIO(content)) as image:
            output = BytesIO()
            ImageOps.exif_transpose(image).convert("RGB").save(output, format="PNG")
        return ExtractionResult(blocks=self.ocr.recognize(output.getvalue()))


class ScannedPDFExtractor:
    def __init__(self, ocr: ImageOCR, *, dpi: int = 300, max_pages: int = 100):
        self.ocr, self.dpi, self.max_pages = ocr, dpi, max_pages

    def page(self, content: bytes, page_number: int) -> list[TextBlock]:
        with TemporaryDirectory(prefix="changeguard-pdf-") as folder:
            source, target = Path(folder) / "source.pdf", Path(folder) / "page"
            source.write_bytes(content)
            subprocess.run(
                [
                    "pdftoppm",
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-singlefile",
                    "-r",
                    str(self.dpi),
                    "-scale-to",
                    "3000",
                    "-png",
                    str(source),
                    str(target),
                ],
                check=True,
                capture_output=True,
                timeout=90,
            )
            return self.ocr.recognize(
                target.with_suffix(".png").read_bytes(), page_number=page_number
            )

    def extract(self, content: bytes) -> ExtractionResult:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or not 0 < len(reader.pages) <= self.max_pages:
            raise ValueError("Encrypted, empty or oversized scanned PDF")
        return ExtractionResult(
            blocks=[
                block
                for number in range(1, len(reader.pages) + 1)
                for block in self.page(content, number)
            ]
        )
