"""ChangeGuard Red-Team Test Suite.

Comprehensive adversarial test suite covering 14 security and robustness categories:
1. Prompt injection in PDFs
2. Prompt injection in emails
3. Prompt injection in image metadata
4. Hidden text instructions
5. Contradictory documents
6. Malformed financial data
7. Missing required fields
8. Cross-tenant access attempts
9. IDOR attempts
10. Unauthorized approval attempts
11. Malicious file uploads
12. Path traversal
13. SQL injection
14. Token reuse after logout
"""

from tests.red_team.cases import RED_TEAM_CASES, RedTeamCase, RedTeamCategory

__all__ = ["RED_TEAM_CASES", "RedTeamCase", "RedTeamCategory"]

