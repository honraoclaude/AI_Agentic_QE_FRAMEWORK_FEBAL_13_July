"""In-memory Jira adapter for demo mode. Seeded with realistic FCA-regulated
wealth-management stories across FSC / Sales Cloud / Marketing Cloud so the
whole platform is explorable without credentials.

Test/demo helpers (simulate_update, remove_from_sprint) let you exercise
conflict detection and out-of-scope handling.
"""

from datetime import datetime, timedelta, timezone

from .adapter import JiraAdapter, JiraStoryData

_T0 = datetime(2026, 7, 6, 9, 0, 0, tzinfo=timezone.utc)


def _seed_stories() -> dict[str, JiraStoryData]:
    stories = [
        JiraStoryData(
            key="WLTH-101",
            summary="Advisor can view household net worth rollup on client 360",
            description=(
                "As a wealth advisor I want a household-level net worth rollup on "
                "the FSC client 360 page so that I can review a family's combined "
                "position before an annual review meeting."
            ),
            acceptance_criteria=[
                "Rollup sums all active financial accounts across household members",
                "Closed and pending accounts are excluded from the rollup",
                "Rollup recalculates within 5 minutes of an account balance change",
                "Values display in GBP with correct rounding to 2 decimal places",
            ],
            story_points=8,
            sprint="Sprint 24",
            status="Refinement",
            assignee="Priya Sharma",
            labels=["fsc", "client-360"],
            priority="High",
            fca_impact="HIGH",
            cloud="FSC",
            updated_at=_T0,
        ),
        JiraStoryData(
            key="WLTH-102",
            summary="Capture client risk profile during onboarding (COBS suitability)",
            description=(
                "Onboarding flow must capture attitude-to-risk and capacity-for-loss "
                "responses and persist them to the FSC client record to evidence "
                "COBS 9A suitability."
            ),
            acceptance_criteria=[
                "All suitability questions are mandatory before submission",
                "Risk profile score is calculated per the approved matrix",
                "A dated, immutable copy of responses is stored on the client record",
            ],
            story_points=5,
            sprint="Sprint 24",
            status="Refinement",
            assignee="Tom Okafor",
            labels=["fsc", "onboarding", "cobs"],
            priority="Highest",
            fca_impact="HIGH",
            cloud="FSC",
            updated_at=_T0 + timedelta(hours=2),
        ),
        JiraStoryData(
            key="WLTH-103",
            summary="Convert referred prospects to opportunities with source tracking",
            description=(
                "Sales team needs lead conversion for professional-introducer "
                "referrals with the referral source carried onto the opportunity."
            ),
            acceptance_criteria=[
                "Lead conversion maps referral source to the opportunity",
                "Duplicate detection runs against existing FSC person accounts",
            ],
            story_points=3,
            sprint="Sprint 24",
            status="Ready for Refinement",
            assignee="Sofia Reyes",
            labels=["sales-cloud", "leads"],
            priority="Medium",
            fca_impact="MEDIUM",
            cloud="SALES",
            updated_at=_T0 + timedelta(hours=4),
        ),
        JiraStoryData(
            key="WLTH-104",
            summary="Quarterly portfolio statement email journey",
            description=(
                "Marketing Cloud journey to notify clients their quarterly statement "
                "is available in the portal, honouring contact preferences."
            ),
            acceptance_criteria=[
                "Journey only targets clients with an active portal login",
                "Suppression list excludes clients with paper-only preference",
                "Unsubscribe updates the FSC contact preference within 24h",
            ],
            story_points=5,
            sprint="Sprint 24",
            status="Ready for Refinement",
            assignee="Dan Whitfield",
            labels=["marketing-cloud", "journeys"],
            priority="Medium",
            fca_impact="MEDIUM",
            cloud="MARKETING",
            updated_at=_T0 + timedelta(hours=6),
        ),
        JiraStoryData(
            key="WLTH-105",
            summary="Fee calculation engine for discretionary portfolios",
            description=(
                "Calculate tiered ad-valorem management fees on discretionary "
                "portfolios, prorated for mid-quarter inflows/outflows."
            ),
            acceptance_criteria=[
                "Tier boundaries applied per the published fee schedule",
                "Mid-quarter flows prorated by calendar days",
                "Calculated fee matches finance reconciliation within 0.01 GBP",
            ],
            story_points=13,
            sprint="Sprint 24",
            status="Refinement",
            assignee="Priya Sharma",
            labels=["fsc", "fees", "financial-calc"],
            priority="Highest",
            fca_impact="HIGH",
            cloud="FSC",
            updated_at=_T0 + timedelta(hours=8),
        ),
        JiraStoryData(
            key="WLTH-106",
            summary="Auto-advance opportunity stage on signed client agreement",
            description=(
                "When a signed client agreement document is attached, move the "
                "opportunity to 'Agreement Signed' and notify the paraplanner queue."
            ),
            acceptance_criteria=[
                "Stage changes only when document type = Client Agreement",
                "Paraplanner queue receives a task within 1 minute",
            ],
            story_points=2,
            sprint="Sprint 24",
            status="Ready for Refinement",
            assignee="Sofia Reyes",
            labels=["sales-cloud", "automation"],
            priority="Low",
            fca_impact="LOW",
            cloud="SALES",
            updated_at=_T0 + timedelta(hours=10),
        ),
        JiraStoryData(
            key="WLTH-107",
            summary="Consent preference centre sync between Marketing Cloud and FSC",
            description=(
                "Two-way sync of marketing consent between the preference centre "
                "and FSC contact records (Consumer Duty / PECR)."
            ),
            acceptance_criteria=[
                "Consent changes propagate both directions within 15 minutes",
                "A full consent-change history is retained",
            ],
            story_points=8,
            sprint="Sprint 24",
            status="Refinement",
            assignee="Dan Whitfield",
            labels=["marketing-cloud", "consent", "consumer-duty"],
            priority="High",
            fca_impact="HIGH",
            cloud="MARKETING",
            updated_at=_T0 + timedelta(hours=12),
        ),
        # Deliberately missing FCA impact + cloud: exercises the Story Quality
        # Agent's propose-then-human-confirm path.
        JiraStoryData(
            key="WLTH-108",
            summary="Merge duplicate person accounts created by householding import",
            description=(
                "The householding data import created duplicate person accounts. "
                "Provide a supervised merge that preserves financial account "
                "relationships and rollup integrity."
            ),
            acceptance_criteria=[
                "Merge preview shows surviving record and field-level outcome",
                "Financial account relationships re-parent to the surviving record",
            ],
            story_points=8,
            sprint="Sprint 24",
            status="Ready for Refinement",
            assignee=None,
            labels=["fsc", "data-quality"],
            priority="High",
            fca_impact=None,
            cloud=None,
            updated_at=_T0 + timedelta(hours=14),
        ),
    ]
    return {s.key: s for s in stories}


