"""Artifact parsers.

Each parser turns a raw uploaded file into a normalized `parsed` dict plus a
short human `summary`. Parsers never raise on malformed input — they return a
`parse_error` string so a bad upload degrades gracefully instead of 500ing.

Normalized shapes (what agents consume):
  SARIF     -> {"findings": [{rule, level, message, location}], "counts": {...}}
  JUNIT     -> {"total", "passed", "failed", "errors", "skipped",
                "failures": [{name, classname, status, message}]}
  COVERAGE  -> {"overall_percent", "classes": [{name, coverage_percent}]}
  METADATA  -> {"components": [str, ...]}
  FINANCIAL -> {"checks": [{name, expected, actual, passed}]}
  GENERIC   -> {"text": "..."}
"""

import csv
import io
import json
import xml.etree.ElementTree as ET

from ...models import ArtifactKind

RAW_EXCERPT_CAP = 20_000


def _result(parsed: dict, summary: str, error: str | None = None) -> dict:
    return {"parsed": parsed, "summary": summary, "error": error}


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


# ---------------------------------------------------------------- SARIF


def parse_sarif(text: str) -> dict:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return _result({}, "Invalid SARIF: not valid JSON.", f"json: {exc}")
    findings = []
    for run in doc.get("runs", []) or []:
        # ruleId -> level default from the driver's rules if present
        for res in run.get("results", []) or []:
            loc = ""
            locations = res.get("locations") or []
            if locations:
                phys = locations[0].get("physicalLocation", {})
                uri = phys.get("artifactLocation", {}).get("uri", "")
                line = phys.get("region", {}).get("startLine")
                loc = f"{uri}:{line}" if line else uri
            findings.append(
                {
                    "rule": res.get("ruleId", "unknown"),
                    "level": res.get("level", "warning"),
                    "message": (res.get("message") or {}).get("text", ""),
                    "location": loc,
                }
            )
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["level"]] = counts.get(f["level"], 0) + 1
    summary = (
        f"{len(findings)} static-analysis finding(s): "
        + ", ".join(f"{n} {lvl}" for lvl, n in sorted(counts.items()))
        if findings
        else "SARIF parsed: no findings."
    )
    return _result({"findings": findings, "counts": counts}, summary)


# ---------------------------------------------------------------- JUnit


def parse_junit(text: str) -> dict:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return _result({}, "Invalid JUnit: not valid XML.", f"xml: {exc}")

    suites = []
    if _strip_ns(root.tag) == "testsuites":
        suites = [c for c in root if _strip_ns(c.tag) == "testsuite"]
    elif _strip_ns(root.tag) == "testsuite":
        suites = [root]
    else:
        suites = root.findall(".//{*}testsuite") or []

    total = passed = failed = errors = skipped = 0
    failures = []
    all_tests: list[str] = []
    for suite in suites:
        for case in suite:
            if _strip_ns(case.tag) != "testcase":
                continue
            total += 1
            name = case.get("name", "")
            all_tests.append(name)
            classname = case.get("classname", "")
            status = "passed"
            message = ""
            for child in case:
                ctag = _strip_ns(child.tag)
                if ctag in ("failure", "error", "skipped"):
                    status = {"failure": "failed", "error": "error", "skipped": "skipped"}[
                        ctag
                    ]
                    message = child.get("message") or (child.text or "").strip()
                    break
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
                failures.append(
                    {"name": name, "classname": classname, "status": status, "message": message}
                )
            elif status == "error":
                errors += 1
                failures.append(
                    {"name": name, "classname": classname, "status": status, "message": message}
                )
            else:
                skipped += 1

    parsed = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "failures": failures,
        "all_tests": all_tests,
    }
    summary = (
        f"{total} tests: {passed} passed, {failed} failed, {errors} errored, "
        f"{skipped} skipped."
    )
    return _result(parsed, summary)


# ---------------------------------------------------------------- Coverage


def _parse_coverage_json(doc) -> dict | None:
    classes = []
    if isinstance(doc, dict) and "classes" in doc:
        for c in doc.get("classes", []):
            name = c.get("name") or c.get("class") or "unknown"
            pct = c.get("coverage_percent")
            if pct is None:
                pct = c.get("coverage")
            if pct is None and c.get("covered") is not None and c.get("total"):
                pct = round(c["covered"] / c["total"] * 100, 1)
            classes.append({"name": name, "coverage_percent": float(pct or 0)})
    elif isinstance(doc, list):
        for c in doc:
            classes.append(
                {
                    "name": c.get("name", "unknown"),
                    "coverage_percent": float(
                        c.get("coverage_percent", c.get("coverage", 0)) or 0
                    ),
                }
            )
    else:
        return None
    overall = (
        round(sum(c["coverage_percent"] for c in classes) / len(classes), 1)
        if classes
        else 0.0
    )
    if isinstance(doc, dict) and doc.get("overall_percent") is not None:
        overall = float(doc["overall_percent"])
    return {"overall_percent": overall, "classes": classes}


