"""Gateway routing, bounded provider behavior, privacy and architecture contracts."""

# ruff: noqa: PLR2004
import ast
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.concurrency import run_in_threadpool

from app.ai.gateway.config import ModelPricing, RetryPolicy, TaskPolicy, TaskType
from app.ai.gateway.context import current_scope, model_scope
from app.ai.gateway.provider import OpenAIProvider, strict_schema
from app.ai.gateway.service import ModelGateway
from app.ai.gateway.types import (
    GatewayRefusedError,
    GatewayUnavailableError,
    GatewayValidationError,
    ProviderCallError,
    ProviderResponse,
    Usage,
)
from app.core.config import Settings
from app.core.logging import JSONFormatter
from app.core.redaction import REDACTED, redact
from app.document_processing.providers import Services
from app.document_processing.structured.service import StructuredExtractionError
from tests.structured_cases import case


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    count: int


MESSAGES = [{"role": "user", "content": "PRIVATE SOURCE DATA"}]
VALID = '{"answer":"grounded", "count":2}'


@pytest.fixture
def gateway():
    policy = TaskPolicy(
        model="primary",
        temperature=0.3,
        max_tokens=777,
        timeout=12,
        retry_policy=RetryPolicy(max_retries=1, backoff_seconds=0.25),
        fallback_model="fallback",
    )
    settings = Settings(
        _env_file=None,
        debug=False,
        model_gateway_tasks={task: policy for task in TaskType if task != TaskType.EMBEDDING},
        model_gateway_prices={"primary": ModelPricing(input_per_million=1, output_per_million=2)},
    )
    provider = Mock()
    provider.generate.return_value = ProviderResponse(content=VALID, usage=Usage(10, 20))
    events = []
    service = ModelGateway(
        settings=settings,
        provider=provider,
        emit=lambda event, **fields: events.append({"event": event, **fields}),
        sleep=Mock(),
    )
    service.events = events
    return service


@pytest.mark.parametrize("task", [task for task in TaskType if task != TaskType.EMBEDDING])
def test_all_tasks_apply_policy(gateway, task):
    result = gateway.generate(task, MESSAGES, prompt_version="task-v1", schema=Answer)
    policy = gateway.provider.generate.call_args.kwargs["policy"]
    assert (policy.model, policy.temperature, policy.max_tokens, policy.timeout) == (
        "primary",
        0.3,
        777,
        12,
    )
    assert result.value.count == 2 and result.model == "primary"
    assert result.cost_estimate == pytest.approx(0.00005)
    assert gateway.events[-1]["task_type"] == task.value


def test_task_environment_configuration(monkeypatch):
    monkeypatch.setenv(
        "MODEL_GATEWAY_TASKS",
        json.dumps(
            {
                "drafting": {
                    "model": "configured",
                    "temperature": 0.6,
                    "max_tokens": 100,
                    "timeout": 7,
                    "retry_policy": {"max_retries": 0},
                    "fallback_model": "backup",
                }
            }
        ),
    )
    service = ModelGateway(
        settings=Settings(_env_file=None, debug=False), provider=Mock(), emit=Mock()
    )
    assert service.policies[TaskType.DRAFTING].model == "configured"
    assert service.policies[TaskType.DRAFTING].fallback_model == "backup"
    assert set(service.policies) == set(TaskType)


@pytest.mark.parametrize(
    "override",
    [
        {"temperature": float("nan")},
        {"max_tokens": 0},
        {"timeout": 0},
        {"retry_policy": {"max_retries": 4}},
        {"unknown": True},
    ],
)
def test_invalid_task_configuration(override):
    with pytest.raises(ValidationError):
        TaskPolicy(model="primary", **override)


