"""Strict typed facts. Missing facts are explicit records, never guessed defaults."""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, ClassVar, Generic, Literal, TypeVar

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    WithJsonSchema,
    model_validator,
)


def decimal_text(value):
    if isinstance(value, Decimal):
        value = format(value, "f")
    if not isinstance(value, str) or not re.fullmatch(
        r"-?(?:0|[1-9]\d{0,14})(?:\.\d{1,6})?", value
    ):
        raise ValueError("Decimal values must be finite plain decimal strings")
    return Decimal(value)


DecimalValue = Annotated[
    Decimal,
    BeforeValidator(decimal_text),
    WithJsonSchema({"type": "string", "pattern": r"^-?(?:0|[1-9]\d{0,14})(?:\.\d{1,6})?$"}),
]


def iso_date(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Dates must be ISO 8601 YYYY-MM-DD")
    date.fromisoformat(value)
    return value


ISODate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(iso_date)]


def email_address(value):
    try:
        validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError("Invalid email address syntax") from exc
    return value


EmailAddress = Annotated[
    str, AfterValidator(email_address), WithJsonSchema({"type": "string", "format": "email"})
]
Text = Annotated[str, Field(min_length=1, max_length=10000)]
ReferenceCode = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,99}$")]
Currency = Literal[
    "USD",
    "EUR",
    "GBP",
    "BDT",
    "INR",
    "AED",
    "SAR",
    "QAR",
    "AUD",
    "CAD",
    "SGD",
    "HKD",
    "JPY",
    "CNY",
    "CHF",
    "NZD",
    "NOK",
    "SEK",
    "DKK",
    "ZAR",
    "KWD",
    "OMR",
    "BHD",
    "MYR",
    "IDR",
    "THB",
    "VND",
    "PKR",
    "LKR",
    "KRW",
]
Unit = Literal["m", "m2", "m3", "mm", "cm", "km", "kg", "t", "l", "each", "h", "day", "set", "%"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Money(StrictModel):
    amount: DecimalValue
    currency: Currency


class Quantity(StrictModel):
    amount: DecimalValue
    unit: Unit


class DocumentReference(StrictModel):
    kind: Literal["contract", "boq", "drawing", "rfi", "change_order", "quotation"]
    reference: ReferenceCode


T = TypeVar("T")


class ExtractedField(StrictModel, Generic[T]):
    value: T | None
    confidence: float = Field(ge=0, le=1)
    source_page: int | None = Field(ge=1)
    source_text_snippet: str | None = Field(min_length=1, max_length=2000)
    missing: bool

    @model_validator(mode="after")
    def consistent_missing(self):
        if self.missing:
            if (
                self.value is not None
                or self.confidence != 0
                or self.source_page is not None
                or self.source_text_snippet is not None
            ):
                raise ValueError("Missing facts require null value/evidence and zero confidence")
        elif self.value is None or not self.source_text_snippet:
            raise ValueError("Present facts require a value and source quotation")
        return self


class DocumentFacts(StrictModel):
    required_facts: ClassVar[tuple[str, ...]] = ()


class Contract(DocumentFacts):
    required_facts = ("reference", "title", "employer", "contractor")
    reference: ExtractedField[ReferenceCode]
    title: ExtractedField[Text]
    employer: ExtractedField[Text]
    contractor: ExtractedField[Text]
    effective_date: ExtractedField[ISODate]
    expiry_date: ExtractedField[ISODate]
    contract_value: ExtractedField[Money]
    status: ExtractedField[Literal["draft", "tender", "signed", "active", "expired", "terminated"]]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class BOQItem(DocumentFacts):
    required_facts = ("code", "description", "quantity")
    code: ExtractedField[ReferenceCode]
    description: ExtractedField[Text]
    quantity: ExtractedField[Quantity]
    unit_rate: ExtractedField[Money]
    stated_total: ExtractedField[Money]
    status: ExtractedField[Literal["planned", "measured", "approved"]]


class BOQ(DocumentFacts):
    required_facts = ("title", "items")
    title: ExtractedField[Text]
    items: list[BOQItem] = Field(max_length=300)
    stated_total: ExtractedField[Money]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class Drawing(DocumentFacts):
    required_facts = ("drawing_number", "title", "revision")
    drawing_number: ExtractedField[ReferenceCode]
    title: ExtractedField[Text]
    revision: ExtractedField[ReferenceCode]
    issue_date: ExtractedField[ISODate]
    scale: ExtractedField[Text]
    status: ExtractedField[
        Literal["draft", "issued_for_review", "issued_for_construction", "as_built", "superseded"]
    ]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class RFI(DocumentFacts):
    required_facts = ("rfi_number", "subject", "question")
    rfi_number: ExtractedField[ReferenceCode]
    subject: ExtractedField[Text]
    question: ExtractedField[Text]
    response: ExtractedField[Text]
    raised_date: ExtractedField[ISODate]
    due_date: ExtractedField[ISODate]
    status: ExtractedField[Literal["open", "answered", "closed"]]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class ChangeOrder(DocumentFacts):
    required_facts = ("co_number", "title", "description")
    co_number: ExtractedField[ReferenceCode]
    title: ExtractedField[Text]
    description: ExtractedField[Text]
    issue_date: ExtractedField[ISODate]
    amount: ExtractedField[Money]
    status: ExtractedField[Literal["draft", "submitted", "approved", "rejected", "executed"]]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class DailyReport(DocumentFacts):
    required_facts = ("report_date", "activities")
    report_date: ExtractedField[ISODate]
    title: ExtractedField[Text]
    weather: ExtractedField[Text]
    activities: ExtractedField[Text]
    labour_quantity: ExtractedField[Quantity]
    status: ExtractedField[Literal["draft", "submitted", "approved"]]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class Email(DocumentFacts):
    required_facts = ("subject", "sender", "body")
    subject: ExtractedField[Text]
    sender: ExtractedField[EmailAddress]
    recipient: ExtractedField[EmailAddress]
    sent_date: ExtractedField[ISODate]
    body: ExtractedField[Text]
    status: ExtractedField[Literal["draft", "sent", "received"]]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class Quotation(DocumentFacts):
    required_facts = ("reference", "supplier", "issue_date")
    reference: ExtractedField[ReferenceCode]
    supplier: ExtractedField[Text]
    issue_date: ExtractedField[ISODate]
    valid_until: ExtractedField[ISODate]
    items: list[BOQItem] = Field(max_length=300)
    stated_total: ExtractedField[Money]
    status: ExtractedField[Literal["draft", "submitted", "accepted", "rejected", "expired"]]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


class Other(DocumentFacts):
    required_facts = ("title",)
    title: ExtractedField[Text]
    description: ExtractedField[Text]
    document_references: list[ExtractedField[DocumentReference]] = Field(max_length=100)


SCHEMAS = {
    "contract": Contract,
    "boq": BOQ,
    "drawing": Drawing,
    "rfi": RFI,
    "change_order": ChangeOrder,
    "daily_report": DailyReport,
    "email": Email,
    "quotation": Quotation,
    "other": Other,
}


def schema_for(document_type):
    # Historical classifier labels remain readable/resumable without relabelling documents.
    return SCHEMAS.get(
        {"invoice": "other", "correspondence": "email"}.get(document_type, document_type)
    )
