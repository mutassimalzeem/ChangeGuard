# Text extraction and OCR (Feature 3.2)

`ExtractionService.extract(bytes) -> ExtractionResult` is the common format
interface. An extraction result contains ordered `TextBlock` records, rather
than a single flattened string. The Celery text stage checkpoints the complete
result. Classification and field extraction receive its text view; the chunk
stage retains source references when writing `document_chunks`.

## Implementations

| Implementation | Locations and metadata |
| --- | --- |
| `PDFTextExtractor` | One-based physical pages; line bounding boxes in points, top-left origin; PDF author and full creation date if declared |
| `ScannedPDFExtractor` | Poppler renders selected pages, bounded to 100; OCR retains original physical page numbers |
| `ImageExtractor` | Normalizes images and EXIF orientation before OCR; single images use page 1 |
| `TesseractOCR` | TSV line boxes in pixels, raster dimensions, minimum word confidence, configured recognition languages |
| `DOCXExtractor` | Paragraph/table order, body indices, table rows, heading styles, explicit page-break counts, author, creation date, revision and declared language |
| `XLSXExtractor` | Sheet, row, populated cell addresses, headers, author, creation date and revision; uncached formulas retained as formulas |
| `EmailExtractor` | MIME paths, message IDs, subject, sender, date and declared language; prefers plain text over duplicate HTML alternatives |

PDF pages with raster images and no text use OCR. Pages containing large raster
images (at least half the page) also use OCR even if a native header is present.
Native lines are retained and exact matching OCR lines are deduplicated. This is
a heuristic, not complete layout analysis. Multi-column reading order and complex
borderless PDF tables may require format-specific tuning.

EML extraction separates conventional quoted replies and attached RFC822
messages. Quoted messages without reliable headers retain unknown author/date
rather than inheriting the outer sender. HTML is parsed locally without fetching
resources; script/style contents and text attachments are excluded from the body.
MSG plain-text bodies and sender/subject properties are supported; compressed
RTF-only MSG files require another adapter. Validated ZIP members retain their
member paths and are never merged across file boundaries. Nested ZIPs are rejected.

DOCX and XLSX do not provide reliable rendered page numbers: these remain null.
Unknown language is `und`; unknown author/date remain null. Declared language
and OCR recognition-language configuration are not language detection. The
text-only vision OCR fallback explicitly reports that coordinates are unavailable.

## Logical chunks

The primary boundaries are:

- Contract clauses/articles and numbered or styled headings, including continuation across physical pages.
- BOQ item rows, with multiline cell content preserved and header/cell references retained.
- RFI question, background, response and related sections.
- Daily report weather, activities, workforce, safety and other labelled sections.
- Email thread messages, including forwarded RFC822 messages.

Unrecognized documents fall back to available headings and document sections. Metadata
or archive-source changes also create boundaries. There is no fixed 500-character
window or overlapping-window primary strategy. `LOGICAL_CHUNK_MAX_CHARS` defaults
to 8000 and is only a safety ceiling for oversized logical units: those split at
paragraph, sentence or word boundaries, with a hard cut only for an oversized
unbroken token. Continuations retain the section and source offsets. The configured
maximum chunk count fails explicitly rather than truncating the document.

Each stored chunk has explicit `document_id`, `project_id`, `tenant_id`,
`page_number`, `section`, `revision`, `date`, `author`, `access_level`, `language`,
`chunk_hash`, and `embedding_model` columns. `attributes` contains the logical
kind and source spans, with chunk-relative start/end offsets and source-relative
text offsets. Multi-page chunks expose their first page in `page_number` and all
pages in the spans. Coordinates describe the source line/region; splitting a
region does not invent more precise character boxes.

Access comes from the registry, not document contents or model output. Revision
uses the declared source revision when available, otherwise the document version.
Dates are source dates, not processing times. `chunk_hash` is SHA-256 of the exact
stored UTF-8 text. The configured embedding model is recorded at chunk creation
and confirmed when embeddings are generated; a row without a vector is not yet
embedded. Tenant/project composite foreign keys and the pipeline's transactional
checkpoints continue to protect ownership and idempotency.

## Upgrade and run

Drain old workers, then apply `alembic upgrade head` before starting the updated
API/workers. Old workers do not supply the new required chunk hash. Migration 0006 backfills
access and revision from the owning document and computes text hashes for existing
chunks. It preserves IDs, text and vectors. Unknown historical embedding model,
language and location provenance are not invented. Existing completed checkpoints
are not automatically re-extracted; legacy 3.1 string checkpoints can still resume.
The earlier `CHUNK_SIZE`/`CHUNK_OVERLAP` settings no longer govern this pipeline.

For local OCR set `OCR_PROVIDER=tesseract` and configure `OCR_LANGUAGES` as needed.
Install corresponding Tesseract language packs. The runtime Dockerfile already
includes English Tesseract and Poppler. Windows requires binaries on PATH or use
the Linux worker image. OpenAI vision remains an optional text-only fallback;
AWS Textract and Azure adapters are not included. No new Python dependency is
required by this feature.

## Verification

Small synthetic fixtures live in `tests/fixtures/extraction`; `generate.py`
recreates the PDF, image and Office files using backend dependencies. Tests run
real native-format parsers, mock OCR process output for portable location checks,
and persist real fixture chunks through the processing pipeline in disposable
PostgreSQL databases. Optional native tests exercise Tesseract and Poppler when
available. `check_native_ocr.py` also runs standalone in a minimal Linux container.

```sh
DEBUG=false TEST_DATABASE_ADMIN_URL=postgresql+asyncpg://USER:PASS@HOST:PORT/postgres pytest tests/test_text_extraction.py tests/test_extraction_migration.py
```

References: [pdfplumber extraction and coordinates](https://github.com/jsvine/pdfplumber),
[python-docx document order](https://python-docx.readthedocs.io/en/develop/api/document.html),
[Tesseract TSV output](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).
