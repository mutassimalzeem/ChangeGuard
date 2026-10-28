"""Deterministic evidence before an optional, validated LLM fallback."""

import re
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.document_processing.schema import Classification

RULE_VERSION = "rules:v1"
METADATA_KEYS = ("file_type", "mime_type", "title", "subject", "document_type")
# Specific titles, not arbitrary keyword mentions throughout a contract's body.
PATTERNS = {
    "contract": r"\b(?:contract|construction agreement|subcontract|conditions of contract)\b",
    "boq": r"\b(?:boq|bill of quantities|schedule of quantities)\b",
    "drawing": (
        r"\b(?:drawing|drawings|floor plan|section detail|structural plan|"
        r"as built|shop drawing)\b"
    ),
    "rfi": r"\b(?:rfi|request for information)\b",
    "change_order": r"\b(?:change order|variation order|change instruction|co\s*\d+)\b",
    "daily_report": r"\b(?:daily report|daily site report|site diary|daily progress report)\b",
    "site_photo": r"\b(?:site photo|site photograph|progress photo|site inspection photo)\b",
    "email": r"\b(?:email|e mail)\b",
    "quotation": r"\b(?:quotation|quote|price offer|request for quotation response)\b",
}


class ClassificationInput(BaseModel):
    filename: str = Field(default="", max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)
    extracted_text: str = Field(default="", max_length=2_000_000)

    def safe_metadata(self):
        return {
            key: str(self.metadata[key])[:512]
            for key in METADATA_KEYS
            if isinstance(self.metadata.get(key), (str, int, float))
        }


class ClassificationService(Protocol):
    def classify(self, document: ClassificationInput) -> Classification: ...


def normalized(value):
    return re.sub(r"[_\-]+", " ", value.casefold())


class RuleFirstClassifier:
    def __init__(
        self,
        fallback: Callable[[ClassificationInput], Classification | dict] | None = None,
        *,
        rule_threshold: float = 0.85,
        margin: float = 0.12,
    ):
        if not 0 <= rule_threshold <= 1 or not 0 <= margin <= 1:
            raise ValueError("Invalid classifier thresholds")
        self.fallback, self.rule_threshold, self.margin = fallback, rule_threshold, margin

    def rules(self, document: ClassificationInput) -> Classification:
        metadata = document.safe_metadata()
        filename = PurePosixPath(document.filename.replace("\\", "/")).name
        extension = (
            str(metadata.get("file_type") or PurePosixPath(filename).suffix).lower().lstrip(".")
        )
        mime = metadata.get("mime_type", "").lower()
        if extension in {"eml", "msg"} or mime in {"message/rfc822", "application/vnd.ms-outlook"}:
            return Classification(
                document_type="email",
                confidence=0.99,
                reasoning="The file format identifies an email message container.",
                model_or_rule_used=f"{RULE_VERSION}:email_format",
            )

        scores, signals = {}, {}

        def evidence(kind, confidence, source):
            # Corroboration across independent sources helps; repeated words do not.
            scores[kind] = max(scores.get(kind, 0), confidence)
            signals.setdefault(kind, set()).add(source)

        name = normalized(PurePosixPath(filename).stem)
        # Only title-like lines near the beginning are decisive. Body references are weak.
        lines = [
            line.strip() for line in document.extracted_text[:12000].splitlines() if line.strip()
        ]
        titles = [line for line in lines[:8] if len(line) <= 140]
        image = extension in {"jpg", "jpeg", "png"} or mime.startswith("image/")
        for kind, pattern in PATTERNS.items():
            if re.search(pattern, name):
                evidence(kind, 0.90, "filename")
            if any(
                re.search(pattern, normalized(str(metadata.get(key, ""))))
                for key in ("title", "subject")
            ):
                evidence(kind, 0.88, "metadata_title")
            if metadata.get("document_type", "").casefold() == kind:
                evidence(kind, 0.60, "metadata_hint")
            if any(re.search(pattern, normalized(line)) for line in titles):
                evidence(kind, 0.94, "text_heading")
        if image and "site_photo" in scores:
            evidence("site_photo", 0.96, "image_format")
        # BOQ tables and drawing title blocks provide evidence even without a labelled title.
        text = normalized(document.extracted_text[:12000])
        if all(
            re.search(rf"\b{word}\b", text) for word in ("description", "quantity", "unit", "rate")
        ):
            evidence("boq", 0.93, "boq_columns")
        if re.search(r"\bdrawing\s*(?:no|number)\b", text) and re.search(
            r"\b(?:scale|revision|rev)\b", text
        ):
            evidence("drawing", 0.95, "drawing_title_block")
        if not scores:
            return Classification(
                document_type="other",
                confidence=0.25,
                reasoning="No decisive filename, metadata or text signature was found.",
                model_or_rule_used=f"{RULE_VERSION}:inconclusive",
            )
        ranked = sorted(scores, key=lambda kind: (-scores[kind], kind))
        winner = ranked[0]
        score = min(0.99, scores[winner] + (0.03 if len(signals[winner]) > 1 else 0))
        runner_up = scores[ranked[1]] if len(ranked) > 1 else 0
        if score < self.rule_threshold or score - runner_up < self.margin:
            return Classification(
                document_type="other",
                confidence=0.40,
                reasoning="Rule evidence is weak or conflicts across candidate types.",
                model_or_rule_used=f"{RULE_VERSION}:inconclusive",
            )
        return Classification(
            document_type=winner,
            confidence=score,
            reasoning=f"Matched {winner} signatures from: {', '.join(sorted(signals[winner]))}.",
            model_or_rule_used=f"{RULE_VERSION}:{winner}",
        )

    def classify(self, document: ClassificationInput) -> Classification:
        document = ClassificationInput.model_validate(document)
        result = self.rules(document)
        if result.model_or_rule_used.endswith(":inconclusive") and self.fallback is not None:
            return Classification.model_validate(self.fallback(document))
        return result
