"""Validated task routing, budgets, retry policies and operator-supplied pricing."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TaskType(StrEnum):
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    RETRIEVAL_QUERY_UNDERSTANDING = "retrieval_query_understanding"
    REASONING = "reasoning"
    DRAFTING = "drafting"
    SUMMARIZATION = "summarization"
    EMBEDDING = "embedding"


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_retries: int = Field(default=1, ge=0, le=3)
    backoff_seconds: float = Field(default=0.25, ge=0, le=5, allow_inf_nan=False)


class TaskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_./:-]+$")
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    max_tokens: int = Field(default=4096, ge=1, le=32768)
    timeout: float = Field(default=60, gt=0, le=120, allow_inf_nan=False)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    fallback_model: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_./:-]+$"
    )


class ModelPricing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input_per_million: float = Field(ge=0, allow_inf_nan=False)
    output_per_million: float = Field(ge=0, allow_inf_nan=False)


def task_policies(settings):
    models = {
        TaskType.CLASSIFICATION: settings.default_classification_model,
        TaskType.EXTRACTION: settings.default_extraction_model,
        TaskType.RETRIEVAL_QUERY_UNDERSTANDING: settings.default_classification_model,
        TaskType.REASONING: settings.default_reasoning_model,
        TaskType.DRAFTING: settings.default_drafting_model,
        TaskType.SUMMARIZATION: settings.default_classification_model,
        TaskType.EMBEDDING: settings.embedding_model,
    }
    policies = {
        task: TaskPolicy(
            model=model,
            temperature=0.2 if task == TaskType.DRAFTING else 0,
            max_tokens=settings.max_tokens_per_request,
            timeout=min(settings.ai_request_timeout, 60),
            retry_policy=RetryPolicy(max_retries=min(settings.ai_max_retries, 3)),
        )
        for task, model in models.items()
    }
    policies.update(settings.model_gateway_tasks)
    # Embedding-space changes cannot silently reuse existing vector model labels.
    embedding = policies[TaskType.EMBEDDING]
    if embedding.model != settings.embedding_model or embedding.fallback_model is not None:
        raise ValueError("Embedding policy must use EMBEDDING_MODEL without a fallback")
    return policies
