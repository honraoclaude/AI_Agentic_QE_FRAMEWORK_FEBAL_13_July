from sqlalchemy import select

from app.models import Phase, Story
from app.services import evidence_pack, workflow
from app.services.agents.registry import agents_for_phase
from app.services.jira import sync_service


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))).scalar_one()


async def _walk_phase(session, story, phase):
    for agent in agents_for_phase(phase):
        run = await workflow.latest_run(session, story.id, agent.key)
        await workflow.approve_and_run(session, run.id, approver="PO")
        await workflow.accept_run(session, run.id, actor="PO")
    await session.commit()


async def test_assemble_structure(session, adapter):
    story = await _seed(session, adapter)
    await _walk_phase(session, story, Phase.REFINEMENT)
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)
    await workflow.signoff_gate(session, gate.id, "Priya", "Product Owner", "Gate 1 met")
    await session.commit()

    pack = await evidence_pack.assemble(session, story)
    assert pack["story"]["jira_key"] == "WLTH-101"
    assert pack["platform"]
    # One signed-off gate recorded with the human approver.
    signed = [g for g in pack["gates"] if g["status"] == "SIGNED_OFF"]
    assert signed and signed[0]["approver_name"] == "Priya"
    # AI-governance record: every agent run has prompt version + output hash.
    assert pack["agents"] and all("prompt_version" in a and a["output_hash"] for a in pack["agents"])
    # Regulatory evidence pulled from the relevant agents.
    assert pack["regulatory"]["fca_impact"].get("applicable_regulations")
    assert pack["regulatory"]["consumer_duty"].get("outcomes")
    # Health synthesis + verified chain.
    assert pack["health"]["score"] is not None
    assert pack["audit_chain_verification"]["valid"] is True


async def test_render_html_is_complete_document(session, adapter):
    story = await _seed(session, adapter)
    await _walk_phase(session, story, Phase.REFINEMENT)
    pack = await evidence_pack.assemble(session, story)
    html = evidence_pack.render_html(pack)

    assert html.startswith("<!doctype html>")
    assert "Regulatory Evidence Pack" in html
    assert "WLTH-101" in html
    assert "AI Governance" in html  # agent execution record section
    assert "Audit Event Log" in html
    assert "Audit chain verified" in html  # chain valid banner
    # No unescaped braces / obvious template leakage.
    assert "{" not in html.split("<style>")[0]
