"""
JSON-RPC 2.0 Model Context Protocol (MCP) Server for Nemotron Forge (`2025-06-18`).
Supports clean stdio transport (zero stdout pollution) and HTTP `/mcp` dispatch.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

from .engine import NemotronForgeEngine, PhysicalVerifier, SandboxRunner
from .models import TaskRequest, redact_sensitive_text
from .providers import TavilyGroundingClient, verify_claim_against_sources


MCP_PROTOCOL_VERSION = "2025-06-18"

MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "forge_orchestrate_task",
        "description": "Execute tiered NVIDIA Nemotron-3 orchestration on Nebius Token Factory with citation, code, and physical verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string", "description": "Engineering or physical AI objective to solve and verify."},
                "task_type": {"type": "string", "enum": ["code", "physical", "research", "hybrid"], "default": "hybrid"},
                "mode": {"type": "string", "enum": ["simulated", "hybrid", "live"], "default": "simulated"},
                "seed": {"type": "integer", "default": 42},
            },
            "required": ["objective"],
        },
    },
    {
        "name": "forge_verify_code",
        "description": "Run static AST security gate and resource-limited isolated subprocess unit test verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python implementation source code."},
                "tests": {"type": "string", "description": "Optional Python test assertions.", "default": ""},
            },
            "required": ["code"],
        },
    },
    {
        "name": "forge_verify_physical_plan",
        "description": "Validate 3D robotic trajectory waypoints against ISO 10218 velocity, acceleration, torque, workspace, and obstacle clearance bounds.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "waypoints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "t_sec": {"type": "number"},
                            "x_m": {"type": "number"},
                            "y_m": {"type": "number"},
                            "z_m": {"type": "number"},
                        },
                        "required": ["t_sec", "x_m", "y_m", "z_m"],
                    },
                },
                "payload_mass_kg": {"type": "number", "default": 2.8},
            },
            "required": [],
        },
    },
    {
        "name": "forge_ground_query",
        "description": "Retrieve technical references via Tavily and run 4-state citation claim verification (supported/weak/unsupported/unverified).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "claim": {"type": "string"},
                "mode": {"type": "string", "enum": ["simulated", "hybrid", "live"], "default": "simulated"},
            },
            "required": ["query", "claim"],
        },
    },
]


class NemotronForgeMCPServer:
    def __init__(self, engine: Optional[NemotronForgeEngine] = None) -> None:
        self.engine = engine or NemotronForgeEngine()

    def handle_jsonrpc(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": request.get("id") if isinstance(request, dict) else None,
                "error": {"code": -32600, "message": "Invalid JSON-RPC 2.0 request."},
            }

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params") or {}

        # Notifications have no id and expect no response
        if method == "notifications/initialized" or req_id is None and method.startswith("notifications/"):
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "nemotron-forge-mcp", "version": "1.0.0"},
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments") or {}
            try:
                result_obj = self._call_tool(tool_name, args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result_obj, ensure_ascii=False)}],
                        "isError": False,
                    },
                }
            except KeyError as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {exc}"},
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": redact_sensitive_text(str(exc))}, ensure_ascii=False)}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name == "forge_orchestrate_task":
            req = TaskRequest(
                objective=str(args.get("objective", "")),
                task_type=str(args.get("task_type", "hybrid")),
                mode=str(args.get("mode", "simulated")),
                seed=int(args.get("seed", 42)),
            )
            return self.engine.execute(req).to_dict()

        if name == "forge_verify_code":
            code = str(args.get("code", ""))
            tests = str(args.get("tests", ""))
            return self.engine.sandbox.verify_code(code, tests).to_dict()

        if name == "forge_verify_physical_plan":
            waypoints = args.get("waypoints")
            payload_mass_kg = float(args.get("payload_mass_kg", 2.8))
            return PhysicalVerifier.verify_trajectory(waypoints_raw=waypoints, payload_mass_kg=payload_mass_kg).to_dict()

        if name == "forge_ground_query":
            query = str(args.get("query", ""))
            claim = str(args.get("claim", ""))
            mode = str(args.get("mode", "simulated"))
            sources, exec_mode, extract_failed = self.engine.tavily.search_and_extract(query, mode=mode)
            verdict = verify_claim_against_sources("CIT-MCP-01", claim, sources, extract_failed=extract_failed, execution_mode=exec_mode)
            return verdict.to_dict()

        raise KeyError(name)


def run_stdio_server() -> None:
    server = NemotronForgeMCPServer()
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()
            continue

        resp = server.handle_jsonrpc(payload)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
