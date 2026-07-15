from dataclasses import asdict

from fastapi import APIRouter

from ..services.agents.registry import AGENTS

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agent_definitions():
    """The agent roster with PACT badges — drives the UI legend."""
    return [asdict(a) for a in AGENTS.values()]