@pytest.mark.parametrize(
    "malformed",
    [
        "not JSON",
        '{"answer":"a"}',
        '{"answer":"a","count":NaN}',
        '{"answer":"a","count":1,"count":2}',
        '{"answer":"a","count":1,"injected":true}',
    ],
)
def test_malformed_output_repaired_once(gateway, malformed):
    gateway.provider.generate.side_effect = [
        ProviderResponse(content=malformed, usage=Usage(10, 20)),
        ProviderResponse(content=VALID, usage=Usage(10, 20)),
    ]
    result = gateway.generate("extraction", MESSAGES, prompt_version="extract-v1", schema=Answer)
    assert result.value.count == 2 and gateway.provider.generate.call_count == 2
    repair = gateway.provider.generate.call_args.kwargs["messages"]
    assert repair[-2]["content"] == malformed and "Repair" in repair[-1]["content"]
    assert MESSAGES == [{"role": "user", "content": "PRIVATE SOURCE DATA"}]
    assert result.usage == Usage(20, 40)
    assert result.cost_estimate == pytest.approx(0.0001)
    assert [e["validation_result"] for e in gateway.events] == ["invalid", "valid", "valid"]


def test_repeated_invalid_output_stops_and_is_safe(gateway):
    gateway.provider.generate.return_value = ProviderResponse(content="SECRET INVALID OUTPUT")
    with pytest.raises(GatewayValidationError) as failure:
        gateway.generate("extraction", MESSAGES, prompt_version="extract-v1", schema=Answer)
    assert gateway.provider.generate.call_count == 2
    assert "SECRET" not in str(failure.value)
    assert "SECRET" not in json.dumps(gateway.events)
    assert gateway.events[-1]["validation_result"] == "invalid"


def test_truncation_is_repaired(gateway):
    gateway.provider.generate.side_effect = [
        ProviderResponse(content='{"answer":', finish_reason="length"),
        ProviderResponse(content=VALID),
    ]
    assert (
        gateway.generate("extraction", MESSAGES, prompt_version="v1", schema=Answer).value.count
        == 2
    )
    assert gateway.provider.generate.call_count == 2


@pytest.mark.parametrize(
    "response", [ProviderResponse(refused=True), ProviderResponse(finish_reason="content_filter")]
)
def test_refusal_is_never_repaired_or_fallback(gateway, response):
    gateway.provider.generate.return_value = response
    with pytest.raises(GatewayRefusedError):
        gateway.generate("reasoning", MESSAGES, prompt_version="v1", schema=Answer)
    assert gateway.provider.generate.call_count == 1
    gateway.sleep.assert_not_called()
    assert gateway.events[-1]["validation_result"] == "refused"


def test_transport_retries_then_fallback(gateway):
    gateway.provider.generate.side_effect = [
        ProviderCallError(retryable=True),
        ProviderCallError(retryable=True),
        ProviderResponse(content=VALID, usage=Usage(2, 3)),
    ]
    result = gateway.generate("reasoning", MESSAGES, prompt_version="v1", schema=Answer)
    assert [call.kwargs["policy"].model for call in gateway.provider.generate.call_args_list] == [
        "primary",
        "primary",
        "fallback",
    ]
    gateway.sleep.assert_called_once_with(0.25)
    assert result.model == "fallback" and result.usage == Usage(2, 3)
    assert result.cost_estimate is None and not gateway.events[-1]["usage_complete"]


def test_provider_failures_are_bounded(gateway):
    gateway.provider.generate.side_effect = ProviderCallError(retryable=True)
    with pytest.raises(GatewayUnavailableError):
        gateway.generate("reasoning", MESSAGES, prompt_version="v1")
    assert gateway.provider.generate.call_count == 4
    assert gateway.events[-1]["validation_result"] == "provider_error"


def test_permanent_failure_not_retried(gateway):
    gateway.provider.generate.side_effect = ProviderCallError(retryable=False)
    with pytest.raises(GatewayUnavailableError):
        gateway.generate("drafting", MESSAGES, prompt_version="v1")
    gateway.provider.generate.assert_called_once()


def test_repair_budget_is_shared_across_fallback(gateway):
    gateway.policies[TaskType.EXTRACTION] = gateway.policies[TaskType.EXTRACTION].model_copy(
        update={"retry_policy": RetryPolicy(max_retries=0)}
    )
    gateway.provider.generate.side_effect = [
        ProviderResponse(content="bad"),
        ProviderCallError(retryable=True),
        ProviderResponse(content="still bad"),
    ]
    with pytest.raises(GatewayValidationError):
        gateway.generate("extraction", MESSAGES, prompt_version="v1", schema=Answer)
    assert gateway.provider.generate.call_count == 3
    assert gateway.provider.generate.call_args.kwargs["policy"].model == "fallback"


