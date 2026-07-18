"""Replay Verifier — prove reproducibility, don't just claim it.

Re-executes a historical run with freshly gathered inputs (same story, same
agent, the pinned upstream/artifact gathering rules) and compares hashes:

- REPRODUCED      — input hash AND output hash match: the recorded decision
                    replays byte-for-byte. The audit guarantee, demonstrated.
- INPUT_DRIFT     — the inputs differ from what the run saw (story edited,
                    artifacts added, upstream re-accepted, prompt upgraded).
                    The `drift` list names exactly which inputs moved.
- OUTPUT_DIVERGED — same inputs, different output. On the deterministic demo
                    path this means the stored output was tampered with or the
                    generator changed; on the real-model path some divergence
                    is expected (LLM nondeterminism) and the comparison is
                    advisory.

Nothing is persisted to the run — a replay is a pure verification. The
attempt and its result ARE recorded to the audit trail (RUN_REPLAYED).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, RunStatus, Story
from . import audit
from .agents import engine
from .agents.registry import get_agent
from .workflow import NotFoundError, _gather_upstream


class ReplayError(Exception):
    pass


def _drift_reasons(stored: dict, fresh: dict) -> list[str]:
    """Name the top-level input fields that changed since the original run."""
    reasons = []
    for field in ("prompt_version", "story", "guidance", "artifacts", "upstream"):
        if stored.get(field) != fresh.get(field):
            reasons.append(field)
    return reasons


async def replay_run(session: AsyncSession, run_id: str, actor: str) -> dict:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError("agent run not found")
    if run.status not in (RunStatus.COMPLETED, RunStatus.ACCEPTED, RunStatus.REJECTED):
        raise ReplayError("only executed runs (with recorded output) can be replayed")
    if not run.output_hash or not run.input_json:
        raise ReplayError("run has no recorded input/output to verify against")

    story = await session.get(Story, run.story_id)
    agent = get_agent(run.agent_key)

    from .artifacts import service as artifact_service

    artifacts = await artifact_service.gather_for_agent(session, story.id, agent.key)
    upstream = await _gather_upstream(session, story.id, agent.key)
    result = await engine.execute(
        run, story, agent,
        guidance=run.guidance, artifacts=artifacts, upstream=upstream,
    )

    input_match = result["input_hash"] == run.input_hash
    output_match = result["output_hash"] == run.output_hash
    if input_match and output_match:
        status = "REPRODUCED"
    elif not input_match:
        status = "INPUT_DRIFT"
    else:
        status = "OUTPUT_DIVERGED"

    verdict_stored = (run.output_json or {}).get("verdict")
    verdict_replay = result["output"].get("verdict")
    report = {
        "run_id": run.id,
        "agent_key": run.agent_key,
        "status": status,
        "input_match": input_match,
        "output_match": output_match,
        "drift": [] if input_match else _drift_reasons(run.input_json, result["input"]),
        "original_input_hash": run.input_hash,
        "replay_input_hash": result["input_hash"],
        "original_output_hash": run.output_hash,
        "replay_output_hash": result["output_hash"],
        "verdict_stable": verdict_stored == verdict_replay,
        "original_verdict": verdict_stored,
        "replay_verdict": verdict_replay,
        "model": result["model"],
        "deterministic": result["model"] == "demo-fixture",
    }
    await audit.record_event(
        session,
        event_type="RUN_REPLAYED",
        entity_type="agent_run",
        entity_id=run.id,
        actor=actor,
        payload={k: report[k] for k in (
            "agent_key", "status", "input_match", "output_match", "drift",
            "original_output_hash", "replay_output_hash", "verdict_stable",
        )},
    )
    return report
