# ChangeGuard — Architecture Decision Records

**Version:** 0.1  
**Date:** October 27, 2026  
**Status:** Living document  

This file records important technical and product decisions, the alternatives considered, and the consequences of each choice.

Use this format:

```text
## ADR-001 — Title
- Status:
- Date:
- Context:
- Decision:
- Alternatives:
- Consequences:
- Revisit when:
```

---

## ADR-001 — Build a vertical construction product, not a generic AI assistant

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Generic RAG chatbots, research agents, and business copilots are crowded and increasingly commoditized. The builder needs a defensible portfolio product and a commercially viable system.  
- **Decision:** Build ChangeGuard, a change-order and project-risk intelligence platform for mid-sized construction contractors.  
- **Alternatives:** Generic operations intelligence, autonomous research engine, freight document reconciliation, procurement risk agent, tender-analysis system.  
- **Consequences:** The product requires construction-domain modeling and access to real project data. In exchange, it has a clearer buyer, measurable pain, and stronger differentiation.  
- **Revisit when:** Pilot interviews show that another vertical has stronger willingness to pay or easier data access.

---

## ADR-002 — Start with a modular monolith

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** The system is initially built by one developer and must ship quickly.  
- **Decision:** Use one deployable backend with clear internal modules: API, ingestion, processing, domain, retrieval, AI, workflow, policy, evaluation, and observability.  
- **Alternatives:** Microservices, serverless functions, monolithic Django app.  
- **Consequences:** Faster iteration and easier debugging. Module boundaries must be enforced to allow later service extraction.  
- **Revisit when:** Different components require independent scaling or separate deployment cadences.

---

## ADR-003 — PostgreSQL is the primary system of record

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** The product needs relational integrity, transactional workflows, auditability, and structured domain data.  
- **Decision:** Use PostgreSQL for projects, users, documents, change orders, approvals, risks, events, evidence links, and audit records.  
- **Alternatives:** MongoDB, DynamoDB, graph database as primary store.  
- **Consequences:** Strong consistency and relational querying. Graph-style questions may require additional indexing or a future graph layer.  
- **Revisit when:** Relationship traversal becomes a major performance bottleneck.

---

## ADR-004 — Use hybrid retrieval, not vector-only search

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Construction data contains exact identifiers—drawing numbers, BOQ codes, clause numbers, CO numbers—and semantic language.  
- **Decision:** Use PostgreSQL full-text search plus pgvector semantic search, metadata filters, and reranking.  
- **Alternatives:** Vector-only retrieval, external search engine, graph-only retrieval.  
- **Consequences:** Better handling of exact identifiers and semantic questions. More moving parts than vector-only search.  
- **Revisit when:** Retrieval quality plateaus or query volume requires dedicated infrastructure.

---

## ADR-005 — LLMs do not calculate money or deadlines

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Financial exposure and approval deadlines must be reliable and auditable.  
- **Decision:** All cost aggregation, currency handling, schedule calculations, deadline checks, and exposure totals are implemented in deterministic Python/SQL.  
- **Alternatives:** Let LLM calculate values, use spreadsheet-style calculations inside prompts.  
- **Consequences:** More reliable and testable outputs. LLM output is limited to interpretation, extraction, classification, drafting, and explanation.  
- **Revisit when:** Never for financial or contractual calculations.

---

## ADR-006 — Every AI conclusion requires evidence

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** The product must be usable in commercial and dispute-sensitive contexts.  
- **Decision:** Every factual AI claim must include an evidence link. If evidence is insufficient, the system must return `insufficient_evidence`.  
- **Alternatives:** Allow uncited answers with disclaimers.  
- **Consequences:** Lower apparent answer rate but higher trust. Requires citation-aware retrieval and evaluation.  
- **Revisit when:** Never for risk, financial, contractual, or approval-related conclusions.

---

## ADR-007 — Human approval gates protect consequential actions

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Change orders, claims, client communication, and approvals affect money and contractual relationships.  
- **Decision:** AI may detect, classify, retrieve, and draft. Humans must approve consequential actions.  
- **Alternatives:** Fully autonomous agent workflow.  
- **Consequences:** Safer adoption and clearer accountability. Adds workflow complexity.  
- **Revisit when:** A workflow has enough evaluation evidence and contractual clarity to allow controlled autonomy.

---

## ADR-008 — Use background workers for document processing

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** OCR, extraction, embedding, and investigation can take seconds to minutes.  
- **Decision:** Use Celery with Redis for asynchronous processing.  
- **Alternatives:** Synchronous API processing, serverless queues, Temporal.  
- **Consequences:** Better UX and reliability. Requires job monitoring, retries, idempotency, and dead-letter handling.  
- **Revisit when:** Workflows require long-running, multi-day, or highly stateful orchestration.

---

## ADR-009 — Use a model gateway

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Model providers, pricing, capabilities, and policies will change.  
- **Decision:** Route all LLM calls through an internal model gateway with task-specific configuration, logging, retries, cost tracking, and fallbacks.  
- **Alternatives:** Direct provider SDK calls throughout the codebase.  
- **Consequences:** Easier model switching, evaluation, and cost control. Adds a small abstraction layer.  
- **Revisit when:** Never remove the gateway; expand it as providers increase.

---

