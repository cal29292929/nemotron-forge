# Sakura AI Engine (`preview/Kimi-K2.7-Code`) Implementation Synthesis — `nemotron_forge`

## Module Synthesis 1 (`chatcmpl-8da9d7e9365a7124` — `preview/Kimi-K2.7-Code`)

 ```python
import ast
from typing import Any


BLOCKED_MODULES = {"os", "subprocess", "socket", "sys"}
BLOCKED_CALLS = {"eval", "exec", "__import__"}


def ast_security_scan(code_str: str) -> list[str]:
    """Scan Python source for unsafe constructs and return violation messages."""
    try:
        tree = ast.parse(code_str)
    except SyntaxError as exc:
        return [f"Syntax error at line {exc.lineno or '?'}: {exc.msg}"]

    violations: list[str] = []
    seen: set[str] = set()
    alias_map: dict[str, str] = {}

    def add(msg: str) -> None:
        if msg not in seen:
            seen.add(msg)
            violations.append(msg)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in BLOCKED_MODULES:
                    asname = alias.asname or alias.name
                    alias_map[asname] = alias.name
                    add(f"Line {node.lineno}: import of blocked module '{alias.name}'")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top = node.module.split(".")[0]
                if top in BLOCKED_MODULES:
                    for alias in node.names:
                        asname = alias.asname or alias.name
                        full = f"{node.module}.{alias.name}" if node.module else alias.name
                        alias_map[asname] = full
                        add(
                            f"Line {node.lineno}: import from blocked module "
                            f"'{node.module}' ('{alias.name}')"
                        )

        elif isinstance(node, ast.Name):
            if node.id in alias_map:
                add(
                    f"Line {node.lineno}: use of blocked module "
                    f"'{alias_map[node.id]}' via alias '{node.id}'"
                )

        elif isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr.endswith("__"):
                add(f"Line {node.lineno}: dunder attribute access '{attr}'")

        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_CALLS:
                add(f"Line {node.lineno}: blocked call '{func.id}'")
            elif isinstance(func, ast.Attribute) and func.attr in BLOCKED_CALLS:
                add(f"Line {node.lineno}: blocked call '{func.attr}'")

    return violations


def verify_kinematic_trajectory(waypoints: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify that a trajectory satisfies kinematic safety limits."""
    LIMITS = {
        "velocity": ("<=", 1.5),
        "acceleration": ("<=", 4.0),
        "torque": ("<=", 45.0),
        "clearance": (">=", 0.15),
    }

    violations: list[str] = []
    max_values: dict[str, float | None] = {k: None for k in LIMITS}

    if not isinstance(waypoints, list):
        return {
            "valid": False,
            "violations": ["waypoints must be a list"],
            "max_values": max_values,
        }

    for idx, wp in enumerate(waypoints):
        if not isinstance(wp, dict):
            violations.append(f"Waypoint {idx}: expected dict, got {type(wp).__name__}")
            continue

        for key, (op, limit) in LIMITS.items():
            if key not in wp:
                violations.append(f"Waypoint {idx}: missing '{key}'")
                continue

            try:
                value = float(wp[key])
            except (TypeError, ValueError):
                violations.append(
                    f"Waypoint {idx}: '{key}' must be numeric, got {wp[key]!r}"
                )
                continue

            if max_values[key] is None or value > max_values[key]:
                max_values[key] = value

            if op == "<=" and value > limit:
                violations.append(
                    f"Waypoint {idx}: {key}={value} exceeds limit {limit}"
                )
            elif op == ">=" and value < limit:
                violations.append(
                    f"Waypoint {idx}: {key}={value} below minimum {limit}"
                )

    return {
        "valid": not violations,
        "violations": violations,
        "max_values": max_values,
        "waypoint_count": len(waypoints),
    }
```

## Module Synthesis 2 (`chatcmpl-a927c7f1da56fc56` — `preview/Kimi-K2.7-Code`)

 ```python
def verify_citation_claim(claim: str, passage: str, extract_failed: bool = False) -> dict:
    """
    Verify a claim against a passage using token overlap (Jaccard similarity).

    Thresholds:
        >= 0.65  -> supported
        >= 0.35  -> weak
        <  0.35  -> unsupported
        extract_failed -> unverified
    """
    if extract_failed:
        return {"status": "unverified", "overlap": None}

    claim_tokens = set(claim.lower().split())
    passage_tokens = set(passage.lower().split())

    union = claim_tokens | passage_tokens
    if not union:
        overlap = 0.0
    else:
        overlap = len(claim_tokens & passage_tokens) / len(union)

    if overlap >= 0.65:
        status = "supported"
    elif overlap >= 0.35:
        status = "weak"
    else:
        status = "unsupported"

    return {"status": status, "overlap": overlap}
```
