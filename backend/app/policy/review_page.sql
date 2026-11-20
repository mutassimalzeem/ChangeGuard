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
), risk_items AS (
    SELECT r.*, array_remove(ARRAY[
        CASE WHEN NOT supported THEN 'insufficient_evidence_risk' END,
        CAST(:risk_categories AS jsonb)->>risk_type,
        CASE WHEN high THEN 'high_severity_risk' END], NULL) AS categories
    FROM risks r
), candidates AS (
    SELECT 'risk' AS kind, r.id, r.categories, r.title, r.description, r.risk_type, r.severity, r.confidence,
        CASE WHEN r.status='open' AND NOT r.supported THEN 'insufficient_evidence' ELSE r.status END AS status,
        r.created_at, r.owner_id, NULL::timestamptz AS deadline, r.document_id, r.change_order_id, r.supported,
        r.reviewable, r.recommended_action, NULL::numeric AS amount, r.exposure_currency AS currency, false AS can_decide,
        'risk' AS evidence_kind, r.id AS evidence_id, 'risk' AS entity_type, r.detected_at AS legacy_date
    FROM risk_items r WHERE r.linked_order_visible AND cardinality(r.categories)>0
    UNION ALL
    SELECT 'extraction', t.id, ARRAY['low_confidence_extraction'], d.filename, 'The extraction needs human verification.',
        t.reason,NULL,coalesce(doc.extraction_confidence,CASE WHEN t.reason='low_classification_confidence'
            THEN (doc.classification_result->>'confidence')::numeric END),
        t.status,t.created_at,NULL,NULL,d.id,NULL,false,t.status IN ('pending','evidence_requested'),
        'Verify the extraction against the original document.',NULL,NULL,false,NULL,NULL,'document_review_task',t.created_at
    FROM document_review_tasks t JOIN access USING (tenant_id,project_id)
    JOIN docs d ON d.id=t.document_id JOIN documents doc ON doc.id=d.id
    WHERE t.reason = ANY(CAST(:extraction_reasons AS text[]))
    UNION ALL
    SELECT 'change_order',o.id,ARRAY['high_value_change'],o.title,o.description,'high_value_change',NULL,NULL,
        o.status,o.created_at,NULL,NULL,NULL,o.id,o.supported,o.status IN ('potential','under_review','drafted','submitted'),
        'Verify the change and its supporting documents.',o.amount,o.currency,false,'change_order',o.id,'change_order',o.created_at
    FROM orders o WHERE o.full_visibility AND o.amount >= (CAST(:thresholds AS jsonb)->>o.currency)::numeric
    UNION ALL
    SELECT 'approval',p.id,ARRAY['approval_request'],coalesce(o.title,r.title),coalesce(o.description,r.description),
        'approval_request',NULL,NULL,p.status,p.created_at,p.assigned_to_id,p.due_at,NULL,p.change_order_id,
        coalesce(o.supported,r.has_links,false),p.status='pending','Review the approval request.',o.amount,CASE WHEN o.amount IS NOT NULL THEN o.currency END,
        (o.id IS NOT NULL AND p.status='pending' AND o.status='submitted' AND CAST(:can_approve AS boolean)
            AND a.actor_id IS DISTINCT FROM o.created_by_id AND a.actor_id IS DISTINCT FROM o.submitted_by_id),
        CASE WHEN o.id IS NULL THEN 'risk' ELSE 'change_order' END, coalesce(o.id,r.id),'approval',p.created_at
    FROM approvals p JOIN access a USING (tenant_id,project_id)
    LEFT JOIN orders o ON o.id=p.change_order_id AND o.full_visibility
    LEFT JOIN risks r ON r.id=p.risk_id AND r.linked_order_visible
    WHERE o.id IS NOT NULL OR r.id IS NOT NULL
), assignments AS (
    SELECT DISTINCT ON (ev.entity_type, ev.entity_id) ev.entity_type,ev.entity_id,(ev.details->>'owner_id')::uuid AS reviewer
    FROM audit_events ev JOIN access USING (tenant_id,project_id)
    WHERE ev.action='review.assign_owner' ORDER BY ev.entity_type,ev.entity_id,ev.created_at DESC,ev.id DESC
), classified AS (
    SELECT c.*,coalesce(a.reviewer,c.owner_id) AS assignee,
        CASE WHEN status='resolved' THEN 'resolved'
             WHEN kind='risk' AND change_order_id IS NOT NULL THEN 'converted_to_change_order'
             WHEN status IN ('approved','closed','rejected','disputed') THEN 'resolved'
             WHEN status='converted' THEN 'converted_to_change_order'
             WHEN status IN ('accepted','dismissed','evidence_requested') THEN status
             WHEN kind='risk' AND NOT supported THEN 'insufficient_evidence' ELSE 'review_required' END AS review_state
    FROM candidates c LEFT JOIN assignments a ON a.entity_type=c.entity_type AND a.entity_id=c.id
), matching AS MATERIALIZED (
    SELECT * FROM classified
    WHERE (NOT :legacy OR kind IN ('risk','extraction'))
      AND (CAST(:item_id AS uuid) IS NULL OR id=:item_id)
      AND (CAST(:kind AS text) IS NULL OR kind=:kind)
      AND (CAST(:category AS text) IS NULL OR :category=ANY(categories))
      AND (CAST(:severity AS text) IS NULL OR severity=:severity)
      AND (:status='all' OR review_state=:status OR (:status='actionable' AND reviewable AND review_state<>'accepted'))
      AND (CAST(:owner_id AS uuid) IS NULL OR assignee=:owner_id)
      AND (CAST(:date_from AS date) IS NULL OR (created_at AT TIME ZONE 'UTC')::date >= :date_from)
      AND (CAST(:date_to AS date) IS NULL OR (created_at AT TIME ZONE 'UTC')::date <= :date_to)
      AND (CAST(:min_conf AS numeric) IS NULL OR confidence >= :min_conf)
      AND (CAST(:max_conf AS numeric) IS NULL OR confidence <= :max_conf)
), page AS MATERIALIZED (
    SELECT *, row_number() OVER sort_order AS position FROM matching
    WINDOW sort_order AS (ORDER BY
        CASE WHEN :legacy THEN CASE kind WHEN 'risk' THEN 0 ELSE 1 END END,
        CASE WHEN :legacy THEN legacy_date END DESC,
        CASE WHEN :legacy THEN id END,
        CASE WHEN :sort='severity' THEN array_position(ARRAY['low','medium','high','critical'],severity)*CAST(:sign AS integer) END NULLS LAST,
        CASE WHEN :sort='confidence' THEN confidence*:sign END NULLS LAST,
        CASE WHEN :sort='deadline' AND :sign=1 THEN deadline END ASC NULLS LAST,
        CASE WHEN :sort='deadline' AND :sign=-1 THEN deadline END DESC NULLS LAST,
        CASE WHEN :sort='created_at' AND :sign=1 THEN created_at END ASC NULLS LAST,
        CASE WHEN :sort='created_at' AND :sign=-1 THEN created_at END DESC NULLS LAST, kind,id)
    ORDER BY position LIMIT :limit OFFSET :offset
), citations AS (
    SELECT l.subject_type,l.subject_id,jsonb_agg(jsonb_build_object(
        'id',l.id,'source_type',l.source_type,'document_id',s.document_id,'document_name',d.filename,
        'source_page',l.source_page,'source_text_snippet',l.source_text_snippet) ORDER BY l.created_at,l.id) AS evidence,
        (array_agg(s.document_id ORDER BY l.created_at,l.id) FILTER (WHERE s.document_id IS NOT NULL))[1] AS first_document
    FROM (SELECT DISTINCT evidence_kind,evidence_id FROM page WHERE evidence_id IS NOT NULL) p
    JOIN access a ON true
    JOIN evidence_links l ON l.tenant_id=a.tenant_id AND l.project_id=a.project_id AND l.subject_type=p.evidence_kind AND l.subject_id=p.evidence_id
    JOIN sources s ON s.kind=l.source_type AND s.id=l.source_id LEFT JOIN docs d ON d.id=s.document_id
    GROUP BY l.subject_type,l.subject_id
), history_events AS (
    SELECT p.kind,p.id,e.id AS audit_id,e.action,e.actor_id,e.created_at,e.details FROM page p
    JOIN access a ON true JOIN audit_events e ON e.tenant_id=a.tenant_id AND e.project_id=a.project_id
        AND NOT :legacy AND e.entity_type=p.entity_type AND e.entity_id=p.id AND e.action<>'review.command'
    UNION ALL
    SELECT p.kind,p.id,e.id,e.action,e.actor_id,e.created_at,e.details FROM page p
    JOIN access a ON true JOIN audit_events e ON e.tenant_id=a.tenant_id AND e.project_id=a.project_id
        AND e.entity_type='change_order' AND e.entity_id=p.change_order_id AND e.details->>'approval_id'=p.id::text
    WHERE p.kind='approval' AND e.action<>'review.command'
), histories AS (
    SELECT kind,id,jsonb_agg(jsonb_build_object('at',created_at,'action',action,'actor_id',actor_id,
        'reason',details->>'reason','owner_id',details->>'owner_id') ORDER BY created_at,audit_id) AS history
    FROM history_events GROUP BY kind,id
)
SELECT totals.total, p.kind,p.id,p.title,p.description,p.risk_type,p.categories,p.confidence,p.severity,p.status,
       p.supported AS evidence_supported,p.reviewable,p.created_at,p.deadline,p.assignee AS owner_id,
       p.change_order_id,p.review_state,p.can_decide,p.recommended_action,p.amount::text,p.currency,
       coalesce(p.document_id,c.first_document) AS document_id,coalesce(c.evidence,'[]'::jsonb) AS evidence_details,
       coalesce(h.history,'[]'::jsonb) AS history,doc.structured_extraction
FROM access CROSS JOIN (SELECT count(*) AS total FROM matching) totals
LEFT JOIN page p ON true LEFT JOIN citations c ON c.subject_type=p.evidence_kind AND c.subject_id=p.evidence_id
LEFT JOIN histories h ON h.kind=p.kind AND h.id=p.id
LEFT JOIN documents doc ON p.kind='extraction' AND doc.id=p.document_id AND doc.project_id=access.project_id AND doc.tenant_id=access.tenant_id
ORDER BY p.position
