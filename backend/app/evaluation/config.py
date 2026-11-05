"""Evaluation harness configuration, constants, and quality thresholds."""

from enum import StrEnum
from pathlib import Path

# Quality thresholds required for CI gating
MIN_CLASSIFICATION_ACCURACY = 0.90  # 90%
MIN_CRITICAL_FIELD_EXTRACTION_ACCURACY = 0.85  # 85%
MIN_CITATION_COVERAGE = 0.95  # 95%
MAX_UNSUPPORTED_FACTUAL_CLAIMS = 0  # Zero hallucinations allowed

# Critical fields per document schema required for compliance
CRITICAL_FIELDS = {
    "contract": ["reference", "title", "employer", "contractor", "contract_value"],
    "boq": ["title", "stated_total", "items"],
    "rfi": ["rfi_number", "subject", "question"],
    "change_order": ["co_number", "title", "amount", "status"],
    "daily_report": ["report_date", "activities", "weather"],
    "email": ["subject", "sender", "recipient", "body"],
    "site_photo": ["title", "description"],
}


class EvaluationSuite(StrEnum):
    ALL = "all"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    ENTITY_LINKING = "entity_linking"
    RETRIEVAL = "retrieval"
    CITATIONS = "citations"
    GROUNDEDNESS = "groundedness"
    REFUSAL = "refusal"
    DUPLICATES = "duplicates"
    RISKS = "risks"
    COMPARISON = "comparison"


class GoldenDatasetNotFoundError(FileNotFoundError):
    """Raised when tests/golden directory cannot be located."""

    def __init__(
        self,
        message: str = (
            "Could not locate tests/golden directory with manifest.json. "
            "Please provide --golden-dir."
        ),
    ) -> None:
        super().__init__(message)


def find_golden_dir(explicit_path: Path | None = None) -> Path:
    """Resolve the golden evaluation dataset path from various invocation contexts."""
    if explicit_path and explicit_path.exists():
        return explicit_path

    candidates = [
        Path(__file__).resolve().parents[3] / "tests/golden",
        Path("tests/golden").resolve(),
        Path("../tests/golden").resolve(),
        Path("../../tests/golden").resolve(),
    ]
    for c in candidates:
        if c.exists() and (c / "manifest.json").exists():
            return c
    raise GoldenDatasetNotFoundError
