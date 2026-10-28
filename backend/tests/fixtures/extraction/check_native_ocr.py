"""Standalone native OCR checks for a disposable Linux container."""

from pathlib import Path

from app.document_processing.extraction.formats import PDFTextExtractor
from app.document_processing.extraction.ocr import ImageExtractor, ScannedPDFExtractor, TesseractOCR

fixtures = Path(__file__).parent
ocr = TesseractOCR()
image = ImageExtractor(ocr).extract((fixtures / "report.png").read_bytes())
assert "Daily Report" in image.text
assert all(block.location["bbox"][2] > block.location["bbox"][0] for block in image.blocks)
scanned = ScannedPDFExtractor(ocr)
pdf = scanned.extract((fixtures / "scanned.pdf").read_bytes())
assert "Daily Report" in pdf.text
assert all(block.page_number == 1 for block in pdf.blocks)
mixed = PDFTextExtractor(scanned).extract((fixtures / "mixed.pdf").read_bytes())
assert "Native text must survive" in mixed.text and "Daily Report" in mixed.text
assert any(b.page_number == 1 and b.location["source"] == "pdf_text" for b in mixed.blocks)
assert any(b.page_number == 2 and b.location["source"] == "ocr" for b in mixed.blocks)
hybrid = PDFTextExtractor(scanned).extract((fixtures / "hybrid.pdf").read_bytes())
assert "Native header" in hybrid.text and "Daily Report" in hybrid.text
print("Native image OCR, scanned PDF OCR and mixed PDF extraction passed")
