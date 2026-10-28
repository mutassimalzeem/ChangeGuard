"""Validate quotations against actual source blocks, not model assertions."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

from app.document_processing.extraction.types import ExtractionResult
from app.document_processing.structured.schemas import (
    DocumentFacts,
    DocumentReference,
    ExtractedField,
    Money,
    Quantity,
)


class EvidenceError(ValueError):
    """A field cannot be verified in its claimed source location."""


def normalize(text):
    return " ".join(text.casefold().split())


def source_units(source: ExtractionResult):
    groups = {}
    for block in source.blocks:
        key = (
            block.page_number,
            block.location.get("archive_member"),
            block.location.get("mime_path"),
            block.location.get("thread_index"),
        )
        group = groups.setdefault(key, {"page": block.page_number, "metadata": [], "text": []})
        metadata = []
        for key in ("section", "author", "date", "revision"):
            value = getattr(block, key)
            if value is not None:
                metadata.append(f"{key}: {value}")
        headers = block.location.get("headers")
        if headers:
            metadata.append("columns: " + " | ".join(str(v) for v in headers))
        for value in metadata:
            if value not in group["metadata"]:
                group["metadata"].append(value)
        group["text"].append(block.text)
    return [
        {"page": group["page"], "text": "\n".join(group["metadata"] + group["text"])}
        for group in groups.values()
    ]


def fields(value, path=""):
    if isinstance(value, ExtractedField):
        yield path, value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from fields(getattr(value, name), f"{path}.{name}".lstrip("."))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from fields(item, f"{path}[{index}]")


def missing_required(value: DocumentFacts, path=""):
    missing = []
    for name in value.required_facts:
        fact = getattr(value, name)
        if (isinstance(fact, ExtractedField) and fact.missing) or (
            isinstance(fact, list) and not fact
        ):
            missing.append(f"{path}.{name}".lstrip("."))
    for name in type(value).model_fields:
        nested = getattr(value, name)
        if isinstance(nested, list):
            for index, item in enumerate(nested):
                if isinstance(item, DocumentFacts):
                    missing.extend(missing_required(item, f"{path}.{name}[{index}]".lstrip(".")))
    return missing


def has_decimal(value: Decimal, text: str):
    for token in re.findall(r"(?<![\w.,])[+-]?\d[\d,]*(?:\.\d+)?(?![\w,]|\.(?:\d|\.))", text):
        # Only permit conventional thousands grouping, never arithmetic/exponents.
        if "," in token and not re.fullmatch(r"[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?", token):
            continue
        try:
            if Decimal(token.replace(",", "")) == value:
                return True
        except InvalidOperation:
            pass
    return False


def paired_decimal(amount, markers, text):
    token = r"([+-]?\d[\d,]*(?:\.\d+)?)"
    for marker in markers:
        for pattern in (
            rf"(?<!\w){re.escape(marker)}\s*{token}(?![\w,]|\.(?:\d|\.))",
            rf"(?<![\w.,]){token}\s*{re.escape(marker)}(?!\w)",
        ):
            if any(has_decimal(amount, match) for match in re.findall(pattern, text, re.I)):
                return True
    return False


def has_money(value, text):
    aliases = {"USD": ("USD", "US$"), "EUR": ("EUR", "€"), "GBP": ("GBP", "£"), "BDT": ("BDT", "৳")}
    return paired_decimal(value.amount, aliases.get(value.currency, (value.currency,)), text)


def has_quantity(value, text):
    aliases = {
        "m2": ("m2", "m²", "m^2"),
        "m3": ("m3", "m³", "m^3"),
        "each": ("each", "ea", "pcs", "nos"),
        "h": ("h", "hour", "hours"),
        "day": ("day", "days"),
        "set": ("set", "sets"),
        "l": ("l", "litre", "litres"),
    }
    return paired_decimal(value.amount, aliases.get(value.unit, (value.unit,)), text)


def has_date(value, text):
    if re.search(rf"(?<!\d){re.escape(value)}(?!\d)", text):
        return True
    for pattern, formats in (
        (r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", ("%d %B %Y", "%d %b %Y")),
        (r"\b[A-Za-z]+\s+\d{1,2},?\s+\d{4}\b", ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y")),
    ):
        for match in re.findall(pattern, text):
            for form in formats:
                try:
                    if datetime.strptime(match, form).date().isoformat() == value:
                        return True
                except ValueError:
                    pass
    return False


def validate_evidence(facts: DocumentFacts, source: ExtractionResult):
    units = source_units(source)
    normalized_units = [(u["page"], normalize(u["text"])) for u in units]
    for path, fact in fields(facts):
        if fact.missing:
            continue
        snippet = fact.source_text_snippet
        quotation = normalize(snippet)
        if not any(
            page == fact.source_page and quotation in text for page, text in normalized_units
        ):
            raise EvidenceError(f"{path}: quotation or page is not in the source")
        value = fact.value
        valid = False
        if isinstance(value, Money):
            valid = has_money(value, snippet)
            if path.endswith("stated_total"):
                # The label and number must share a source line; never multiply/sum items.
                valid = valid and any(
                    re.search(r"\btotal\b", line, re.I)
                    and not re.search(
                        r"[+*/]|\d\s*[-=]\s*(?:[A-Z]{3}\s*)?\d|\bsum\s*\(", line, re.I
                    )
                    and has_money(value, line)
                    for line in snippet.splitlines()
                )
        elif isinstance(value, Quantity):
            valid = has_quantity(value, snippet)
        elif isinstance(value, DocumentReference):
            valid = bool(re.search(rf"(?<!\w){re.escape(value.reference)}(?!\w)", snippet, re.I))
            hints = {
                "drawing": r"drawing|drg|dwg|dr",
                "boq": r"boq|bill of quantities",
                "rfi": r"rfi|request for information",
                "change_order": r"co|change order|variation order",
                "contract": r"contract|ct",
                "quotation": r"quotation|quote|q",
            }
            valid = valid and bool(re.search(rf"\b(?:{hints[value.kind]})\b", snippet, re.I))
        elif isinstance(value, str):
            if path.endswith("_date") or path.endswith("valid_until"):
                valid = has_date(value, snippet)
            elif path.rsplit(".", 1)[-1] in {
                "reference",
                "code",
                "drawing_number",
                "rfi_number",
                "co_number",
                "revision",
            }:
                valid = bool(re.search(rf"(?<!\w){re.escape(value)}(?!\w)", snippet, re.I))
            else:
                target = normalize(value.replace("_", " "))
                source_text = normalize(snippet.replace("_", " "))
                valid = target in source_text
                if path.endswith("status"):
                    valid = bool(re.search(rf"(?<!\w){re.escape(target)}(?!\w)", source_text))
                    if re.search(
                        rf"\b(?:not|never|not yet|no longer)\s+{re.escape(target)}\b", source_text
                    ):
                        valid = False
                if value in {"issued_for_construction", "issued_for_review", "as_built"}:
                    code = {
                        "issued_for_construction": "IFC",
                        "issued_for_review": "IFR",
                        "as_built": "as-built",
                    }[value]
                    valid = valid or bool(re.search(rf"\b{re.escape(code)}\b", snippet, re.I))
                    if re.search(
                        rf"\b(?:not|never|not yet|no longer)\s+{re.escape(code)}\b", snippet, re.I
                    ):
                        valid = False
                    if re.search(
                        rf"\b(?:not|never|not yet|no longer)\s+{re.escape(target)}\b", source_text
                    ):
                        valid = False
        if not valid:
            raise EvidenceError(f"{path}: value is not supported by its source quotation")
    return facts