def test_domain_validation_uses_same_repair_budget(gateway):
    def grounded(value):
        if value.count != 1:
            raise ValueError("PRIVATE validation detail")
        return value

    gateway.provider.generate.side_effect = [
        ProviderResponse(content=VALID),
        ProviderResponse(content='{"answer":"ok","count":1}'),
    ]
    result = gateway.generate(
        "extraction", MESSAGES, prompt_version="v1", schema=Answer, validator=grounded
    )
    assert result.value.count == 1
    assert "PRIVATE" not in json.dumps(gateway.events)


def test_actual_serialized_audit_fields_and_privacy(gateway):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger("gateway-test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    gateway.emit = lambda event, **fields: logger.info({"event": event, **fields})
    tenant, project = uuid4(), uuid4()
    try:
        with model_scope(tenant, project):
            result = gateway.generate(
                "extraction", MESSAGES, prompt_version="extract-v2", schema=Answer
            )
    finally:
        logger.removeHandler(handler)
    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(events) == 2
    for event in events:
        assert event["trace_id"] == result.trace_id
        assert event["tenant_id"] == str(tenant) and event["project_id"] == str(project)
        assert event["prompt_version"] == "extract-v2"
        assert len(event["input_hash"]) == 64
        assert event["usage"] == {"input_tokens": 10, "output_tokens": 20}
        assert event["cost_estimate"] == pytest.approx(0.00005)
        assert event["latency_ms"] >= 0 and event["validation_result"] == "valid"
    assert "PRIVATE SOURCE DATA" not in stream.getvalue() and "grounded" not in stream.getvalue()


def test_redaction_exceptions_do_not_expose_token_strings():
    assert redact(
        {
            "input_tokens": "secret-token",
            "output_tokens": {"value": "secret"},
            "prompt_version": "raw prompt text",
            "api_token": 42,
        }
    ) == {
        "input_tokens": REDACTED,
        "output_tokens": REDACTED,
        "prompt_version": REDACTED,
        "api_token": REDACTED,
    }


def test_hash_is_stable_and_scoped(gateway):
    a, b = uuid4(), uuid4()
    with model_scope(a):
        gateway.generate("reasoning", MESSAGES, prompt_version="v1")
        gateway.generate("reasoning", MESSAGES, prompt_version="v1")
    with model_scope(b):
        gateway.generate("reasoning", MESSAGES, prompt_version="v1")
    summaries = [e for e in gateway.events if e["event"] == "model_gateway_result"]
    assert summaries[0]["input_hash"] == summaries[1]["input_hash"]
    assert summaries[0]["input_hash"] != summaries[2]["input_hash"]
    assert len({e["trace_id"] for e in summaries}) == 3
    assert current_scope().tenant_id is None


async def test_scope_survives_threadpool(gateway):
    tenant, project = uuid4(), uuid4()
    with model_scope(tenant, project):
        await run_in_threadpool(gateway.generate, "summarization", MESSAGES, prompt_version="v1")
    assert gateway.events[-1]["project_id"] == str(project)
    assert current_scope().project_id is None


def test_embeddings_also_use_gateway(gateway):
    gateway.provider.embed.return_value = ProviderResponse(
        vectors=[[1.0] + [0.0] * 1535], usage=Usage(5, 0)
    )
    result = gateway.embed(["text"])
    assert len(result.value[0]) == 1536
    assert gateway.events[-1]["task_type"] == "embedding"
    assert gateway.provider.embed.call_args.kwargs["policy"].model == "text-embedding-3-small"
    gateway.provider.generate.assert_not_called()


@pytest.mark.parametrize("vectors", [None, [], [[0.0] * 1536], [[float("nan")] * 1536], [[1.0]]])
def test_invalid_embedding_response_is_rejected(gateway, vectors):
    gateway.provider.embed.return_value = ProviderResponse(vectors=vectors)
    with pytest.raises(GatewayValidationError):
        gateway.embed(["text"])
    gateway.provider.embed.assert_called_once()


def test_provider_uses_configured_request_and_no_sdk_retry(monkeypatch):
    import openai

    settings = Settings(_env_file=None, debug=False, llm_provider="openai", llm_api_key="test-only")
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=VALID, refusal=None), finish_reason="stop"
            )
        ],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=6),
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr(openai, "OpenAI", factory)
    response = OpenAIProvider(settings).generate(
        policy=TaskPolicy(model="primary", temperature=0.4, max_tokens=333, timeout=9),
        messages=MESSAGES,
        schema=Answer.model_json_schema(),
    )
    assert factory.call_args.kwargs["max_retries"] == 0
    args = client.chat.completions.create.call_args.kwargs
    assert (args["model"], args["temperature"], args["max_completion_tokens"], args["timeout"]) == (
        "primary",
        0.4,
        333,
        9,
    )
    assert args["response_format"]["json_schema"]["strict"]
    assert response.usage == Usage(5, 6)


