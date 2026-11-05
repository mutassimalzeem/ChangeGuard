"""Permission isolation golden test cases definition (10 cases)."""

def get_permission_isolation_cases():
    return [
        {
            "id": "PERM-001",
            "title": "Cross-Tenant Document Access Prevention",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-tenant-b-01",
                    "tenant_id": "22222222-2222-2222-2222-222222222222",
                    "role": "project_manager",
                },
                "target_resource": {
                    "resource_type": "document",
                    "document_id": "doc-tenant-a-con01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                },
                "action": "documents.read",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 403,
                "error_code": "TENANT_ACCESS_DENIED",
                "data_leaked": False,
                "audit_event_logged": True,
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                    "zero_tenant_leakage": True,
                },
            },
        },
        {
            "id": "PERM-002",
            "title": "Cross-Project Document Scoping within Tenant",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-proj-101-pm",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "assigned_projects": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
                    "role": "project_manager",
                },
                "target_resource": {
                    "resource_type": "document",
                    "document_id": "doc-proj-102-boq",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                },
                "action": "documents.read",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 403,
                "error_code": "PROJECT_ACCESS_DENIED",
                "data_leaked": False,
                "audit_event_logged": True,
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                    "project_scoping_enforced": True,
                },
            },
        },
        {
            "id": "PERM-003",
            "title": "Role Boundary: Site Engineer Blocked from Change Order Approval",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-site-eng-01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "role": "site_engineer",
                },
                "target_resource": {
                    "resource_type": "change_order",
                    "change_order_id": "co-2026-001",
                    "amount": "142500.00",
                },
                "action": "approvals.decide",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 403,
                "error_code": "INSUFFICIENT_ROLE_PERMISSIONS",
                "required_roles": ["commercial_manager", "owner", "admin"],
                "data_leaked": False,
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                    "privilege_escalation_prevented": True,
                },
            },
        },
        {
            "id": "PERM-004",
            "title": "Role Boundary: Project Manager Blocked from Financial Release",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-pm-01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "role": "project_manager",
                },
                "target_resource": {
                    "resource_type": "payment_certificate",
                    "certificate_id": "ipc-2026-03",
                    "release_amount": "450000.00",
                },
                "action": "financial.release",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 403,
                "error_code": "FINANCIAL_RELEASE_UNAUTHORIZED",
                "required_roles": ["commercial_manager", "owner"],
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                },
            },
        },
        {
            "id": "PERM-005",
            "title": "Restricted Access Document Inaccessible to Project Viewer",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-viewer-01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "role": "viewer",
                },
                "target_resource": {
                    "resource_type": "document",
                    "document_id": "doc-commercial-settlement",
                    "access_level": "restricted",
                    "classification": "contract",
                },
                "action": "documents.read",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 403,
                "error_code": "RESTRICTED_ACCESS_REQUIRED",
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                },
            },
        },
        {
            "id": "PERM-006",
            "title": "Read-Only Auditor Blocked from Risk Status Modification",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-auditor-01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "role": "auditor",
                },
                "target_resource": {
                    "resource_type": "risk",
                    "risk_id": "risk-cost-outlier-01",
                },
                "action": "risks.write",
                "mutation": {"status": "accepted"},
            },
            "expected_output": {
                "allowed": False,
                "http_status": 403,
                "error_code": "AUDITOR_READ_ONLY",
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                    "read_only_guarantee": True,
                },
            },
        },
        {
            "id": "PERM-007",
            "title": "Quarantined Document Raw File & Text Chunk Access Blocked",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-pm-01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "role": "project_manager",
                },
                "target_resource": {
                    "resource_type": "document",
                    "document_id": "doc-malicious-infected-pdf",
                    "status": "quarantined",
                    "quarantine_reason": "Embedded executable script detected by virus scanner",
                },
                "action": "documents.read_raw",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 423,
                "error_code": "DOCUMENT_QUARANTINED",
                "raw_file_accessible": False,
                "chunks_searchable": False,
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                    "quarantine_isolation_enforced": True,
                },
            },
        },
        {
            "id": "PERM-008",
            "title": "Deleted Project Tombstone Scoping in Evidence Queries",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-pm-01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "role": "project_manager",
                },
                "target_resource": {
                    "resource_type": "project",
                    "project_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    "deleted_at": "2026-03-01T12:00:00Z",
                },
                "action": "evidence.query",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 404,
                "error_code": "PROJECT_NOT_FOUND_OR_DELETED",
                "returned_links_count": 0,
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                    "tombstone_isolated": True,
                },
            },
        },
        {
            "id": "PERM-009",
            "title": "API Service Key Cross-Tenant Hybrid Retrieval Rejection",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "auth_method": "service_token",
                    "token_id": "svc-token-tenant-a",
                    "token_tenant_id": "11111111-1111-1111-1111-111111111111",
                },
                "target_resource": {
                    "endpoint": "/api/v1/retrieval/search",
                    "requested_tenant_id": "22222222-2222-2222-2222-222222222222",
                    "query": "chilled water riser specifications",
                },
                "action": "retrieval.search",
            },
            "expected_output": {
                "allowed": False,
                "http_status": 403,
                "error_code": "SERVICE_TOKEN_TENANT_MISMATCH",
                "returned_hits_count": 0,
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "access_allowed": False,
                    "zero_cross_tenant_search": True,
                },
            },
        },
        {
            "id": "PERM-010",
            "title": "Chunk-Level Redaction in Hybrid Search Results",
            "category": "permission_isolation",
            "input": {
                "actor": {
                    "user_id": "user-site-eng-01",
                    "tenant_id": "11111111-1111-1111-1111-111111111111",
                    "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    "role": "site_engineer",
                    "has_restricted_access": False,
                },
                "search_query": "contract payment retainage terms",
                "candidate_chunks": [
                    {"chunk_id": "chk-public-01", "access_level": "project", "text": "Interim valuations shall be submitted monthly. Retainage of 5% applies."},
                    {"chunk_id": "chk-restricted-01", "access_level": "restricted", "text": "Confidential settlement: Contractor agrees to maximum liquidated damages cap of $500,000."},
                ],
            },
            "expected_output": {
                "allowed": True,
                "filtered_results": [
                    {"chunk_id": "chk-public-01", "redacted": False}
                ],
                "omitted_chunk_ids": ["chk-restricted-01"],
                "data_leaked": False,
            },
            "evaluation_criteria": {
                "metric": "security_isolation",
                "assertions": {
                    "restricted_chunks_omitted": True,
                    "allowed_chunks_returned": True,
                },
            },
        },
    ]

