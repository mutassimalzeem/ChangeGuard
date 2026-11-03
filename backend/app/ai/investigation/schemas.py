"""Closed schemas. No tenant selectors, SQL, approval or financial write fields."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class SearchArgs(Closed):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=4, ge=1, le=8)


class RecordArgs(Closed):
    record_id: UUID


class TimelineArgs(Closed):
    limit: int = Field(default=8, ge=1, le=8)


class ActionArgs(Closed):
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


READ_TOOLS = {
    "search_project_documents": SearchArgs,
    "get_document_chunk": RecordArgs,
    "get_contract_clause": RecordArgs,
    "get_boq_item": RecordArgs,
    "get_change_order": RecordArgs,
    "get_approval_history": RecordArgs,
    "get_project_timeline": TimelineArgs,
    "find_similar_past_cases": SearchArgs,
}
WRITE_TOOLS = {"create_draft_change_order": ActionArgs, "request_human_review": ActionArgs}
TOOL_ARGUMENTS = READ_TOOLS | WRITE_TOOLS
ToolName = Literal[
    "search_project_documents",
    "get_document_chunk",
    "get_contract_clause",
    "get_boq_item",
    "get_change_order",
    "get_approval_history",
    "get_project_timeline",
    "find_similar_past_cases",
    "create_draft_change_order",
    "request_human_review",
]


class ToolCall(Closed):
    name: ToolName
    arguments: SearchArgs | RecordArgs | TimelineArgs | ActionArgs

    @model_validator(mode="after")
    def correct_arguments(self):
        self.arguments = TOOL_ARGUMENTS[self.name].model_validate(self.arguments.model_dump())
        return self


class Citation(Closed):
    evidence_id: str = Field(min_length=1, max_length=20)
    quote: str = Field(min_length=8, max_length=2000)


class Conclusion(Closed):
    kind: Literal["supported", "conflict", "insufficient_evidence"]
    citations: list[Citation] = Field(min_length=1, max_length=8)
    recommended_action: Literal["no_action", "request_human_review"]


class AgentStep(Closed):
    tool_call: ToolCall | None
    conclusions: list[Conclusion] = Field(max_length=8)

    @model_validator(mode="after")
    def one_operation(self):
        if (self.tool_call is None) == (not self.conclusions):
            raise ValueError("Return one tool call or evidenced conclusions")
        return self


class EvidenceRef(Closed):
    source_type: Literal[
        "document",
        "document_chunk",
        "contract_clause",
        "boq_item",
        "change_order",
        "approval",
        "project_event",
    ]
    source_id: UUID
    source_page: int | None = Field(default=None, ge=1)
    excerpt: str = Field(min_length=1, max_length=2000)


class InvestigationRequest(Closed):
    document_id: UUID
    question: str = Field(min_length=1, max_length=500)
    max_tool_depth: int = Field(default=6, ge=1, le=12)
    max_seconds: float = Field(default=20, gt=0, le=60, allow_inf_nan=False)


def tool_schemas():
    return [
        {"name": name, "read_only": name in READ_TOOLS, "parameters": schema.model_json_schema()}
        for name, schema in TOOL_ARGUMENTS.items()
    ]
