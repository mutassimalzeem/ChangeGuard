"""No SQL, network clients, arbitrary execution or approval capability in this loop."""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from app.ai.gateway.types import GatewayError, GatewayUnavailableError
from app.ai.investigation.schemas import WRITE_TOOLS, AgentStep, EvidenceRef

log = structlog.get_logger(__name__)


def digest(value):
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True).encode()).hexdigest()


@dataclass
class Observation:
    evidence: list[EvidenceRef] = field(default_factory=list)
    facts: list[tuple[str, str, int]] = field(default_factory=list)
    # Facts are (server-generated comparison key, recorded value, evidence index).
    result: dict = field(default_factory=dict)


class EvidenceLedger:
    def __init__(self):
        self.items, self.keys, self.facts, self.conflicts = {}, {}, {}, set()

    def observe(self, observation):
        labels = []
        for evidence in observation.evidence:
            evidence = EvidenceRef.model_validate(evidence)
            key = (evidence.source_type, evidence.source_id, evidence.excerpt)
            if key not in self.keys:
                if len(self.items) >= 64:
                    raise ValueError("Evidence budget exhausted")
                label = f"E{len(self.items) + 1}"
                self.keys[key] = label
                self.items[label] = evidence
            labels.append(self.keys[key])
        for key, value, index in observation.facts:
            label = labels[index]
            for previous, previous_label in self.facts.get(key, []):
                if previous != value:
                    self.conflicts.add(tuple(sorted([previous_label, label])))
            self.facts.setdefault(key, []).append((value, label))
        return labels

    def selected(self, labels):
        if not labels or any(label not in self.items for label in labels):
            raise ValueError("Unobserved evidence cannot authorize an action")
        return [self.items[label] for label in dict.fromkeys(labels)]

    def conclusions(self, proposed):
        if self.conflicts:
            return [
                {
                    "kind": "conflict",
                    "recommended_action": "request_human_review",
                    "evidence_links": [self.items[label].model_dump(mode="json") for label in pair],
                    "summary": "Recorded facts conflict. Human review must resolve both sources.",
                }
                for pair in sorted(self.conflicts)
            ]
        result = []
        covered = set()
        for item in proposed:
            if item.kind == "conflict" and (
                len({c.evidence_id for c in item.citations}) < 2
                or item.recommended_action != "request_human_review"
            ):
                raise ValueError("Conflicts require both sources and human review")
            for citation in item.citations:
                evidence = self.items.get(citation.evidence_id)
                if evidence is None or citation.quote not in evidence.excerpt:
                    raise ValueError("Conclusion is not grounded in observed evidence")
                covered.add(citation.evidence_id)
            result.append(
                {
                    "kind": item.kind,
                    "recommended_action": item.recommended_action,
                    "summary": "Source quotations require human interpretation.",
                    "evidence_links": [
                        self.items[c.evidence_id]
                        .model_copy(update={"excerpt": c.quote})
                        .model_dump(mode="json")
                        for c in item.citations
                    ],
                }
            )
        if proposed and covered != set(self.items):
            return [
                {
                    "kind": "insufficient_evidence",
                    "recommended_action": "request_human_review",
                    "summary": "Review all observed sources; the recommendation omitted evidence.",
                    "evidence_links": [ref.model_dump(mode="json") for ref in self.items.values()],
                }
            ]
        return result


class Trace:
    """Log every event with content digests, never raw documents/provider output."""

    def __init__(self, tenant_id, project_id, user_id, request_id=None, run_id=None, emit=None):
        self.run_id = run_id or uuid4()
        self.context = dict(
            run_id=str(self.run_id),
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            user_id=str(user_id),
            request_id=request_id,
        )
        self.events = []
        self.emit = emit or log.info

    def record(self, event, *, payload=None, **metadata):
        item = {
            **self.context,
            "sequence": len(self.events) + 1,
            "event_type": event,
            "timestamp": datetime.now(UTC).isoformat(),
            "payload_hash": digest(payload),
            **metadata,
        }
        self.events.append(item)
        self.emit("investigation_trace", **item)


