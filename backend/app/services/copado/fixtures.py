"""Sample Copado result payloads for demo mode / the /copado/simulate endpoint.

Lets the whole ingest flow be exercised offline, with no real Copado org — the
same spirit as the mock Jira adapter. Payloads mirror the WLTH-101 seed story
(household rollup on Financial Services Cloud) so the ingested artifacts line up
with what the agents expect.
"""

from __future__ import annotations


def sample_results(environment: str = "UAT") -> list[dict]:
    """A representative pipeline run: CodeScan violations, an Apex test run with
    one failure, and the User Story commit manifest."""
    return [
        {
            "result_type": "codescan",
            "run": {"environment": environment, "run_id": "CS-4821"},
            "payload": {
                "violations": [
                    {
                        "rule": "ApexCRUDViolation",
                        "severity": "high",
                        "file": "classes/HouseholdRollupService.cls",
                        "line": 88,
                        "message": "SOQL without WITH SECURITY_ENFORCED on FinancialAccount.",
                    },
                    {
                        "rule": "AvoidSoqlInLoops",
                        "severity": "medium",
                        "file": "classes/HouseholdRollupService.cls",
                        "line": 142,
                        "message": "SOQL query located within a for-loop.",
                    },
                ]
            },
        },
        {
            "result_type": "apex_tests",
            "run": {"environment": environment, "run_id": "AT-9910"},
            "payload": {
                "tests": [
                    {"name": "rollupSumsActiveAccounts", "className": "HouseholdRollupServiceTest", "outcome": "Pass"},
                    {"name": "excludesClosedAccounts", "className": "HouseholdRollupServiceTest", "outcome": "Pass"},
                    {"name": "recalcUnderBulkLoad", "className": "HouseholdRollupServiceTest",
                     "outcome": "Fail", "message": "System.LimitException: Too many SOQL queries: 101"},
                ]
            },
        },
        {
            "result_type": "commit",
            "run": {"environment": environment, "run_id": "CM-3307"},
            "payload": {
                "components": [
                    {"type": "ApexClass", "name": "HouseholdRollupService"},
                    {"type": "ApexTrigger", "name": "FinancialAccountTrigger"},
                    {"type": "Flow", "name": "HouseholdReassignment"},
                ]
            },
        },
    ]
