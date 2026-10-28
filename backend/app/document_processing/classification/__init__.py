"""Rules-first document classification."""

from app.document_processing.classification.service import (
    ClassificationInput,
    ClassificationService,
    RuleFirstClassifier,
)

__all__ = ["ClassificationInput", "ClassificationService", "RuleFirstClassifier"]
