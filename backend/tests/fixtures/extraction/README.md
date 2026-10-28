# Synthetic extraction fixtures

All files contain synthetic construction examples and reserved `example.test`
email addresses. They contain no customer data.

- `contract.pdf`: two native-text pages with separate clauses.
- `scanned.pdf`: one raster-only page containing a short daily report.
- `mixed.pdf`: native-text first page and raster-only second page.
- `hybrid.pdf`: scanned content with a native-text header on the same page.
- `report.png` / `report.tsv`: small OCR image and deterministic TSV output for portable tests.
- `contract.docx`: two clauses, a table between paragraphs, and explicit source properties.
- `boq.xlsx`: two item rows, a multiline description, and an uncached formula.
- `thread.eml`: an RFI email with one conventional quoted reply.

Run `python tests/fixtures/extraction/generate.py` from the backend environment
to recreate the binary fixtures. ZIP container timestamps may differ; tests
assert extracted facts and locations rather than binary byte identity.
`check_native_ocr.py` exercises actual Tesseract/Poppler outside pytest when
running in a minimal Linux test container.
