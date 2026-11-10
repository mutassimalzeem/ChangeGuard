# Explicit event links and audited risk resolution

Implement one deterministic transition for `daily_report_delay_without_link`.

- [x] Add immutable same-tenant/project event-to-RFI/change-order links and a
  migration linking a resolved risk to its exact source-event relationship.
- [x] Add an authenticated explicit linking endpoint with mandatory reason,
  source visibility and entity-write/risk-review permissions. Serialize by event;
  repeated linkage must preserve the first resolution and audit exactly once.
- [x] Reuse the transition from human change-order creation with source_event_id
  and existing change-order/event evidence appends. No model capability is added.
- [x] Expose resolution metadata through risk/timeline reads; keep original risk
  and evidence intact; block unaudited status changes and later accidental reopening.
- [x] Test RFI/CO linking, unrelated links, roles/tenants/restricted evidence,
  replay/rollback/immutability, preservation and prevention of later duplicate risks.
- [x] Run focused and full backend validation, update documentation and MEMORY.md.

Resolution records entity type/ID, actor, timestamp and reason. Similar text,
retrieval and model judgment alone never create a relationship or resolve a risk.
