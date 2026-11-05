"""Entities golden test cases definition."""

def get_entities_manifest():
    return {
        "metadata": {
            "version": "1.0.0",
            "description": "Master entity graph for ChangeGuard Golden Evaluation Dataset.",
            "synthetic_data_guarantee": "Strictly realistic synthetic construction entities. Zero customer data.",
        },
        "tenants": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Apex Global Developments",
                "slug": "apex-global",
                "status": "active",
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "Metro Authority Transit",
                "slug": "metro-transit",
                "status": "active",
            },
        ],
        "projects": [
            {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "name": "Apex Horizon Commercial Center - Phase 1",
                "code": "PRJ-AHCC-01",
                "status": "active",
                "currency": "USD",
                "total_budget": "185000000.00",
            },
            {
                "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "name": "Highline Commercial Tower",
                "code": "PRJ-HLT-02",
                "status": "active",
                "currency": "USD",
                "total_budget": "94000000.00",
            },
            {
                "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
                "tenant_id": "11111111-1111-1111-1111-111111111111",
                "name": "Waterfront Logistics Hub (Archived)",
                "code": "PRJ-WLH-ARCH",
                "status": "deleted",
                "deleted_at": "2026-03-01T12:00:00Z",
                "currency": "USD",
                "total_budget": "42000000.00",
            },
        ],
        "employers": [
            {"id": "emp-001", "name": "Apex Real Estate Ventures Ltd", "role": "client_developer"},
            {"id": "emp-002", "name": "Metro Transit Infrastructure Authority", "role": "public_authority"},
            {"id": "emp-003", "name": "Highline Tower Development Corp", "role": "client_developer"},
            {"id": "emp-004", "name": "Waterfront Logistics Park LLC", "role": "client_developer"},
            {"id": "emp-005", "name": "Zenith Commercial Towers Ltd", "role": "client_developer"},
        ],
        "contractors": [
            {"id": "con-001", "name": "Horizon Structural Engineering LLC", "specialty": "reinforced_concrete"},
            {"id": "con-002", "name": "Pioneer Thermal Dynamics Corp", "specialty": "mechanical_chilled_water"},
            {"id": "con-003", "name": "Titan Metalwork Specialists", "specialty": "structural_steel"},
            {"id": "con-004", "name": "GeoFoundation Engineering Ltd", "specialty": "piling_shoring_dewatering"},
            {"id": "con-005", "name": "Alumitech Glazing Systems Inc", "specialty": "unitized_curtain_wall"},
        ],
        "contracts": [
            {"reference": "CON-2026-CS-001", "employer": "Apex Real Estate Ventures Ltd", "contractor": "Horizon Structural Engineering LLC", "value": "4850000.00", "currency": "USD"},
            {"reference": "CON-2026-MEP-002", "employer": "Metro Transit Infrastructure Authority", "contractor": "Pioneer Thermal Dynamics Corp", "value": "2420000.00", "currency": "USD"},
            {"reference": "CON-2026-STL-003", "employer": "Highline Tower Development Corp", "contractor": "Titan Metalwork Specialists", "value": "3150000.00", "currency": "USD"},
            {"reference": "CON-2026-GEO-004", "employer": "Waterfront Logistics Park LLC", "contractor": "GeoFoundation Engineering Ltd", "value": "1875000.00", "currency": "USD"},
            {"reference": "CON-2026-FAC-005", "employer": "Zenith Commercial Towers Ltd", "contractor": "Alumitech Glazing Systems Inc", "value": "5600000.00", "currency": "USD"},
        ],
        "rfis": [
            {"reference": "RFI-2026-001", "subject": "Clash between Chilled Water Riser and Transfer Girder TG-04", "contract": "CON-2026-CS-001", "status": "answered"},
            {"reference": "RFI-2026-002", "subject": "Unforeseen High Water Table Elevation at Basement B3", "contract": "CON-2026-GEO-004", "status": "open"},
            {"reference": "RFI-2026-003", "subject": "Curtain Wall Seismic Joint Displacement Clearance", "contract": "CON-2026-FAC-005", "status": "answered"},
            {"reference": "RFI-2026-004", "subject": "Rebar Lap Splice Length in High Moment Plastic Hinge Zone", "contract": "CON-2026-CS-001", "status": "answered"},
            {"reference": "RFI-2026-005", "subject": "Discontinued Fire Damper Substitution", "contract": "CON-2026-MEP-002", "status": "closed"},
        ],
        "change_orders": [
            {"reference": "CO-2026-001", "amount": "142500.00", "currency": "USD", "contract": "CON-2026-CS-001", "status": "approved"},
            {"reference": "CO-2026-002", "amount": "88750.00", "currency": "USD", "contract": "CON-2026-MEP-002", "status": "submitted"},
            {"reference": "CO-2026-003", "amount": "215000.00", "currency": "USD", "contract": "CON-2026-CS-001", "status": "approved"},
            {"reference": "CO-2026-004", "amount": "64200.00", "currency": "USD", "contract": "CON-2026-CS-001", "status": "draft"},
            {"reference": "CO-2026-005", "amount": "118900.00", "currency": "USD", "contract": "CON-2026-GEO-004", "status": "executed"},
            {"reference": "CO-2026-006", "amount": "95400.00", "currency": "USD", "contract": "CON-2026-CS-001", "status": "submitted"},
            {"reference": "CO-2026-007", "amount": "134800.00", "currency": "USD", "contract": "CON-2026-MEP-002", "status": "approved"},
            {"reference": "CO-2026-008", "amount": "76500.00", "currency": "USD", "contract": "CON-2026-MEP-002", "status": "submitted"},
            {"reference": "CO-2026-009", "amount": "52300.00", "currency": "USD", "contract": "CON-2026-CS-001", "status": "draft"},
            {"reference": "CO-2026-010", "amount": "-48000.00", "currency": "USD", "contract": "CON-2026-CS-001", "status": "approved"},
        ],
    }

