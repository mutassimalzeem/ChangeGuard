"""Native-format extractors preserve physical and structural source references."""

import re
from collections import OrderedDict
from datetime import datetime
from io import BytesIO

from app.document_processing.extraction.types import ExtractionResult, TextBlock


class PDFTextExtractor:
    def __init__(self, scanned=None, *, max_pages=100):
        self.scanned, self.max_pages = scanned, max_pages

    def extract(self, content: bytes) -> ExtractionResult:
        import pdfplumber

        blocks = []
        with pdfplumber.open(BytesIO(content)) as pdf:
            if pdf.doc.is_extractable is False or not 0 < len(pdf.pages) <= self.max_pages:
                raise ValueError("Unreadable, empty or oversized PDF")
            created = None
            raw_date = pdf.metadata.get("CreationDate", "")
            try:
                created = datetime.strptime(str(raw_date).removeprefix("D:")[:8], "%Y%m%d").date()
            except ValueError:
                pass  # missing or partial PDF dates remain unknown
            author = pdf.metadata.get("Author")
            for number, page in enumerate(pdf.pages, 1):
                words = page.extract_words()
                page_blocks = []
                lines = OrderedDict()
                for word in words:
                    key = round(word["top"] / 3) * 3
                    lines.setdefault(key, []).append(word)
                for words in lines.values():
                    page_blocks.append(
                        TextBlock(
                            text=" ".join(w["text"] for w in words),
                            page_number=number,
                            author=str(author) if author else None,
                            date=created,
                            location={
                                "source": "pdf_text",
                                "unit": "point",
                                "origin": "top-left",
                                "bbox": [
                                    min(w["x0"] for w in words),
                                    min(w["top"] for w in words),
                                    max(w["x1"] for w in words),
                                    max(w["bottom"] for w in words),
                                ],
                                "page_width": page.width,
                                "page_height": page.height,
                            },
                        )
                    )
                large_image = any(
                    image["width"] * image["height"] >= page.width * page.height * 0.5
                    for image in page.images
                )
                if self.scanned is not None and page.images and (not words or large_image):
                    # A scan with a native header still needs OCR. Keep native lines
                    # and supplement them with OCR, removing exact duplicate lines.
                    native = {re.sub(r"\W+", "", b.text).casefold() for b in page_blocks}
                    for block in self.scanned.page(content, number):
                        if re.sub(r"\W+", "", block.text).casefold() not in native:
                            page_blocks.append(
                                block.model_copy(
                                    update={
                                        "author": block.author or (str(author) if author else None),
                                        "date": block.date or created,
                                    }
                                )
                            )

                def reading_order(block):
                    location = block.location
                    if not location.get("bbox"):
                        return float("inf")
                    height = (
                        location.get("image_height")
                        if location.get("unit") == "pixel"
                        else page.height
                    )
                    return location["bbox"][1] / height if height else float("inf")

                blocks.extend(sorted(page_blocks, key=reading_order))
        return ExtractionResult(blocks=blocks)


class DOCXExtractor:
    def extract(self, content: bytes) -> ExtractionResult:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = Document(BytesIO(content))
        default_lang = document.styles.element.xpath(".//w:docDefaults//w:lang/@w:val")
        default_lang = default_lang[0] if default_lang else "und"
        properties = document.core_properties
        common = {
            "author": properties.author or None,
            "date": properties.created.date() if properties.created else None,
            "revision": str(properties.revision) if properties.revision else None,
        }
        blocks, section = [], None
        # XML document order is essential: tables often sit between clause paragraphs.
        for index, child in enumerate(document.element.body):
            if child.tag == qn("w:p"):
                paragraph = Paragraph(child, document)
                if not paragraph.text.strip():
                    continue
                heading = paragraph.style is not None and paragraph.style.name.startswith("Heading")
                if heading:
                    section = paragraph.text.strip()
                lang = child.xpath(".//w:lang/@w:val")
                blocks.append(
                    TextBlock(
                        text=paragraph.text,
                        kind="heading" if heading else "paragraph",
                        section=section,
                        language=lang[0] if lang else default_lang,
                        **common,
                        # DOCX does not contain reliable rendered pagination.
                        location={
                            "source": "docx",
                            "body_index": index,
                            "style": paragraph.style.name if paragraph.style else None,
                            "explicit_page_breaks": len(child.xpath('.//w:br[@w:type="page"]')),
                        },
                    )
                )
            elif child.tag == qn("w:tbl"):
                table = Table(child, document)
                headers = [cell.text for cell in table.rows[0].cells] if table.rows else []
                for number, row in enumerate(table.rows):
                    cells = [cell.text for cell in row.cells]
                    if not any(cell.strip() for cell in cells):
                        continue
                    blocks.append(
                        TextBlock(
                            text="\t".join(cells),
                            kind="table_row",
                            section=section,
                            language=default_lang,
                            **common,
                            location={
                                "source": "docx",
                                "body_index": index,
                                "row": number + 1,
                                "cells": cells,
                                "headers": headers,
                                "is_header": number == 0,
                            },
                        )
                    )
        return ExtractionResult(blocks=blocks)


class XLSXExtractor:
    def extract(self, content: bytes) -> ExtractionResult:
        from openpyxl import load_workbook

        # Formula strings are preserved when there is no cached calculated value.
        values = load_workbook(BytesIO(content), read_only=True, data_only=True)
        formulas = load_workbook(BytesIO(content), read_only=True, data_only=False)
        blocks = []
        try:
            for sheet, formula_sheet in zip(values, formulas, strict=True):
                if sheet.max_row and sheet.max_row > 100_000:
                    raise ValueError("Spreadsheet row limit exceeded")
                if sheet.max_column and sheet.max_column > 256:
                    raise ValueError("Spreadsheet column limit exceeded")
                headers = None
                for row, formula_row in zip(
                    sheet.iter_rows(), formula_sheet.iter_rows(), strict=True
                ):
                    cells = [
                        str(c.value if c.value is not None else f.value)
                        if c.value is not None or f.value is not None
                        else ""
                        for c, f in zip(row, formula_row, strict=True)
                    ]
                    if not any(cell.strip() for cell in cells):
                        continue
                    is_header = headers is None
                    headers = cells if is_header else headers
                    coordinates = [
                        cell.coordinate for cell in formula_row if cell.value is not None
                    ]
                    blocks.append(
                        TextBlock(
                            text="\t".join(cells),
                            kind="table_row",
                            section=sheet.title,
                            author=values.properties.creator or None,
                            date=values.properties.created.date()
                            if values.properties.created
                            else None,
                            revision=values.properties.revision,
                            location={
                                "source": "xlsx",
                                "sheet": sheet.title,
                                "row": next(c.row for c in formula_row if c.value is not None),
                                "cells": coordinates,
                                "headers": headers,
                                "is_header": is_header,
                            },
                        )
                    )
        finally:
            values.close()
            formulas.close()
        return ExtractionResult(blocks=blocks)