class InvestigationAgent:
    def __init__(self, planner, tools, trace):
        self.planner, self.tools, self.trace = planner, tools, trace

    async def run(
        self, question, seed, *, eligible, max_tool_depth=6, max_seconds=20, absolute_deadline=None
    ):
        if (
            type(max_tool_depth) is not int
            or not 1 <= max_tool_depth <= 12
            or not 0 < max_seconds <= 60
        ):
            raise ValueError("Invalid investigation budget")
        ledger = EvidenceLedger()
        ledger.observe(seed)
        self.trace.record(
            "observation",
            payload={
                "result": seed.result,
                "facts": seed.facts,
                "evidence": [e.model_dump(mode="json") for e in seed.evidence],
            },
            evidence_ids=list(ledger.items),
            outcome="initial_evidence",
        )
        conclusions, action, calls = [], None, 0
        status = "not_required" if not eligible else "completed"
        if not ledger.items:
            eligible = False
            status = "insufficient_evidence"
        deadline = asyncio.get_running_loop().time() + max_seconds
        if absolute_deadline is not None:
            deadline = min(deadline, absolute_deadline)
        try:
            if eligible:
                async with asyncio.timeout_at(deadline):
                    while True:
                        if ledger.conflicts:
                            conclusions = ledger.conclusions([])
                            status = "conflict"
                            break
                        raw = await self.planner.next_step(
                            question, ledger, deadline - asyncio.get_running_loop().time()
                        )
                        self.trace.record(
                            "model_step",
                            payload=raw.model_dump(mode="json")
                            if hasattr(raw, "model_dump")
                            else raw,
                            outcome="received",
                        )
                        try:
                            step = AgentStep.model_validate(raw)
                        except ValueError:
                            rejected = (
                                raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
                            )
                            if isinstance(rejected, dict) and rejected.get("tool_call"):
                                self.trace.record(
                                    "tool_call",
                                    payload=rejected["tool_call"],
                                    tool="unrecognized_or_invalid",
                                    depth=calls + 1,
                                )
                                self.trace.record(
                                    "observation",
                                    payload=None,
                                    tool="unrecognized_or_invalid",
                                    outcome="policy_denied",
                                    evidence_ids=[],
                                )
                            raise
                        if step.tool_call is None:
                            conclusions = ledger.conclusions(step.conclusions)
                            break
                        call = step.tool_call
                        self.trace.record(
                            "tool_call",
                            payload=call.model_dump(mode="json"),
                            tool=call.name,
                            depth=calls + 1,
                        )
                        if calls >= max_tool_depth:
                            self.trace.record(
                                "observation",
                                payload=None,
                                tool=call.name,
                                outcome="depth_limit",
                                evidence_ids=[],
                            )
                            status = "depth_limit"
                            break
                        calls += 1
                        if call.name == "create_draft_change_order" and ledger.conflicts:
                            self.trace.record(
                                "observation",
                                payload=None,
                                tool=call.name,
                                outcome="conflict_blocks_draft",
                                evidence_ids=[],
                            )
                            status = "conflict"
                            break
                        try:
                            observation = await self.tools.execute(call, ledger, deadline)
                        except asyncio.CancelledError:
                            self.trace.record(
                                "observation",
                                payload=None,
                                tool=call.name,
                                outcome="cancelled",
                                evidence_ids=[],
                            )
                            raise
                        except Exception:
                            self.trace.record(
                                "observation",
                                payload=None,
                                tool=call.name,
                                outcome="denied_or_failed",
                                evidence_ids=[],
                            )
                            status = "blocked"
                            break
                        try:
                            labels = ledger.observe(observation)
                        except ValueError:
                            self.trace.record(
                                "observation",
                                payload={
                                    "result": observation.result,
                                    "facts": observation.facts,
                                    "evidence": [
                                        e.model_dump(mode="json") for e in observation.evidence
                                    ],
                                },
                                tool=call.name,
                                outcome="evidence_limit",
                                evidence_ids=[],
                            )
                            status = "evidence_limit"
                            break
                        self.trace.record(
                            "observation",
                            payload={
                                "result": observation.result,
                                "facts": observation.facts,
                                "evidence": [
                                    e.model_dump(mode="json") for e in observation.evidence
                                ],
                            },
                            tool=call.name,
                            outcome="ok",
                            evidence_ids=labels,
                            resource_id=observation.result.get("change_order_id")
                            or observation.result.get("review_task_id"),
                        )
                        if call.name in WRITE_TOOLS:
                            refs = ledger.selected(call.arguments.evidence_ids)
                            action = observation.result
                            conclusions = [
                                {
                                    "kind": "supported",
                                    "summary": "Human review required for this draft or task.",
                                    "recommended_action": call.name,
                                    "evidence_links": [r.model_dump(mode="json") for r in refs],
                                }
                            ]
                            break
            if ledger.conflicts:
                conclusions = ledger.conclusions([])
                status = "conflict"
        except TimeoutError:
            status = "time_limit"
        except asyncio.CancelledError:
            self.trace.record(
                "final_recommendation", payload=None, outcome="cancelled", tool_calls=calls
            )
            raise
        except GatewayUnavailableError:
            self.trace.record("model_failure", outcome="unavailable")
            status = "model_unavailable"
        except GatewayError:
            self.trace.record("model_failure", outcome="provider_error")
            status = "model_failed"
        except Exception:
            self.trace.record("policy_rejection", payload=None, outcome="invalid_model_output")
            status = "invalid_model_output"
        if not conclusions and ledger.items:
            conclusions = ledger.conclusions([]) or [
                {
                    "kind": "insufficient_evidence" if eligible else "supported",
                    "summary": "Human review required."
                    if eligible
                    else "Deterministic rules do not require investigation.",
                    "recommended_action": "request_human_review" if eligible else "no_action",
                    "evidence_links": [
                        ref.model_dump(mode="json") for ref in ledger.items.values()
                    ],
                }
            ]
        result = {
            "run_id": str(self.trace.run_id),
            "status": status,
            "tool_calls": calls,
            "conclusions": conclusions,
            "action": action,
            "human_review_required": eligible or bool(ledger.conflicts) or not bool(ledger.items),
        }
        self.trace.record(
            "final_recommendation",
            payload=result,
            outcome=status,
            tool_calls=calls,
            recommendation="human_review" if eligible else "deterministic_only",
            conclusion_kinds=sorted({c["kind"] for c in conclusions}),
            recommended_actions=sorted({c["recommended_action"] for c in conclusions}),
        )
        return {**result, "trace": self.trace.events}
