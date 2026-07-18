"""Flaky-Test Intelligence — cross-run memory of recurring failures.

Every Test Execution Analyst run classifies flakiness and then forgets. This
ledger remembers: failures are fingerprinted (test name + normalised message,
volatile parts stripped) and tracked across runs and stories with a flake
score. Humans can QUARANTINE a signature — but only with an OWNER and an
EXPIRY (quarantine that never expires is how test suites rot); expired
quarantines are flagged for review, never silently extended.

The ledger feeds back into the pipeline as advisory evidence: when the Test
Execution Analyst or Defect Triage runs, matching known signatures are
injected as upstream context ("matches FLK-…, seen 7× across 3 stories —
re-run, not defect"). Evidence, not behaviour change — no FCA self-tuning.
"""

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, FlakySignature
from ..util import utcnow
from . import audit

FEED_AGENTS = ("test_execution_analyst", "defect_triage")  # Decision C


class FlakyError(Exception):
    pass


def normalize_message(text: str) -> str:
    """Strip the volatile parts so the same failure matches across runs:
    numbers, ids, durations, timestamps, hex, quoted values."""
    t = (text or "").lower()
    t = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<id>", t)
    t = re.sub(r"0x[0-9a-f]+", "<hex>", t)
    t = re.sub(r"\d+(\.\d+)?(ms|s|sec|seconds)\b", "<duration>", t)
    # Any token containing a digit (numbers, Salesforce ids, dates) folds to <n>.
    t = re.sub(r"[\w.,-]*\d[\w.,-]*", "<n>", t)
    t = re.sub(r"'[^']*'|\"[^\"]*\"", "<val>", t)
    return re.sub(r"\s+", " ", t).strip()[:500]


def signature_of(test_name: str, message: str) -> str:
    base = f"{(test_name or '').strip().lower()}|{normalize_message(message)}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _score(sig: FlakySignature) -> int:
    """0-100: recurrence + the analyst's own flaky classifications + spread."""
    return min(
        100,
        15 * min(sig.occurrences, 4)
        + 25 * min(sig.flaky_votes, 2)
        + 10 * max(0, len(sig.stories_seen) - 1),
    )


async def record_from_run(session: AsyncSession, run: AgentRun, jira_key: str) -> int:
    """Ingest a completed Test Execution Analyst run into the ledger.
    Idempotent per run (runs_seen). Returns signatures created/updated."""
    if run.agent_key != "test_execution_analyst" or not run.output_json:
        return 0
    touched = 0
    for f in run.output_json.get("failures") or []:
        name = f.get("test_name") or "unknown-test"
        sig_hash = signature_of(name, f.get("detail") or "")
        sig = (
            await session.execute(
                select(FlakySignature).where(FlakySignature.signature == sig_hash)
            )
        ).scalar_one_or_none()
        if sig is None:
            sig = FlakySignature(
                signature=sig_hash,
                test_name=name[:250],
                normalized_message=normalize_message(f.get("detail") or ""),
            )
            session.add(sig)
            await session.flush()
        if run.id in (sig.runs_seen or []):
            continue  # this run already counted
        sig.runs_seen = [*(sig.runs_seen or []), run.id]
        sig.occurrences += 1
        if f.get("likely_flaky"):
            sig.flaky_votes += 1
        if jira_key not in (sig.stories_seen or []):
            sig.stories_seen = [*(sig.stories_seen or []), jira_key]
        sig.last_seen = utcnow()
        sig.flake_score = _score(sig)
        touched += 1
    return touched


async def known_signatures(session: AsyncSession) -> list[dict]:
    """The feed for the pipeline: active signatures worth telling the
    analyst/triage about (anything quarantined, or scored as suspicious)."""
    rows = (
        (await session.execute(select(FlakySignature))).scalars().all()
    )
    out = []
    for s in rows:
        if s.status == "CLEARED":
            continue
        if s.status != "QUARANTINED" and s.flake_score < 25:
            continue
        out.append({
            "id": f"FLK-{s.signature[:8]}",
            "test_name": s.test_name,
            "status": s.status,
            "flake_score": s.flake_score,
            "occurrences": s.occurrences,
            "stories_seen": len(s.stories_seen or []),
            "owner": s.owner,
            "quarantine_expiry": s.quarantine_expiry.isoformat()
            if s.quarantine_expiry else None,
        })
    return out


def _serialize(s: FlakySignature) -> dict:
    now = utcnow().replace(tzinfo=None)
    expired = (
        s.status == "QUARANTINED"
        and s.quarantine_expiry is not None
        and s.quarantine_expiry.replace(tzinfo=None) < now
    )
    return {
        "id": s.id, "ref": f"FLK-{s.signature[:8]}", "signature": s.signature,
        "test_name": s.test_name, "normalized_message": s.normalized_message,
        "occurrences": s.occurrences, "flaky_votes": s.flaky_votes,
        "stories_seen": s.stories_seen or [], "runs_seen": len(s.runs_seen or []),
        "first_seen": s.first_seen.isoformat() if s.first_seen else None,
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        "flake_score": s.flake_score, "status": s.status,
        "owner": s.owner,
        "quarantine_expiry": s.quarantine_expiry.isoformat()
        if s.quarantine_expiry else None,
        "quarantine_expired": expired,
        "note": s.note,
    }


async def ledger(session: AsyncSession) -> dict:
    rows = (
        (await session.execute(
            select(FlakySignature).order_by(FlakySignature.flake_score.desc())
        )).scalars().all()
    )
    entries = [_serialize(s) for s in rows]
    return {
        "signatures": entries,
        "summary": {
            "total": len(entries),
            "quarantined": sum(1 for e in entries if e["status"] == "QUARANTINED"),
            "expired_quarantines": sum(1 for e in entries if e["quarantine_expired"]),
            "high_score": sum(1 for e in entries if e["flake_score"] >= 50),
        },
    }


async def _get(session: AsyncSession, sig_id: str) -> FlakySignature:
    s = await session.get(FlakySignature, sig_id)
    if s is None:
        raise FlakyError("flaky signature not found")
    return s


async def quarantine(
    session: AsyncSession, sig_id: str, actor: str, owner: str,
    expiry_days: int, note: str,
) -> dict:
    """Owner + expiry are mandatory — no immortal quarantine."""
    if not owner or not owner.strip():
        raise FlakyError("an owner is required to quarantine a test")
    if not expiry_days or expiry_days < 1 or expiry_days > 90:
        raise FlakyError("expiry must be 1-90 days — quarantine always expires")
    from datetime import timedelta

    s = await _get(session, sig_id)
    s.status = "QUARANTINED"
    s.owner = owner.strip()
    s.quarantine_expiry = utcnow() + timedelta(days=expiry_days)
    s.note = note
    await audit.record_event(
        session, event_type="FLAKY_QUARANTINED", entity_type="flaky_signature",
        entity_id=s.id, actor=actor,
        payload={"test_name": s.test_name, "owner": s.owner,
                 "expiry": s.quarantine_expiry.isoformat(), "note": note},
    )
    return _serialize(s)


async def clear(session: AsyncSession, sig_id: str, actor: str, note: str) -> dict:
    """The flakiness is fixed (or the signature was wrong) — stop tracking."""
    s = await _get(session, sig_id)
    s.status = "CLEARED"
    s.note = note
    await audit.record_event(
        session, event_type="FLAKY_CLEARED", entity_type="flaky_signature",
        entity_id=s.id, actor=actor,
        payload={"test_name": s.test_name, "note": note},
    )
    return _serialize(s)
