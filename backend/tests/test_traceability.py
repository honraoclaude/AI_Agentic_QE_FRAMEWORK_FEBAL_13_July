"""Evidence-anchor traceability spine: acceptance criteria carry stable ids
(AC-1..N) that thread through FCA Impact, BDD, AC Compliance and Test Execution.
"""

from sqlalchemy import select

from app.models import ArtifactKind, Story
from app.services.agents.demo_outputs import GENERATORS, build
from app.services.agents.output_schemas import (
    AcComplianceOutput,
    BddGeneratorOutput,
    FcaRegulatoryImpactOutput,
    TestExecutionOutput,
)
from app.services.artifacts import parsers
from app.services.jira import sync_service


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))).scalar_one()


def _ta_upstream(story):
    return [{"agent_key": "three_amigos", "agent_name": "TA",
             "output": GENERATORS["three_amigos"](story)}]


async def test_ac_id_spine_threads_through_agents(session, adapter):
    story = await _seed(session, adapter)
    n_ac = len(story.acceptance_criteria)
    assert n_ac >= 2

    # 1. FCA Impact anchors each regulation to a triggering AC id.
    fca = build("fca_regulatory_impact", story, None, artifacts=[], upstream=[])
    fca_p = FcaRegulatoryImpactOutput.model_validate(fca)
    assert all(r.triggered_by.startswith("AC-") for r in fca_p.applicable_regulations)

    # 2. BDD scenarios carry ac_refs.
    bdd = build("bdd_generator", story, None, artifacts=[], upstream=_ta_upstream(story))
    bdd_p = BddGeneratorOutput.model_validate(bdd)
    assert bdd_p.scenarios and all(
        s.ac_refs and s.ac_refs[0].startswith("AC-") for s in bdd_p.scenarios
    )

    # 3. AC Compliance stamps every mapping row with its AC id (AC-1..N).
    meta = parsers.parse(ArtifactKind.METADATA, '["ApexClass: HouseholdRollupService"]')
    arts = [{"kind": "METADATA", "filename": "p.json", "summary": meta["summary"], "parsed": meta["parsed"]}]
    ac = build("ac_compliance", story, None, artifacts=arts,
               upstream=[{"agent_key": "bdd_generator", "agent_name": "BDD", "output": bdd}])
    ac_p = AcComplianceOutput.model_validate(ac)
    ids = [m.ac_id for m in ac_p.ac_mapping]
    assert ids == [f"AC-{i}" for i in range(1, n_ac + 1)]

    # 4. Test Execution links a failure back to the AC id via the matched scenario.
    junit = parsers.parse(ArtifactKind.JUNIT, (
        '<testsuites><testsuite name="t">'
        '<testcase name="Rollup sums only active household accounts" classname="T">'
        '<failure message="off by one">x</failure></testcase>'
        '</testsuite></testsuites>'
    ))
    te = build("test_execution_analyst", story, None,
               artifacts=[{"kind": "JUNIT", "filename": "t.xml", "summary": junit["summary"], "parsed": junit["parsed"]}],
               upstream=[{"agent_key": "bdd_generator", "agent_name": "BDD", "output": bdd}])
    te_p = TestExecutionOutput.model_validate(te)
    anchored = [f for f in te_p.failures if f.ac_ref]
    assert anchored and anchored[0].ac_ref.startswith("AC-")