class MockJiraAdapter(JiraAdapter):
    def __init__(self) -> None:
        self._stories: dict[str, JiraStoryData] = _seed_stories()
        # Push records — inspectable in demo mode / tests.
        self.posted_comments: list[dict] = []
        self.applied_labels: list[dict] = []
        self.transitions_done: list[dict] = []
        self.attachments: list[dict] = []
        # Test/demo hook: simulate Jira being down for pushes (retry queue).
        self.fail_pushes: bool = False

    def _maybe_fail(self) -> None:
        if self.fail_pushes:
            raise RuntimeError("simulated Jira outage (mock adapter fail_pushes=True)")

    async def test_connection(self) -> dict:
        return {
            "ok": True,
            "mode": "demo",
            "user": "demo.user@wealthco.example",
            "project": "WLTH",
            "stories_available": len(self._stories),
        }

    async def fetch_stories(self, jql: str | None = None) -> list[JiraStoryData]:
        return [s.model_copy(deep=True) for s in self._stories.values()]

    async def fetch_story(self, key: str) -> JiraStoryData | None:
        story = self._stories.get(key)
        return story.model_copy(deep=True) if story else None

    async def add_comment(self, key: str, adf_body: dict) -> dict:
        self._maybe_fail()
        record = {"key": key, "body": adf_body}
        self.posted_comments.append(record)
        return {"ok": True, **record}

    async def add_label(self, key: str, label: str) -> dict:
        self._maybe_fail()
        record = {"key": key, "label": label}
        self.applied_labels.append(record)
        return {"ok": True, **record}

    async def get_transitions(self, key: str) -> list[dict]:
        return [
            {"id": "11", "name": "Ready for Dev"},
            {"id": "21", "name": "In Progress"},
            {"id": "31", "name": "Ready for UAT"},
            {"id": "41", "name": "Done"},
        ]

    async def transition_issue(self, key: str, transition_id: str) -> dict:
        self._maybe_fail()
        record = {"key": key, "transition_id": transition_id}
        self.transitions_done.append(record)
        return {"ok": True, **record}

    async def attach_file(self, key: str, filename: str, content: bytes) -> dict:
        self._maybe_fail()
        record = {"key": key, "filename": filename, "size": len(content)}
        self.attachments.append(record)
        return {"ok": True, **record}

    # ---- demo/test helpers (not part of the adapter contract) ----

    def simulate_update(self, key: str, **changes) -> None:
        """Mutate a story upstream, as if someone edited it in Jira."""
        story = self._stories[key]
        data = story.model_dump()
        data.update(changes)
        data["updated_at"] = datetime.now(timezone.utc)
        self._stories[key] = JiraStoryData(**data)

    def remove_from_sprint(self, key: str) -> None:
        """Story dropped from the sprint — should become OUT_OF_SCOPE locally."""
        self._stories.pop(key, None)
