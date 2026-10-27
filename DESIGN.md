# ChangeGuard — Product and UX Design

**Version:** 0.1  
**Date:** October 27, 2026  
**Status:** MVP design guide  

---

## 1. Design philosophy

ChangeGuard is used by busy construction professionals. The interface must make it easy to:

- Upload evidence.
- Understand what the AI found.
- Verify why the system reached a conclusion.
- Take action quickly.
- Trust the system during disputes.

### Design principles

1. **Evidence first.** Every claim must be clickable and traceable.
2. **Human control.** AI proposes; humans approve.
3. **Operational clarity.** Show status, owner, deadline, money, and risk.
4. **Progressive disclosure.** Show the summary first; expose detail on demand.
5. **No black-box AI.** Always show confidence, evidence, and missing information.
6. **Mobile-friendly capture.** Site engineers must be able to upload photos and reports easily.

---

## 2. Primary users

| User | Main screen | Main job |
|---|---|---|
| Owner | Portfolio dashboard | Understand exposure and risk |
| Project manager | Project workspace | Manage changes and approvals |
| Commercial manager / QS | Change-order review | Validate cost and evidence |
| Site engineer | Mobile capture | Upload reports and photos |
| Document controller | Document library | Manage files and versions |

---

## 3. Information architecture

```text
ChangeGuard
|-- Portfolio
|   |-- Projects
|   |-- Exposure overview
|   |-- Alerts
|-- Project workspace
|   |-- Overview
|   |-- Documents
|   |-- Timeline
|   |-- Change orders
|   |-- Risks
|   |-- Approvals
|   |-- Ask ChangeGuard
|-- Review queue
|   |-- Low-confidence extractions
|   |-- Potential changes
|   |-- Approval requests
|-- Settings
|   |-- Team and roles
|   |-- Projects
|   |-- Integrations
|   |-- Audit log
|-- Audit
    |-- AI decisions
    |-- User actions
    |-- Evidence history
```

---

## 4. Key screens

### 4.1 Portfolio dashboard

**Purpose:** Give owners and managers a commercial overview.

Show:

- Active projects.
- Total pending change-order exposure.
- Overdue approvals.
- High and critical risks.
- Documents requiring review.
- Recent AI-detected events.
- Projects with rising risk.

### Layout

```text
+------------------------------------------------------+
| Portfolio overview                                    |
+--------------+--------------+--------------+----------+
| Active       | Pending      | Overdue      | High     |
| projects     | exposure     | approvals    | risks    |
+--------------+--------------+--------------+----------+
| Project risk table                                    |
| Project | Exposure | Open COs | Overdue | Risk        |
+------------------------------------------------------+
| Recent evidence events                                |
+------------------------------------------------------+
```

### Rules

- Money values must be calculated by backend logic, never by the LLM.
- Every number must be clickable to its source records.
- Show timestamp and data freshness.

---

### 4.2 Project workspace

**Purpose:** The operational home for one project.

Tabs:

1. Overview
2. Documents
3. Timeline
4. Change orders
5. Risks
6. Approvals
7. Ask ChangeGuard

### Overview tab

Show:

- Project name, client, contract value, dates.
- Pending exposure.
- Open change orders.
- Overdue approvals.
- Latest risks.
- Latest documents.
- Recent timeline events.

---

### 4.3 Document library

**Purpose:** Make evidence findable and trustworthy.

Show:

- Upload button.
- Filters: type, date, uploader, status, project area.
- Document cards with:
  - File name.
  - Type.
  - Upload date.
  - Version.
  - Processing status.
  - Confidence.
  - Extracted fields.
  - Linked entities.
  - Evidence references.

### Upload flow

1. Drag and drop files.
2. Select project and document type, if not auto-detected.
3. System shows processing progress.
4. System shows extracted fields.
5. User confirms or corrects fields.
6. System saves corrections as feedback.

---

### 4.4 Evidence timeline

**Purpose:** Show the chronological story of the project.

Each event should display:

- Date and time.
- Event type.
- Short description.
- Source document.
- Linked people, drawings, BOQ items, or change orders.
- Confidence.
- Evidence button.

Example:

```text
12 Aug 2026 — Potential delay detected
“Basement waterproofing delayed due to late material delivery.”

Evidence:
- Daily report — 12 Aug, page 2
- Site photo — IMG_2231
- Supplier email — 11 Aug
- Drawing S-103 Rev C

Linked:
- Change order CO-014
- Supplier: ABC Materials
- BOQ item: WP-012

Confidence: Medium
Missing evidence: Revised delivery schedule
```

---

### 4.5 Change-order workspace

**Purpose:** Manage a change from detection to approval.

### Change-order detail page

Show:

- Title and number.
- Status.
- Owner.
- Created date.
- Deadline.
- Cost impact.
- Schedule impact.
- Responsible party.
- Evidence package.
- AI draft.
- Human edits.
- Approval history.

### Status flow

```text
Potential
   |
   v
Under review
   |
   v
Drafted
   |
   v
Submitted
   |
   v
Approved / Rejected / Disputed
   |
   v
Closed
```

### Evidence package

