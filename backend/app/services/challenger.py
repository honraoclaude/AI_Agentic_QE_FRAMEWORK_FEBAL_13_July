"""Adversarial Challenger — the red-team pass at the gate.

Every pipeline agent argues FOR its conclusions. Before a human signs a gate,
the Challenger argues AGAINST: for each executed run in the phase it tries to
falsify the result — self-reported caveats, severe findings sitting under an
accepting verdict, cross-agent contradictions, unresolved blocking questions,
uncovered evidence anchors. The output is a challenge list pinned to the
sign-off: "before you sign, here is the strongest case against these results."

This upgrades HITL from review to cross-examination. It is advisory only —
it cannot block, and it changes nothing; the human weighs it and signs (or
doesn't). Demo path is deterministic (reproducible, auditable); with an API
key a classification-tier model adds novel challenges on top.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import AgentRun, Phase
from .agents.output_schemas import severity_rank
from .agents.registry import get_agent
from . import referee

# Challenges ordered strongest-first by this rank.
_PRIORITY = {"CONTRADICTION": 0, "BLOCKING_QUESTION": 1, "SEVERE_FINDING": 2,
             "UNCOVERED_EVIDENCE": 3, "SELF_REPORTED_CAVEAT": 4}


def _name(key: str) -> str:
    try:
        return get_agent(key).name
    except KeyError:
        return key


def _challenge(kind: str, agent_key: str, text: str, basis: str) -> dict:
    return {"kind": kind, "agent_key": agent_key, "agent_name": _name(agent_key),
            "challenge": text, "basis": basis}


def deterministic_challenges(latest: dict[str, AgentRun], phase: Phase) -> list[dict]:
    """Reproducible red-team pass over the phase's executed runs."""
    phase_runs = {k: r for k, r in latest.items() if r.phase == phase}
    out: list[dict] = []

    for key, run in phase_runs.items():
        o = run.output_json or {}
        verdict = o.get("verdict") or "WARN"
        conf = (o.get("confidence") or {})
        caveats = conf.get("caveats") or []

        # 1. The agent itself told you why it might be wrong — surface that
        #    at the moment of signing, not buried in a drawer.
        if conf.get("level") in ("LOW", "MEDIUM") and caveats:
            out.append(_challenge(
                "SELF_REPORTED_CAVEAT", key,
                f"{_name(key)} passed with {conf.get('level')} confidence and "
                f"warned: “{str(caveats[0])[:160]}”. Have you discounted that caveat?",
                "agent confidence.caveats"))

        # 2. A PASS/WARN verdict sitting on top of a HIGH+ finding.
        worst = max((severity_rank(f.get("severity")) for f in o.get("findings") or []),
                    default=0)
        if verdict != "FAIL" and worst >= severity_rank("HIGH"):
            sev_f = max((o.get("findings") or []),
                        key=lambda f: severity_rank(f.get("severity")))
            out.append(_challenge(
                "SEVERE_FINDING", key,
                f"{_name(key)} verdict is {verdict}, yet it raised a "
                f"{sev_f.get('severity')} finding: “{str(sev_f.get('title'))[:120]}”. "
                "Why does that finding not change the verdict?",
                "findings vs verdict"))

        # 3. Unresolved blocking questions (Three Amigos).
        for q in o.get("open_questions") or []:
            if isinstance(q, dict) and q.get("blocking"):
                out.append(_challenge(
                    "BLOCKING_QUESTION", key,
                    f"A BLOCKING question is unresolved: “{str(q.get('question'))[:140]}” "
                    "— signing this gate accepts scenarios drafted on an assumption.",
                    "open_questions.blocking"))

        # 4. Uncovered evidence anchors (BDD example cards).
        cov = o.get("coverage") or {}
        if isinstance(cov, dict) and cov.get("uncovered_examples"):
            out.append(_challenge(
                "UNCOVERED_EVIDENCE", key,
                f"{len(cov['uncovered_examples'])} example card(s) have no realising "
                f"scenario ({', '.join(cov['uncovered_examples'][:4])}). Is that gap "
                "deliberate and recorded?",
                "coverage.uncovered_examples"))

    # 5. Cross-agent contradictions touching this phase's agents. Referee rules
    #    use short display names ("Financial Data Integrity"); match loosely.
    phase_names = {_name(k) for k in phase_runs}
    def _touches(inc_agents: list[str]) -> bool:
        return any(a in pn or pn in a for a in inc_agents for pn in phase_names)
    for inc in referee.find_inconsistencies(latest):
        if _touches(inc.get("agents") or []):
            out.append(_challenge(
                "CONTRADICTION", "referee",
                f"{inc['detail']} {inc['recommendation']}",
                f"referee rule: {inc['rule']}"))

    out.sort(key=lambda c: _PRIORITY.get(c["kind"], 9))
    return out


async def challenges_for_gate(session: AsyncSession, story_id: str, phase: Phase) -> dict:
    latest = await referee._latest_runs(session, story_id)
    challenges = deterministic_challenges(latest, phase)
    generated_by = "deterministic"

    # Real-model augmentation is deliberately deferred: the deterministic pass
    # is reproducible and auditable, which a regulated gate values more than
    # novelty. (An LLM layer can append novel challenges later, clearly tagged.)
    settings = get_settings()
    _ = settings  # reserved for the LLM augmentation path

    return {
        "story_id": story_id,
        "phase": phase.value,
        "challenges": challenges,
        "count": len(challenges),
        "generated_by": generated_by,
        "note": "Advisory red-team pass. It cannot block the gate — weigh each "
        "challenge, then sign with your rationale.",
    }
