# Document classification (Feature 3.3)

`ClassificationService.classify(ClassificationInput) -> Classification` is the
interface. `RuleFirstClassifier` implements it with an optional injectable LLM
fallback. `Services.classify` integrates it with Celery and also accepts legacy
text-only callers.

Types: `contract`, `boq`, `drawing`, `rfi`, `change_order`, `daily_report`,
`site_photo`, `email`, `quotation`, `other`.

Every result includes `document_type`, `confidence`, `reasoning`, and
`model_or_rule_used`. Rules have versioned provenance (`rules:v1:…`); the provider
stamps `llm:<selected model>` (including gateway fallback) rather than trusting generated provenance.
Pydantic rejects invalid types, confidence ranges, empty reasoning and extra fields.

## Routing and evidence

Rules inspect filename tokens, format/MIME type, title/subject metadata, weak
declared-type hints, short headings near the start of extracted text, BOQ table
headers and drawing title blocks. Filename directory components are excluded.
EML/MSG containers identify email messages directly; an email-upload source alone
does not make a PDF attachment an email. Repeated words do not boost confidence.
Independent corroborating signals can. Conflicting or weak candidates abstain.
Rule explanations summarize evidence categories without quoting document text.

`CLASSIFICATION_RULE_THRESHOLD` defaults to 0.85;
`CLASSIFICATION_RULE_MARGIN` defaults to 0.12. Only inconclusive rules invoke an
available LLM. The provider receives allowlisted metadata and at most the first
16,000 extracted characters, with document instructions treated as untrusted data.
The central [model gateway](../../ai/gateway/README.md) applies the classification
task policy, validates JSON, and permits one malformed-output repair.

Without a configured LLM, inconclusive evidence returns low-confidence `other`
for review. Exhausted gateway requests propagate to the pipeline dead-letter path; they are not converted into fabricated classifications.
Confidence scores are heuristics, not calibrated probabilities.

## Persistence and review

Migration 0007 adds nullable `documents.classification_result` JSONB. New
classifications persist all four fields and update `document_type` alongside the
stage checkpoint. Registry responses expose `classification_result`. Historical
records may have null results; existing labels and completed checkpoints are
not automatically rewritten.

Confidence **below** `CLASSIFICATION_REVIEW_THRESHOLD` (default 0.8) sets
`processing_status` and coarse `status` to `review_required`, creates one pending
review task and stops before field extraction. Equal confidence continues.
Repeated delivery does not reclassify or duplicate review tasks. Classification
confidence is separate from the later field-extraction confidence.

Known site-photo filenames/metadata can classify without OCR or a vision-model
call. Textless images with unavailable OCR can still reach classification. Even
a confident classification without text pauses for visual review, preserving
originals and checkpoints instead of attempting extraction from an empty string.
OCR for other documents remains a separate stage with its own provider policy.

Run `alembic upgrade head` before updated API/workers. New classifications use
the exact taxonomy above instead of the earlier `invoice`/`correspondence` labels.
Invoices without another recognized purpose become `other`; email containers
become `email`. Legacy labels remain readable. No public manual-review/replay
endpoint is added in this feature.

## Golden evaluation

`tests/fixtures/classification/golden.json` contains 22 synthetic documents
covering all ten types, including a misleading filename and an unlabelled image.

```sh
python -m app.evaluation.classification
python -m app.evaluation.classification --min-accuracy 0.9 --output classification-report.json
python -m app.evaluation.classification --dataset path/to/golden.json
```

Default evaluation is offline, with zero model calls. Reports include accuracy,
per-type precision/recall, confusion matrix, review count, confident coverage,
LLM calls and failed IDs. A minimum accuracy controls the exit code. Empty
datasets, duplicate IDs and invalid labels are rejected. Custom cases contain
`id`, `expected`, and `input` (`filename`, `metadata`, `extracted_text`).

Baseline: **20/22 correct (90.91%)**, **18/22 confident coverage (81.82%)**,
four low-confidence reviews, zero LLM calls. Two `other` cases are correct
abstentions; the ambiguous RFI and unlabelled photo are scored as misses. Small
synthetic cases do not establish production accuracy or calibration.

Opt in to live fallback evaluation explicitly:

```sh
LLM_PROVIDER=openai LLM_API_KEY=… python -m app.evaluation.classification --llm
```

Live mode requires a configured key/provider, uses the configured review
threshold, sends inconclusive document evidence to the model, and may incur API
costs. Offline CLI evaluation uses the documented default rule thresholds;
custom experiments can call `evaluate` with a configured classifier instance.
CI injects mocked fallback responses to test routing; live model accuracy has
not been measured by these tests.

Reference: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