The evidence package must show:

| Evidence | Source | Date | Relevance | Confidence |
|---|---|---|---|---|
| Site delay report | Daily report, 12 Aug | 12 Aug | Supports delay | High |
| Supplier delay email | Email thread | 11 Aug | Supports cause | Medium |
| Waterproofing drawing | S-103 Rev C | 02 Aug | Defines scope | Verified |
| Cost basis | BOQ item WP-012 | — | Supports cost | High |

---

### 4.6 Risk center

**Purpose:** Turn raw evidence into actionable operational risk.

Each risk card should show:

- Risk title.
- Severity.
- Financial exposure.
- Schedule impact.
- Responsible party.
- Evidence.
- Recommended action.
- Status.
- Owner.
- Human override option.

### Risk states

- `new`
- `under_review`
- `accepted`
- `dismissed`
- `converted_to_change_order`
- `resolved`

---

### 4.7 Review queue

**Purpose:** Prevent silent AI errors.

Queue categories:

- Low-confidence extraction.
- Missing required fields.
- Potential duplicate.
- Conflicting evidence.
- High-value change.
- High-severity risk.
- Approval request.

Each item must show:

- What the system found.
- Why it needs review.
- Evidence.
- Recommended correction.
- Approve / edit / reject controls.

---

### 4.8 Ask ChangeGuard

**Purpose:** Let users ask questions about project evidence.

This is **not** a general chatbot. It is a project-grounded assistant.

Example questions:

- “What is the current pending change-order exposure?”
- “Which approvals are overdue?”
- “What evidence supports the basement waterproofing delay?”
- “Which suppliers caused repeated delays?”
- “Summarize all change orders related to Level 3.”
- “What documents are missing for CO-014?”

### Required behavior

- Every factual answer must include citations.
- Financial calculations must come from backend logic.
- If evidence is insufficient, say so.
- Never invent clause numbers, dates, amounts, or approvals.
- Show retrieved sources beneath the answer.

---

## 5. AI interaction rules

### Show uncertainty

Use clear labels:

- Verified
- High confidence
- Medium confidence
- Low confidence
- Insufficient evidence

### Never present AI output as final

Use language such as:

- “Potential change detected.”
- “Suggested draft.”
- “Requires commercial review.”
- “Evidence suggests…”
- “Insufficient evidence to determine cause.”

### Always expose evidence

Every AI conclusion must have:

- Source document.
- Page or timestamp.
- Relevant excerpt or image region.
- Link to full source.
- Confidence.
- Missing evidence, if applicable.

---

## 6. Visual design direction

### Tone

Professional, calm, precise, operational.

Avoid:

- Gimmicky AI language.
- Excessive animations.
- Overly technical ML terminology.
- Claims of certainty.

### Color usage

| Color | Meaning |
|---|---|
| Neutral gray | Base interface |
| Blue | Informational and navigation |
| Amber | Review required |
| Red | Critical risk, overdue, financial exposure |
| Green | Approved, verified, resolved |
| Purple | AI-generated content |

### Typography

Use a clean, highly legible sans-serif system:

- Inter, IBM Plex Sans, or similar.
- Strong hierarchy for project names, money, deadlines, and status.
- Monospace for IDs, drawing numbers, BOQ codes, and file hashes.

---

## 7. Mobile capture experience

Site engineers need a fast flow.

### Capture flow

1. Open project.
2. Tap “Add site evidence.”
3. Choose: photo, daily report, voice note, or document.
4. Capture or upload.
5. Add optional note.
6. Submit.
7. System processes in background.
8. Engineer sees confirmation and later sees extracted result.

### Requirements

- Works on poor connectivity with queued upload.
- Compress images without destroying readability.
- Capture timestamp and GPS only with explicit consent.
- Allow offline draft saving.
- Show upload status clearly.

---

## 8. Empty, loading, and error states

### Empty states

Every empty state should explain the next action.

Example:

> “No change orders yet. Upload RFIs, daily reports, drawings, or emails, and ChangeGuard will identify potential scope, cost, or schedule changes.”

### Loading states

Show meaningful progress:

- “Extracting text…”
- “Classifying document…”
- “Linking to project records…”
- “Building evidence package…”

### Error states

Never show raw stack traces.

Example:

> “We could not process this PDF. The file may be scanned or corrupted. You can retry processing or upload a clearer version.”

---

## 9. Accessibility

Follow WCAG 2.2 AA where practical.

Requirements:

- Keyboard navigation.
- Visible focus states.
- Sufficient contrast.
- Descriptive alt text.
- Accessible tables.
- Clear form labels.
- No color-only status indicators.
- Screen-reader-friendly evidence links.

---

## 10. MVP design acceptance criteria

The MVP design is acceptable when:

1. A new user can upload a document without training.
2. A project manager can find pending exposure in under 30 seconds.
3. Every AI risk is traceable to evidence.
4. Every financial value has a deterministic source.
5. Every approval action is explicit and auditable.
6. Low-confidence AI output enters a review queue.
7. The mobile upload flow works with poor connectivity.
8. The interface avoids presenting AI output as unquestionable truth.