@pytest.mark.parametrize("status,retryable", [(401, False), (400, False), (429, True), (500, True)])
def test_provider_status_classification(status, retryable):
    from openai import APIStatusError

    client = Mock()
    client.chat.completions.create.side_effect = APIStatusError(
        "SECRET PROVIDER BODY",
        response=httpx.Response(status, request=httpx.Request("POST", "https://example.invalid")),
        body=None,
    )
    with pytest.raises(ProviderCallError) as failure:
        OpenAIProvider(None, client=client).generate(
            policy=TaskPolicy(model="model"), messages=MESSAGES, schema=None
        )
    assert failure.value.retryable == retryable
    assert "SECRET" not in str(failure.value)


def test_strict_schema_does_not_mutate_original():
    schema = {"type": "object", "properties": {"value": {"type": "string", "default": "x"}}}
    strict = strict_schema(schema)
    assert strict["required"] == ["value"] and strict["additionalProperties"] is False
    assert "default" not in strict["properties"]["value"]
    assert schema["properties"]["value"]["default"] == "x"


def test_production_extraction_uses_one_gateway_repair(gateway):
    data, source = case("contract")
    gateway.provider.generate.side_effect = [
        ProviderResponse(content="bad"),
        ProviderResponse(content=json.dumps(data)),
    ]
    result = Services(gateway=gateway).extract(source, {"document_type": "contract"})
    assert result["fields"] == data
    assert result["model_or_rule_used"] == "llm:primary"
    assert len(result["attempts"]) == 2 and gateway.provider.generate.call_count == 2


def test_production_extraction_exhaustion_does_not_start_another_loop(gateway):
    _, source = case("contract")
    gateway.provider.generate.return_value = ProviderResponse(content="bad")
    with pytest.raises(StructuredExtractionError):
        Services(gateway=gateway).extract(source, {"document_type": "contract"})
    assert gateway.provider.generate.call_count == 2


def test_vision_ocr_uses_extraction_gateway(gateway):
    gateway.provider.generate.return_value = ProviderResponse(content="OCR result")
    services = Services(gateway=gateway)
    services.settings = services.settings.model_copy(update={"ocr_provider": "none"})
    assert services.ocr(b"fake-image", "png") == "OCR result"
    assert gateway.events[-1]["task_type"] == "extraction"
    assert gateway.events[-1]["prompt_version"] == "vision-ocr-v1"


def test_provider_sdk_boundary():
    app_root = Path(__file__).resolve().parents[1] / "app"
    violations = []
    banned = (
        "openai",
        "anthropic",
        "langchain_openai",
        "langchain_anthropic",
        "litellm",
        "google.genai",
        "google.generativeai",
    )
    for path in app_root.rglob("*.py"):
        if path == app_root / "ai" / "gateway" / "provider.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            elif isinstance(node, ast.Call):
                function = ast.unparse(node.func)
                if (
                    function in {"__import__", "importlib.import_module"}
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                ):
                    modules = [str(node.args[0].value)]
                if function.endswith(
                    (
                        ".chat.completions.create",
                        ".responses.create",
                        ".embeddings.create",
                        ".messages.create",
                    )
                ):
                    violations.append(str(path))
            if any(
                module == prefix or module.startswith(prefix + ".")
                for module in modules
                for prefix in banned
            ):
                violations.append(str(path))
    assert violations == [], f"Provider calls must use the model gateway: {violations}"