def _parse_cobertura(text: str) -> dict | None:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    if _strip_ns(root.tag) != "coverage":
        return None
    classes = []
    for cls in root.findall(".//{*}class"):
        name = cls.get("name", "unknown")
        rate = cls.get("line-rate")
        if rate is not None:
            classes.append(
                {"name": name, "coverage_percent": round(float(rate) * 100, 1)}
            )
    overall = None
    if root.get("line-rate") is not None:
        overall = round(float(root.get("line-rate")) * 100, 1)
    elif classes:
        overall = round(sum(c["coverage_percent"] for c in classes) / len(classes), 1)
    return {"overall_percent": overall or 0.0, "classes": classes}


def parse_coverage(text: str) -> dict:
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            return _result({}, "Invalid coverage JSON.", f"json: {exc}")
        parsed = _parse_coverage_json(doc)
        if parsed is None:
            return _result({}, "Unrecognized coverage JSON shape.", "shape")
    else:
        parsed = _parse_cobertura(text)
        if parsed is None:
            return _result({}, "Unrecognized coverage format (JSON or Cobertura XML).", "shape")
    summary = (
        f"Overall coverage {parsed['overall_percent']}% across "
        f"{len(parsed['classes'])} class(es)."
    )
    return _result(parsed, summary)


# ---------------------------------------------------------------- Financial


def _coerce(value):
    return str(value).strip()


def parse_financial(text: str) -> dict:
    stripped = text.lstrip()
    checks = []
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            return _result({}, "Invalid financial JSON.", f"json: {exc}")
        rows = doc if isinstance(doc, list) else doc.get("checks", [])
        for r in rows:
            expected = _coerce(r.get("expected"))
            actual = _coerce(r.get("actual"))
            passed = r.get("passed")
            if passed is None:
                passed = expected == actual
            checks.append(
                {
                    "name": r.get("name", "check"),
                    "expected": expected,
                    "actual": actual,
                    "passed": bool(passed),
                }
            )
    else:
        try:
            reader = csv.DictReader(io.StringIO(text))
            for r in reader:
                lower = {(k or "").strip().lower(): v for k, v in r.items()}
                expected = _coerce(lower.get("expected"))
                actual = _coerce(lower.get("actual"))
                passed_raw = lower.get("passed")
                passed = (
                    passed_raw.strip().lower() in ("true", "1", "yes", "pass")
                    if passed_raw
                    else expected == actual
                )
                checks.append(
                    {
                        "name": lower.get("name", "check"),
                        "expected": expected,
                        "actual": actual,
                        "passed": passed,
                    }
                )
        except csv.Error as exc:
            return _result({}, "Invalid financial CSV.", f"csv: {exc}")

    failed = [c for c in checks if not c["passed"]]
    summary = (
        f"{len(checks)} financial check(s): {len(checks) - len(failed)} passed, "
        f"{len(failed)} failed."
        + (" ⚠ release-blocking" if failed else "")
    )
    return _result({"checks": checks}, summary)


# ---------------------------------------------------------------- Metadata


def parse_metadata(text: str) -> dict:
    components: list[str] = []
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            return _result({}, "Invalid metadata JSON.", f"json: {exc}")
        rows = doc if isinstance(doc, list) else doc.get("components", [])
        for r in rows:
            if isinstance(r, str):
                components.append(r)
            elif isinstance(r, dict):
                name = r.get("name") or r.get("fullName") or r.get("component")
                typ = r.get("type")
                components.append(f"{typ}: {name}" if typ else str(name))
    else:
        for line in text.replace(",", "\n").splitlines():
            item = line.strip()
            if item:
                components.append(item)
    summary = f"{len(components)} changed component(s)."
    return _result({"components": components}, summary)


# ---------------------------------------------------------------- Generic


def parse_generic(text: str) -> dict:
    excerpt = text.strip()[:2000]
    return _result({"text": excerpt}, f"Freeform artifact ({len(text)} chars).")


PARSERS = {
    ArtifactKind.SARIF: parse_sarif,
    ArtifactKind.JUNIT: parse_junit,
    ArtifactKind.COVERAGE: parse_coverage,
    ArtifactKind.FINANCIAL: parse_financial,
    ArtifactKind.METADATA: parse_metadata,
    ArtifactKind.GENERIC: parse_generic,
}


def parse(kind: ArtifactKind, text: str) -> dict:
    return PARSERS[kind](text)


def detect_kind(filename: str, text: str) -> ArtifactKind:
    """Best-effort kind detection for AUTO uploads."""
    name = (filename or "").lower()
    stripped = text.lstrip()[:4000]
    lower = stripped.lower()
    if name.endswith(".sarif") or '"$schema"' in lower and "sarif" in lower:
        return ArtifactKind.SARIF
    if stripped.startswith("{") and '"runs"' in lower and '"results"' in lower:
        return ArtifactKind.SARIF
    if "<testsuite" in lower or "<testsuites" in lower:
        return ArtifactKind.JUNIT
    if "<coverage" in lower or "line-rate" in lower:
        return ArtifactKind.COVERAGE
    if "coverage" in name:
        return ArtifactKind.COVERAGE
    if any(k in name for k in ("junit", "test-result", "testresult", "pytest")):
        return ArtifactKind.JUNIT
    if "expected" in lower and "actual" in lower:
        return ArtifactKind.FINANCIAL
    if any(k in name for k in ("package.xml", "manifest", "metadata", "delta")):
        return ArtifactKind.METADATA
    return ArtifactKind.GENERIC
