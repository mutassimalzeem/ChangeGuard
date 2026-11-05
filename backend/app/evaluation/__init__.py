"""ChangeGuard evaluation harness package."""

from app.evaluation.config import (
    CRITICAL_FIELDS,
    MAX_UNSUPPORTED_FACTUAL_CLAIMS,
    MIN_CITATION_COVERAGE,
    MIN_CLASSIFICATION_ACCURACY,
    MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY,
    EvaluationSuite,
    find_golden_dir,
)
from app.evaluation.harness import EvaluationHarness

__all__ = [
    "CRITICAL_FIELDS",
    "MAX_UNSUPPORTED_FACTUAL_CLAIMS",
    "MIN_CITATION_COVERAGE",
    "MIN_CLASSIFICATION_ACCURACY",
    "MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY",
    "EvaluationHarness",
    "EvaluationSuite",
    "find_golden_dir",
]
