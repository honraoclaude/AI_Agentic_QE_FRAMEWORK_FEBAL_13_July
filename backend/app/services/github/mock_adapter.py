"""Mock GitHub adapter for demo mode — a canned branch + CI run for the seeded
WLTH-101 household-rollup story, so the whole connect/sync flow runs offline.
"""

import json

from ...models import ArtifactKind
from .adapter import GithubAdapter, PullItem

_SOURCE = """public with sharing class HouseholdRollupService {
    // Recalculate a household's total from its active financial accounts.
    public static void recalculate(Id householdId) {
        for (Account a : [SELECT Id FROM Account WHERE ParentId = :householdId]) {
            Decimal total = 0;
            for (FinServ__FinancialAccount__c f :
                 [SELECT Balance__c FROM FinServ__FinancialAccount__c WHERE Household__c = :a.Id]) {
                total += f.Balance__c;   // NB: SOQL inside a loop
            }
            a.Household_Total__c = total;
            update a;
        }
    }
}"""

_SARIF = {
    "version": "2.1.0",
    "runs": [{"tool": {"driver": {"name": "CodeQL"}}, "results": [
        {"ruleId": "js/sql-in-loop", "level": "warning",
         "message": {"text": "SOQL query inside a loop."},
         "locations": [{"physicalLocation": {
             "artifactLocation": {"uri": "classes/HouseholdRollupService.cls"},
             "region": {"startLine": 6}}}]},
    ]}],
}

_JUNIT = ('<testsuites><testsuite name="apex">'
          '<testcase name="rollupSumsActiveAccounts" classname="HouseholdRollupServiceTest"/>'
          '<testcase name="excludesClosedAccounts" classname="HouseholdRollupServiceTest"/>'
          '<testcase name="recalcUnderBulkLoad" classname="HouseholdRollupServiceTest">'
          '<failure message="System.LimitException: Too many SOQL queries: 101">stack</failure>'
          '</testcase></testsuite></testsuites>')

_COVERAGE = json.dumps({"overall_percent": 82.0, "classes": [
    {"name": "HouseholdRollupService", "coverage_percent": 78.0},
    {"name": "FinancialAccountTriggerHandler", "coverage_percent": 88.0},
]})

_COMPONENTS = json.dumps([
    "ApexClass: HouseholdRollupService",
    "ApexTrigger: FinancialAccountTrigger",
    "LightningComponentBundle: householdSummary",
])


class MockGithubAdapter(GithubAdapter):
    async def test_connection(self) -> dict:
        return {"ok": True, "mode": "mock"}

    async def get_branch(self, repo: str, branch: str) -> dict | None:
        return {"name": branch or "feature/WLTH-101", "head_sha": "a1b2c3d", "repo": repo}

    async def fetch_branch_artifacts(self, repo: str, branch: str) -> list[PullItem]:
        base = f"{repo or 'acme/wealth-sfdx'}@{branch or 'feature/WLTH-101'}"
        return [
            PullItem(ArtifactKind.METADATA, "changed-files.json", _COMPONENTS, f"{base} (diff)"),
            PullItem(ArtifactKind.SARIF, "codeql.sarif", json.dumps(_SARIF), f"{base} (CI #128)"),
            PullItem(ArtifactKind.JUNIT, "apex-tests.xml", _JUNIT, f"{base} (CI #128)"),
            PullItem(ArtifactKind.COVERAGE, "coverage.json", _COVERAGE, f"{base} (CI #128)"),
            PullItem(ArtifactKind.GENERIC, "HouseholdRollupService.cls", _SOURCE, f"{base} (source)"),
        ]
