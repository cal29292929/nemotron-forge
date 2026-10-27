"""
CLI entrypoint for Nemotron Forge (`nemotron_forge.cli`):
- `demo`: Executes full 5-stage pipeline and writes JSON/Markdown artifacts + `FEEDBACK.md`
- `selfcheck`: Probes live `/v1/models` on Nebius Token Factory and verifies environment readiness
- `serve`: Starts hardened local HTTP dashboard & REST/MCP server
- `mcp`: Starts stdio JSON-RPC 2.0 MCP server
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

from .engine import NemotronForgeEngine
from .mcp_server import run_stdio_server
from .models import TaskRequest
from .server import create_http_server


def render_markdown_report(result_dict: dict) -> str:
    cv = result_dict["code_verification"]
    pv = result_dict["physical_verification"]
    cs = result_dict["cost_summary"]
    av = result_dict["audit_verification"]

    lines = [
        f"# Nemotron Forge Execution Report — `{result_dict['run_id']}`",
        "",
        f"- **Timestamp (JST)**: `{result_dict['created_at_jst']}`",
        f"- **Objective**: {result_dict['objective']}",
        f"- **Requested / Effective Mode**: `{result_dict['requested_mode']}` / `{result_dict['effective_mode']}`",
        f"- **Telemetry Classification**: `{cs['telemetry_label']}` (`is_estimated_telemetry={result_dict['is_estimated_telemetry']}`)",
        f"- **Deterministic Result Digest**: `{result_dict['result_digest']}` (`sim_version={result_dict['sim_version']}`, `seed={result_dict['seed']}`)",
        "",
        "## 1. Tiered NVIDIA Nemotron-3 & Cosmos Stage Trace",
        "",
        "| # | Stage | Tier | Served Model | Mode | Confidence | Escalated | Tokens (P/C) | Latency (ms) | Est. Cost (USD) |",
        "| :-: | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in result_dict["stages"]:
        lines.append(
            f"| {s['stage_index']} | `{s['stage_name']}` | **{s['tier_id']}** | `{s['served_model_id']}` | `{s['execution_mode']}` | "
            f"{s['confidence']:.2f} | `{s['escalated_to_deep']}` | {s['prompt_tokens']}/{s['completion_tokens']} | "
            f"{s['latency_ms']:.1f} | ${s['estimated_cost_usd']:.6f} |"
        )

    lines.extend(
        [
            "",
            "## 2. Code & Sandbox Security Gate (`ASTSecurityGate` + `SandboxRunner`)",
            "",
            f"- **AST Safe**: `{cv['ast_safe']}` (Violations: `{len(cv['ast_violations'])}`)",
            f"- **Execution Policy**: `{cv['execution_policy']}`",
            f"- **Unit Tests Passed**: `{cv['tests_passed']} / {cv['tests_run']}` (`exit_code={cv['exit_code']}`, `{cv['duration_ms']} ms`)",
            f"- **Stdout Excerpt**: `{cv['stdout_excerpt']}`",
            "",
            "## 3. Physical AI Kinematic & NVIDIA Cosmos Critic Verification",
            "",
            f"- **Trajectory Passed**: `{pv['passed']}` (Plausibility Score: `{pv['plausibility_score']}`)",
            f"- **Peak Velocity**: `{pv['max_velocity_mps']} m/s` (Limit: `{pv['velocity_limit_mps']} m/s`)",
            f"- **Peak Acceleration**: `{pv['max_acceleration_mps2']} m/s²` (Limit: `{pv['acceleration_limit_mps2']} m/s²`)",
            f"- **Min Obstacle Clearance**: `{pv['min_obstacle_clearance_m']} m` (Min Required: `{pv['clearance_limit_m']} m`)",
            f"- **Peak Payload Torque**: `{pv['payload_torque_nm']} Nm` (Limit: `{pv['torque_limit_nm']} Nm`)",
            f"- **Cosmos Critic Summary**: {pv['cosmos_critic_summary']}",
            "",
            "## 4. Tavily 4-State Citation Grounding (`supported` / `weak` / `unsupported` / `unverified`)",
            "",
            "| ID | Status | Overlap | Source Title | Reason |",
            "| :--- | :---: | :---: | :--- | :--- |",
        ]
    )
    for c in result_dict["citations"] + result_dict["omitted_claims"]:
        lines.append(f"| `{c['citation_id']}` | **{c['status']}** | {c['overlap_score']:.2f} | {c['title']} | {c['reason']} |")

    lines.extend(
        [
            "",
            "## 5. Tiered Cost Efficiency & Cryptographic Audit Verification",
            "",
            f"- **Tiered Pipeline Cost**: `${cs['tiered_cost_usd']:.6f}` vs Monolithic DEEP Baseline `${cs['monolithic_deep_baseline_cost_usd']:.6f}` (**{cs['estimated_cost_savings_pct']:.2f}% savings**)",
            f"- **SHA-256 Hash Chain Verified**: `{av['chain_verified']}` ({av['entry_count']} entries, head `{av['head_hash'][:16]}...`)",
            f"- **HMAC Configured / Verified**: `hmac_configured={av['hmac_configured']}` / `hmac_verified={av['hmac_verified']}`",
            "",
        ]
    )
    return "\n".join(lines)


def render_feedback_markdown(engine: NemotronForgeEngine) -> str:
    lines = [
        "# Nebius Token Factory — Structured Platform Feedback Report (`FEEDBACK.md`)",
        "",
        "> **Submission Track**: Nebius Token Factory Platform Feedback Prize ($500) + Main Track",
        "> **Provenance Note**: Every entry explicitly distinguishes `live_api_observation` from `architecture_pre_flight` analysis.",
        "",
        "| ID | Source | Endpoint | Requested Model | Served Model | Category | Observation | Actionable Recommendation |",
        "| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for e in engine.feedback.events:
        lines.append(
            f"| `{e.event_id}` | `{e.source}` | `{e.endpoint}` | `{e.requested_model}` | `{e.served_model}` | "
            f"`{e.category}` | {e.observation} | {e.recommendation} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="nemotron-forge", description="Nemotron Forge CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_demo = sub.add_parser("demo", help="Run full verification pipeline and write artifacts")
    p_demo.add_argument(
        "--objective",
        default="Design and verify a velocity-bounded 3D robotic trajectory controller with ISO 10218 torque & obstacle clearance guarantees.",
    )
    p_demo.add_argument("--mode", choices=["simulated", "hybrid", "live"], default="simulated")
    p_demo.add_argument("--seed", type=int, default=42)
    p_demo.add_argument("--out-dir", default="artifacts")

    p_check = sub.add_parser("selfcheck", help="Probe Nebius Token Factory /v1/models and environment status")
    p_check.add_argument("--json", action="store_true", help="Output raw JSON")

    p_serve = sub.add_parser("serve", help="Start HTTP dashboard & REST/MCP server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)
    p_serve.add_argument("--allow-unauthenticated-public-bind", action="store_true")

    sub.add_parser("mcp", help="Run stdio JSON-RPC 2.0 MCP server")

    args = parser.parse_args(argv)
    engine = NemotronForgeEngine()

    if args.cmd == "mcp":
        run_stdio_server()
        return 0

    if args.cmd == "selfcheck":
        probe = engine.nebius.probe_models()
        print(json.dumps(probe, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "serve":
        srv = create_http_server(
            host=args.host,
            port=args.port,
            engine=engine,
            allow_unauthenticated_public=args.allow_unauthenticated_public_bind,
        )
        print(f"Nemotron Forge Studio listening on http://{args.host}:{args.port}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
        return 0

    if args.cmd == "demo":
        req = TaskRequest(objective=args.objective, task_type="hybrid", mode=args.mode, seed=args.seed)
        res = engine.execute(req)
        res_dict = res.to_dict()
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "latest_run.json").write_text(json.dumps(res_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        (out_dir / "latest_run.md").write_text(render_markdown_report(res_dict), encoding="utf-8")
        fb_path = Path("FEEDBACK.md")
        fb_path.write_text(render_feedback_markdown(engine), encoding="utf-8")
        print(json.dumps({"run_id": res.run_id, "effective_mode": res.effective_mode, "result_digest": res.result_digest}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