async def test_processing_stage_binds_document_scope():
    from app.document_processing.extraction.types import ExtractionResult, TextBlock
    from app.document_processing.pipeline import execute_stage

    document = SimpleNamespace(tenant_id=uuid4(), project_id=uuid4())
    observed = []
    services = Mock()
    services.extract.side_effect = lambda *_: observed.append(current_scope()) or {"ok": True}
    data = {
        "extract_text": ExtractionResult(blocks=[TextBlock(text="source")]).model_dump(mode="json"),
        "classify_document": {"document_type": "contract"},
    }
    await execute_stage("extract_fields", document, data, Mock(), services, Mock())
    assert observed[0].tenant_id == document.tenant_id
    assert observed[0].project_id == document.project_id
    assert current_scope().tenant_id is None


def test_provider_exception_details_never_enter_logs(gateway):
    gateway.provider.generate.side_effect = RuntimeError("api_key=SECRET raw private document")
    with pytest.raises(GatewayUnavailableError) as failure:
        gateway.generate("reasoning", MESSAGES, prompt_version="v1")
    assert "SECRET" not in str(failure.value) + json.dumps(gateway.events)
    assert gateway.events[-1]["validation_result"] == "provider_error"


def test_unknown_prices_and_usage_are_explicit(gateway):
    gateway.prices = {}
    gateway.provider.generate.return_value = ProviderResponse(content=VALID)
    result = gateway.generate("extraction", MESSAGES, prompt_version="v1", schema=Answer)
    assert result.cost_estimate is None
    assert gateway.events[-1]["cost_estimate"] is None
    assert gateway.events[-1]["usage_complete"] is False


def test_embedding_fallback_cannot_change_vector_space():
    settings = Settings(
        _env_file=None,
        debug=False,
        model_gateway_tasks={
            TaskType.EMBEDDING: TaskPolicy(model="text-embedding-3-small", fallback_model="other")
        },
    )
    with pytest.raises(ValueError):
        ModelGateway(settings=settings, provider=Mock(), emit=Mock())


def test_version_redaction_does_not_accept_api_key_shaped_values():
    assert redact({"raw_output": "private model answer"})["raw_output"] == REDACTED
    assert redact({"prompt_version": "sk-not-a-version"})["prompt_version"] == REDACTED


def test_embedding_provider_preserves_batch_order():
    client = Mock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(index=1, embedding=[2]), SimpleNamespace(index=0, embedding=[1])],
        usage=SimpleNamespace(prompt_tokens=9),
    )
    result = OpenAIProvider(None, client=client).embed(
        policy=TaskPolicy(model="embedding", timeout=7), texts=["a", "b"]
    )
    assert result.vectors == [[1], [2]] and result.usage == Usage(9, 0)
    assert client.embeddings.create.call_args.kwargs["timeout"] == 7


def test_validator_failure_still_accounts_for_provider_usage(gateway):
    def broken(_):
        raise RuntimeError("PRIVATE validator bug")

    with pytest.raises(GatewayValidationError):
        gateway.generate(
            "extraction", MESSAGES, prompt_version="v1", schema=Answer, validator=broken
        )
    gateway.provider.generate.assert_called_once()
    assert gateway.events[-1]["usage"] == {"input_tokens": 10, "output_tokens": 20}
    assert gateway.events[-1]["validation_result"] == "validation_error"
    assert "PRIVATE" not in json.dumps(gateway.events)


def test_validator_without_schema_is_rejected(gateway):
    with pytest.raises(ValueError):
        gateway.generate("extraction", MESSAGES, prompt_version="v1", validator=lambda value: value)
    gateway.provider.generate.assert_not_called()
