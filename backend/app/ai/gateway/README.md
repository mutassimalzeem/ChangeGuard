# Model gateway (feature 4.3)

All model traffic must enter `app.ai.gateway.service.ModelGateway`. The only
provider SDK boundary is `gateway/provider.py`; the architecture unit test rejects
SDK imports, dynamic imports, and completion/embedding calls elsewhere in `app`.
The implemented transport is the existing OpenAI provider. Tests inject the
provider protocol; adding another transport belongs inside the gateway package.

The gateway supports these generation tasks:

| Task | Default model setting | Default temperature |
| --- | --- | --- |
| classification | DEFAULT_CLASSIFICATION_MODEL | 0 |
| extraction | DEFAULT_EXTRACTION_MODEL | 0 |
| retrieval_query_understanding | DEFAULT_CLASSIFICATION_MODEL | 0 |
| reasoning | DEFAULT_REASONING_MODEL | 0 |
| drafting | DEFAULT_DRAFTING_MODEL | 0.2 |
| summarization | DEFAULT_CLASSIFICATION_MODEL | 0 |

Each resolved task policy includes model, temperature, max_tokens, timeout,
retry_policy (max_retries and backoff_seconds), and fallback_model. Defaults reuse
`MAX_TOKENS_PER_REQUEST`, `min(AI_REQUEST_TIMEOUT, 60)`, up to three legacy
`AI_MAX_RETRIES`, 0.25-second initial backoff and no fallback. A configured task
entry replaces that task's default policy; omitted policy fields use TaskPolicy's
4096 tokens, 60 seconds, zero temperature, one retry and no fallback.

`MODEL_GATEWAY_TASKS` accepts a JSON object, for example:

```json
{
  "reasoning": {
    "model": "gpt-4o",
    "temperature": 0,
    "max_tokens": 4096,
    "timeout": 45,
    "retry_policy": {"max_retries": 1, "backoff_seconds": 0.25},
    "fallback_model": "gpt-4o-mini"
  }
}
```

Policies reject unknown fields, nonfinite values and unbounded budgets. Timeout
is per provider attempt (up to 120 seconds), not a total invocation deadline.
The selected primary and fallback must support the configured Chat Completions
parameters and, for structured calls, the strict JSON schema subset.

Usage inside an already authorized business operation:

```python
from app.ai.gateway.config import TaskType
from app.ai.gateway.context import model_scope
from app.ai.gateway.service import ModelGateway

with model_scope(tenant_id, project_id):
    result = ModelGateway().generate(
        TaskType.REASONING,
        messages=[{"role": "user", "content": authorized_evidence}],
        prompt_version="risk-reasoning-v1",
        schema=ReasoningSchema,  # a Pydantic output model
    )
    validated_output = result.value
```

`model_scope` carries trusted UUIDs through async calls and Starlette threadpools;
it resets on exit/failure. It is audit context, not an authorization service.
Callers must perform permission filtering first. Document processing binds each
stage's document tenant/project. Retrieval binds the authenticated tenant and
requested project around query embedding; tenant-wide search has project_id=null.
Offline/system calls without business context log null tenant/project IDs.
Generation tasks have no new public endpoints and do not confer authority to
approve, persist verified claims, or bypass evidence rules.

Structured calls use a strict provider JSON schema and local Pydantic validation.
The parser rejects duplicate keys, nonfinite constants, malformed/fenced JSON,
and responses above one million characters. An optional `validator` runs on the
parsed model for domain checks; it requires a schema. Extraction supplies its
existing source-evidence validator. Plain text must be nonempty and bounded.

Malformed, truncated, schema-invalid or unsupported structured output receives
exactly one repair attempt containing the original messages and bounded prior
output plus a fixed repair instruction. A second invalid result raises
GatewayValidationError. Refusals/content filtering are terminal: no repair or
fallback is attempted. Unexpected domain-validator bugs are logged and fail safely
without repair. Provider errors never appear in exception messages or logs.

Connection/timeouts, 408/409/429 and 5xx responses use the task's bounded
exponential retry policy (backoff capped at five seconds). After exhaustion, one
configured fallback model can be selected. Permanent provider errors are terminal.
SDK automatic retries are disabled. The repair flag and retry counters are shared
across the invocation, including fallback; a fallback cannot reset the repair
budget. At most `2 * (max_retries + 1) + 1` provider attempts occur with fallback
and repair combined. Internally created SDK clients close after each attempt.

`embed(texts)` is an additional gateway operation so no embeddings SDK calls
remain outside the boundary. It validates batch size, finite nonzero 1536-value
vectors and provider result ordering. Its policy uses EMBEDDING_MODEL; overrides
cannot change that model or enable fallback, because mixing embedding spaces
would invalidate stored chunk metadata. Temperature/max_tokens do not apply to
the embeddings API. Embedding schema failures are terminal, without a text repair.

Two structured audit events are emitted: `model_gateway_attempt` for each call and
`model_gateway_result` for the final outcome. Both include trace_id, tenant_id,
project_id, task_type, selected model, prompt_version, input_hash, usage counters,
latency_ms, cost_estimate, cost_currency and validation_result. All attempts share
a trace UUID and the original input hash; attempts also include a hash of their
actual payload. Original hashes include scope, task, schema and prompt version.
The final event aggregates known token counts, latency (including backoff), and
cost over retries/repairs/fallback. `usage_complete=false` marks unknown usage.

Configure `MODEL_GATEWAY_PRICES` with current operator-maintained USD rates per
million tokens: each model key maps to `input_per_million` and
`output_per_million`. Cost is `(input_count * input_rate + output_count *
output_rate) / 1_000_000`. No prices are guessed or hardcoded: cost_estimate is null
when rates or usage are unavailable; the aggregate is null if any attempt is
unknown. These are estimates, not invoices. Prompt versions are short identifiers
such as `v1` or `structured-extraction-v1`; they cannot be arbitrary prompt text.
The redactor permits only nonnegative integer token counters and bounded version
identifiers while continuing to mask credentials, prompts and raw content.

Audit logs contain no input/output bodies, source text, image bytes, credentials,
validation input values, or provider exception messages. Internal result attempt
history retains bounded raw responses for the existing durable extraction-review
workflow; it must not be logged. Audit events use the existing structured logging
pipeline, without a new database table or schema migration.

Existing classification, structured extraction, vision OCR and ingestion/query
embeddings now route through the gateway. Classification/extraction provenance
uses the selected model, including fallback. Production extraction uses one
shared gateway repair budget; it no longer stacks the standalone
SchemaConstrainedExtractor repair loop on top. The legacy
STRUCTURED_EXTRACTION_REPAIR_RETRIES setting does not control production gateway
calls. Gateway exhaustion reaches the processing dead-letter path; Celery no
longer replays already-exhausted provider retry budgets. Storage/database retries
remain in the worker. Existing model/key settings still work; task and price
configuration is optional. No Python dependencies or migrations are added.

Validation uses mocked providers and actual PostgreSQL processing/retrieval
integration tests, including SDK request parameters, retry/fallback exhaustion,
refusals, malformed/schema/domain output, scope propagation, exact rendered audit
fields, cost accounting, redaction and the no-direct-SDK architecture rule.
No paid/live provider requests are needed for tests.

Provider contract reference: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
