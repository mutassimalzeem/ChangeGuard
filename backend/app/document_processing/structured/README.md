# Schema-constrained structured extraction (Feature 3.4)

`StructuredExtractionService.extract(ExtractionResult, document_type)` is the
interface. `SchemaConstrainedExtractor` selects a Pydantic schema, requests strict
JSON, validates all facts against source evidence, and performs bounded repair.
`Services.extract` connects it to the existing configured OpenAI model.

Schemas cover Contract, BOQItem (inside a BOQ document), Drawing, RFI, ChangeOrder,
DailyReport, Email and Quotation. A conservative Other schema handles other text
documents. Site photos pause for visual review instead of entering unsupported
structured extraction. Historical `invoice`/`correspondence` classifier labels
use Other/Email extraction schemas without changing their stored labels.

## Field contract

Every leaf fact is wrapped, including monetary and quantity values:

```json
{
  "value": {"amount": "1250.50", "currency": "BDT"},
  "confidence": 0.96,
  "source_page": 1,
  "source_text_snippet": "Contract value: BDT 1,250.50",
  "missing": false
}
```

Unknown facts use exactly `value=null`, `confidence=0`, `source_page=null`,
`source_text_snippet=null`, `missing=true`. All JSON keys are required, even for
unknown facts; omission is a schema error and requests repair. Structural lists
contain objects whose leaf facts carry their own evidence. Empty lists do not
invent items or references. Business-critical missing facts (declared by each
schema's `required_facts`) are listed explicitly in `missing_required_fields` and
force overall extraction confidence to zero for human review.

Strict mode forbids extra keys and scalar coercion. Values include:

- Calendar-valid ISO 8601 dates (`YYYY-MM-DD`). Only ISO or unambiguous English named-month source dates are normalized; ambiguous numeric dates are not guessed.
- Money as exact `Decimal` values serialized to decimal strings plus an allowed uppercase currency code. No binary floats, exponent notation, NaN or Infinity.
- Quantities as exact decimal strings plus an allowed construction unit. Units are copied/normalized, never converted or multiplied.
- Document-specific status enums; source statements do not approve or change domain records.
- Bounded reference codes for drawing numbers, BOQ item codes, RFI/CO numbers and related documents.

Supported currencies/units are enumerated in `schemas.py`. Decimal strings allow
up to 15 integer digits and six fractional digits; unsupported currencies, units
or number formats require explicit missing values rather than guesses. Email
addresses receive syntax validation without DNS/deliverability checks, including
reserved test domains.

## Evidence and totals

Each present quotation must match actual source text or recorded source metadata
after whitespace/case normalization. Physical page claims must match a source
page; null is accepted only where pagination is unknown. Contiguous blocks on
the same page may form one quotation. Different archive members and MIME thread
messages remain separate source units. Text remains preserved in the earlier
extraction checkpoint and, after successful processing, document chunks.

Values must appear in the quoted evidence. Amounts and currencies, and quantities
and units, must occur as pairs rather than unrelated numbers elsewhere on a page.
Reference kinds require corresponding source labels/codes. Simple negated status
statements cannot become positive approvals. These are conservative lexical
checks, not proof of semantic correctness or business authority.

The prompt explicitly forbids totals, sums, multiplication, currency conversion
and estimates. `stated_total` is accepted only when a matching amount/currency is
on a source line labelled Total and the line is not an arithmetic expression.
An absent or formula-only total stays missing. The application does not calculate
financial totals in this feature. Existing deterministic risk checks receive
validated Decimal-compatible values; reference linking uses only grounded related
references supported by the existing domain link models.

## Repair and persistence

Requests use `response_format.type=json_schema`, `strict=true`, closed objects
(`additionalProperties=false`) and all properties required, recursively. Application
validation remains mandatory after generation. Duplicate JSON keys, fenced or
malformed JSON, non-finite constants, invalid types/enums and unsupported evidence
trigger a repair request containing the original source, prior response and safe
validation error codes/paths. Repairs regenerate a complete object and may mark
unsupported values missing; they cannot invent facts to satisfy a schema.

`STRUCTURED_EXTRACTION_REPAIR_RETRIES` defaults to one (two total calls), bounded
to zero through two. Truncated output can be repaired; refusals/content filtering
are not retried as repair prompts. Transport/rate-limit errors retain the existing
Celery backoff/dead-letter policy. Each model request is limited to 60 seconds
and the configured output-token limit.

Migration 0008 adds nullable `documents.structured_extraction`. The pipeline
revalidates evidence before persisting validated fields, missing-field paths,
derived confidence, model provenance and attempt history. Confidence summaries
come from validated fields, not model assertions. Review decisions use unrounded
confidence, so the database's four-decimal public summary cannot round a low
value above the review threshold. Completed stages remain idempotent.

Exhausted repair attempts are retained in the durable processing state alongside
earlier checkpoints and the original file; the job enters the existing dead-letter
queue. Raw attempts and quoted facts stay out of logs and public registry responses.
The registry continues to expose confidence; no public raw-extraction endpoint is
introduced. Legacy unversioned generic checkpoints can still resume but are not
misrepresented as typed/provenanced results.

Apply `alembic upgrade head` before updated API/workers. Existing documents and
their historical results are not automatically re-extracted. Requests reject
empty sources, sources exceeding 120,000 characters, and JSON responses exceeding
one million characters; they do not silently truncate the source. Narrative fields
need supporting quotations (at most 2,000 characters). Very large documents/BOQs
may require later per-section orchestration or larger supported model output limits.

## Validation

```sh
DEBUG=false TEST_DATABASE_ADMIN_URL=postgresql+asyncpg://USER:PASS@HOST:PORT/postgres pytest tests/test_structured_extraction.py
```

Synthetic cases exercise all schemas, decimals, ISO dates, statuses, references,
missing facts, malformed/duplicate/non-finite JSON, omitted/extra fields, false
quotes/pages/values, invented totals, truncated responses, refusal boundaries,
repair exhaustion, typed persistence, Decimal risk checks and confidence rounding.
All model responses are mocked; live model accuracy is not asserted.

Reference: [OpenAI strict structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