## ADR-010 — Start with manual upload before deep integrations

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Integrations are valuable but slow, permission-heavy, and customer-specific.  
- **Decision:** MVP begins with manual upload, email forwarding, and bulk ZIP ingestion. Deep ERP, Procore, Autodesk, or accounting integrations come later.  
- **Alternatives:** Build ERP integration first.  
- **Consequences:** Faster validation and pilot onboarding. Some manual work remains for customers.  
- **Revisit when:** Three or more pilot customers request the same integration.

---

## ADR-011 — Use confidence thresholds and review queues

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** OCR, scanned documents, handwritten notes, and inconsistent terminology will produce errors.  
- **Decision:** Every extraction has a confidence score. Low-confidence or high-impact outputs enter a human-review queue.  
- **Alternatives:** Fully automatic processing, manual review of everything.  
- **Consequences:** Improves trust and data quality. Requires workflow UI and reviewer accountability.  
- **Revisit when:** Confidence calibration and extraction accuracy improve substantially.

---

## ADR-012 — Evidence links are first-class domain objects

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** A change-order claim is only useful if it can be traced to source documents and events.  
- **Decision:** Model `EvidenceLink` as a first-class entity connecting claims, risks, events, and change orders to documents, chunks, images, and database records.  
- **Alternatives:** Store citations only as text in AI responses.  
- **Consequences:** Enables audit, dispute support, retrieval evaluation, and trust. Requires disciplined ingestion metadata.  
- **Revisit when:** Never; this is a core product principle.

---

## ADR-013 — Use evaluation as a release gate

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** AI behavior changes when prompts, models, retrieval settings, or tools change.  
- **Decision:** Maintain golden datasets and automated evaluation. Prompt, model, retrieval, and tool changes must pass evaluation before release.  
- **Alternatives:** Manual spot-checking only.  
- **Consequences:** Slower iteration but much higher reliability.  
- **Revisit when:** Evaluation coverage becomes a bottleneck; expand automation rather than remove gates.

---

## ADR-014 — Build for Bangladesh first, design for international expansion

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** The builder has local market access and can conduct pilot interviews more easily.  
- **Decision:** Validate with Bangladeshi mid-sized contractors first, but avoid hard-coding local assumptions into the core domain model.  
- **Alternatives:** Build only for local market; build globally from day one.  
- **Consequences:** Faster pilot access. Currency, language, tax, regulatory, and document conventions must remain configurable.  
- **Revisit when:** First international pilot opportunity appears.

---

## ADR-015 — Do not build a generic agent framework

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Agent frameworks are useful, but the product value comes from domain workflow and evidence reliability.  
- **Decision:** Use a simple deterministic workflow engine first. Introduce LangGraph or another agent framework only for bounded investigation tasks.  
- **Alternatives:** Build a general multi-agent system from the start.  
- **Consequences:** Higher reliability and easier debugging. Less flexibility for open-ended exploration.  
- **Revisit when:** Multiple complex investigation workflows justify shared orchestration.

---

## ADR-016 — Keep the original document immutable

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Disputes require trustworthy evidence.  
- **Decision:** Uploaded originals are immutable. Corrections apply to extracted metadata and derived records, never to the original file.  
- **Alternatives:** Allow file replacement or editing.  
- **Consequences:** Strong evidence integrity. Requires explicit versioning for corrected or replacement documents.  
- **Revisit when:** Never for original evidence files.

---

## ADR-017 — Ship a pilot before building advanced features

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** The biggest risk is building a sophisticated system nobody wants.  
- **Decision:** Secure 2–3 pilot commitments before building advanced AI reasoning, integrations, or multi-project analytics.  
- **Alternatives:** Build the full product first, then sell.  
- **Consequences:** The MVP may feel less impressive technically, but it produces real validation and case-study material.  
- **Revisit when:** Pilot commitments are secured and real workflows are understood.

---

## ADR-018 — Use synthetic data for development, real data for validation

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Real construction data is sensitive and may not be available immediately.  
- **Decision:** Build with realistic synthetic fixtures. Use anonymized or permissioned real documents only in staging and pilot environments.  
- **Alternatives:** Use real customer data in development.  
- **Consequences:** Safer development. Synthetic data must be realistic enough to expose real failures.  
- **Revisit when:** A secure data-sharing agreement and anonymization process exist.

---

## ADR-019 — Prefer boring, observable infrastructure

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** The product must be reliable and maintainable by a small team.  
- **Decision:** Use FastAPI, PostgreSQL, Redis, Celery, Docker, structured logs, and OpenTelemetry. Avoid exotic infrastructure in the MVP.  
- **Alternatives:** Kubernetes from day one, complex event streaming, multi-cloud deployment.  
- **Consequences:** Faster delivery and easier debugging. May require migration later at scale.  
- **Revisit when:** Operational scale or customer requirements demand it.

---

## ADR-020 — The product sells workflow outcomes, not AI features

- **Status:** Accepted  
- **Date:** 2026-10-27  
- **Context:** Customers do not buy “RAG” or “agents”; they buy fewer missed changes, faster approvals, and stronger claim evidence.  
- **Decision:** Position ChangeGuard around measurable outcomes: reduced approval delay, improved evidence completeness, earlier risk detection, and reduced dispute exposure.  
- **Alternatives:** Sell AI features or token-based access.  
- **Consequences:** Requires pilot metrics and case studies. Creates stronger pricing power.  
- **Revisit when:** Customer feedback reveals a different primary buying criterion.
