-- One MVCC snapshot for authorization, exact totals, page quotations and audit history.
WITH access AS MATERIALIZED (
    SELECT p.id AS project_id, p.tenant_id, u.id AS actor_id, CAST(:tenant_wide AS boolean) AS privileged
    FROM projects p
    JOIN users u ON u.tenant_id = p.tenant_id
    JOIN tenants t ON t.id = p.tenant_id AND t.status = 'active'
    WHERE p.id = :project_id AND p.tenant_id = :tenant_id AND u.id = :actor_id
      AND u.is_active AND u.role = :actor_role
      AND (CAST(:tenant_wide AS boolean) OR EXISTS (
          SELECT 1 FROM project_memberships m
          WHERE m.tenant_id = p.tenant_id AND m.project_id = p.id AND m.user_id = u.id AND m.is_active
      ))
), docs AS MATERIALIZED (
    SELECT d.id, d.filename, (a.privileged OR d.uploaded_by_id = a.actor_id) AS private_access
    FROM documents d JOIN access a USING (tenant_id, project_id)
    WHERE d.deleted_at IS NULL AND (d.access_level <> 'restricted' OR a.privileged OR d.uploaded_by_id = a.actor_id)
), contracts_visible AS (
    SELECT c.id, c.document_id FROM contracts c JOIN access USING (tenant_id, project_id)
    LEFT JOIN docs d ON d.id = c.document_id WHERE c.document_id IS NULL OR d.id IS NOT NULL
), rfis_visible AS (
    SELECT r.id FROM rfis r JOIN access USING (tenant_id, project_id)
    LEFT JOIN docs d ON d.id = r.document_id WHERE r.document_id IS NULL OR d.id IS NOT NULL
), events_visible AS (
    SELECT e.id, e.document_id FROM project_events e JOIN access USING (tenant_id, project_id)
    LEFT JOIN docs d ON d.id = e.document_id WHERE e.document_id IS NULL OR d.id IS NOT NULL
), sources AS MATERIALIZED (
    SELECT 'document' AS kind, id, id AS document_id FROM docs
    UNION ALL SELECT 'document_chunk', c.id, d.id FROM document_chunks c
        JOIN access USING (tenant_id, project_id) JOIN docs d ON d.id = c.document_id
        WHERE c.access_level <> 'restricted' OR d.private_access
    UNION ALL SELECT 'site_photo', p.id, d.id FROM site_photos p
        JOIN access USING (tenant_id, project_id) JOIN docs d ON d.id = p.document_id
    UNION ALL SELECT 'project_event', id, document_id FROM events_visible
    UNION ALL SELECT 'contract_clause', cc.id, c.document_id FROM contract_clauses cc
        JOIN access USING (tenant_id, project_id) JOIN contracts_visible c ON c.id = cc.contract_id
    UNION ALL SELECT 'boq_item', b.id, c.document_id FROM boq_items b
        JOIN access USING (tenant_id, project_id) LEFT JOIN contracts_visible c ON c.id = b.contract_id
        WHERE b.contract_id IS NULL OR c.id IS NOT NULL
), link_status AS (
    SELECT l.subject_type, l.subject_id, bool_and(s.id IS NOT NULL) AS all_visible
    FROM evidence_links l JOIN access USING (tenant_id, project_id)
    LEFT JOIN sources s ON s.kind = l.source_type AND s.id = l.source_id
    WHERE l.subject_type IN ('risk', 'change_order')
    GROUP BY l.subject_type, l.subject_id
), orders AS (
    SELECT o.id, o.title, o.description, o.status, o.created_at, o.amount, o.currency,
           o.created_by_id, o.submitted_by_id, ls.subject_id IS NOT NULL AS supported,
           ((o.contract_id IS NULL OR c.id IS NOT NULL) AND (o.rfi_id IS NULL OR r.id IS NOT NULL)) AS full_visibility
    FROM change_orders o JOIN access USING (tenant_id, project_id)
    LEFT JOIN link_status ls ON ls.subject_type = 'change_order' AND ls.subject_id = o.id
    LEFT JOIN events_visible e ON e.id = o.source_event_id
    LEFT JOIN contracts_visible c ON c.id = o.contract_id LEFT JOIN rfis_visible r ON r.id = o.rfi_id
    WHERE ls.all_visible IS NOT FALSE AND (o.source_event_id IS NULL OR e.id IS NOT NULL)
), prior_high AS (
    SELECT DISTINCT ev.entity_id FROM audit_events ev JOIN access USING (tenant_id, project_id)
    WHERE NOT CAST(:legacy AS boolean) AND ev.entity_type = 'risk' AND ev.action = 'risk.override'
      AND ev.details->'before'->>'severity' IN ('high','critical')
), risks AS (
    SELECT r.id, r.title, r.description, r.severity, r.confidence, r.document_id, r.created_at, r.detected_at,
           CASE WHEN r.exposure_amount IS NOT NULL THEN r.currency END AS exposure_currency,
           r.owner_id, r.change_order_id, r.status, r.recommended_action,
           coalesce(nullif(r.risk_type,''),nullif(r.category,''),'operational_risk') AS risk_type,
           ls.subject_id IS NOT NULL AS has_links,
           (ls.subject_id IS NOT NULL AND NOT r.evidence_review_required AND r.status <> 'insufficient_evidence') AS supported,
           r.resolution_link_id IS NULL AND r.change_order_id IS NULL AND r.status NOT IN ('resolved','dismissed','converted') AS reviewable,
           linked_order.full_visibility IS TRUE OR r.change_order_id IS NULL AS linked_order_visible,
           r.severity IN ('high','critical') OR ph.entity_id IS NOT NULL AS high
    FROM risks r JOIN access a USING (tenant_id, project_id)
    LEFT JOIN docs d ON d.id = r.document_id LEFT JOIN events_visible e ON e.id = r.project_event_id
    LEFT JOIN link_status ls ON ls.subject_type = 'risk' AND ls.subject_id = r.id
    LEFT JOIN prior_high ph ON ph.entity_id = r.id
    LEFT JOIN orders linked_order ON linked_order.id = r.change_order_id
    LEFT JOIN event_entity_links el ON el.id = r.resolution_link_id AND el.project_id = a.project_id AND el.tenant_id = a.tenant_id
    LEFT JOIN rfis_visible rr ON rr.id = el.rfi_id LEFT JOIN orders ro ON ro.id = el.change_order_id
    WHERE ls.all_visible IS NOT FALSE AND (r.document_id IS NULL OR d.id IS NOT NULL)
      AND (r.project_event_id IS NULL OR e.id IS NOT NULL)
      AND (r.resolution_link_id IS NULL OR rr.id IS NOT NULL OR ro.full_visibility IS TRUE)
)
