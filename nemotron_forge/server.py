"""
Zero-dependency HTTP & REST API Server + Interactive Web Studio UI for Nemotron Forge.
Includes security hardening required by GPT-5.6 Luna review:
- Loopback-only binding by default; non-loopback binding requires FORGE_API_TOKEN or explicit override
- Maximum request body size cap (256 KiB)
- Origin / Host header validation to prevent DNS rebinding / CSRF
- Bounded concurrency semaphore (MAX_CONCURRENT_RUNS = 4)
"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
from typing import Any, Dict, Optional
import urllib.parse

from .engine import NemotronForgeEngine
from .mcp_server import NemotronForgeMCPServer
from .models import DEFAULT_MODEL_TIERS, TaskRequest


MAX_BODY_BYTES = 262_144  # 256 KiB
MAX_CONCURRENT_RUNS = 4
_RUN_SEMAPHORE = threading.BoundedSemaphore(MAX_CONCURRENT_RUNS)

ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Nemotron Forge — Nebius Token Factory x NVIDIA Multi-Agent Verification Studio</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root {
    --bg: #0b0f17;
    --panel: #131b2e;
    --border: #243252;
    --accent: #76b900;
    --nebius: #38bdf8;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --ok: #22c55e;
    --warn: #f59e0b;
    --err: #ef4444;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
  }
  header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 18px 24px; background: var(--panel); border: 1px solid var(--border);
    border-radius: 12px; margin-bottom: 20px;
  }
  .badge {
    display: inline-block; padding: 4px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 700; margin-left: 8px;
    background: rgba(118, 185, 0, 0.18); color: var(--accent); border: 1px solid var(--accent);
  }
  .badge-nebius {
    background: rgba(56, 189, 248, 0.16); color: var(--nebius); border-color: var(--nebius);
  }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .panel {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px;
  }
  h2 { margin-top: 0; font-size: 18px; color: #fff; }
  textarea, select, button {
    width: 100%; padding: 10px 12px; border-radius: 8px;
    border: 1px solid var(--border); background: #090d16; color: var(--text);
    font-size: 14px; margin-bottom: 12px;
  }
  button {
    background: var(--accent); color: #05080d; font-weight: 700;
    cursor: pointer; border: none;
  }
  pre {
    background: #070a12; padding: 12px; border-radius: 8px;
    border: 1px solid var(--border); overflow-x: auto; font-size: 12px;
  }
</style>
</head>
<body>
<header>
  <div>
    <h1 style="margin:0;font-size:22px;">Nemotron Forge Studio</h1>
    <div style="color:var(--muted);font-size:13px;margin-top:4px;">
      Tiered Multi-Agent Orchestrator &amp; Physical/Code Verification on Nebius Token Factory + NVIDIA Nemotron-3 &amp; Cosmos
    </div>
  </div>
  <div>
    <span class="badge">NVIDIA Nemotron-3 (Nano / Super / Ultra)</span>
    <span class="badge badge-nebius">Nebius Token Factory</span>
  </div>
</header>
<div class="grid">
  <div class="panel">
    <h2>1. Submit Multi-Agent Verification Task</h2>
    <label>Engineering / Physical AI Objective</label>
    <textarea id="objective" rows="4">Synthesize and verify a velocity-bounded 3D robotic arm trajectory controller with ISO 10218 torque &amp; obstacle clearance guarantees.</textarea>
    <label>Execution Mode</label>
    <select id="mode">
      <option value="simulated">Simulated (Deterministic Seed=42)</option>
      <option value="hybrid">Hybrid (Live Nebius/Tavily if keys set, else fallback)</option>
    </select>
    <button id="runBtn">Run Tiered Nemotron-3 Pipeline</button>
    <pre id="statusBox">Ready. Click Run to execute 5-stage pipeline.</pre>
  </div>
  <div class="panel">
    <h2>2. Verification Telemetry &amp; Audit Digest</h2>
    <pre id="resultBox">Awaiting execution...</pre>
  </div>
</div>
<script>
document.getElementById("runBtn").addEventListener("click", async () => {
  const statusBox = document.getElementById("statusBox");
  const resultBox = document.getElementById("resultBox");
  statusBox.textContent = "Executing FAST -> Tavily -> MID -> Sandbox/Cosmos -> DEEP...";
  try {
    const resp = await fetch("/api/v1/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        objective: document.getElementById("objective").value,
        task_type: "hybrid",
        mode: document.getElementById("mode").value,
        seed: 42
      })
    });
    const data = await resp.json();
    statusBox.textContent = "Run ID: " + data.run_id + " | Mode: " + data.effective_mode + " | Digest: " + (data.result_digest || "").slice(0, 16) + "...";
    resultBox.textContent = JSON.stringify({
      effective_mode: data.effective_mode,
      is_estimated_telemetry: data.is_estimated_telemetry,
      code_verification: data.code_verification,
      physical_verification: {
        passed: data.physical_verification?.passed,
        plausibility_score: data.physical_verification?.plausibility_score,
        max_velocity_mps: data.physical_verification?.max_velocity_mps,
        payload_torque_nm: data.physical_verification?.payload_torque_nm
      },
      cost_summary: data.cost_summary,
      audit_verification: data.audit_verification
    }, null, 2);
  } catch (err) {
    statusBox.textContent = "Error: " + String(err);
  }
});
</script>
</body>
</html>
"""


def validate_bind_policy(host: str, api_token: Optional[str], allow_unauthenticated_public: bool = False) -> None:
    """
    Refuses non-loopback binding unless an API token is configured or explicit override is passed.
    """
    normalized = host.strip().lower()
    if normalized not in ALLOWED_LOOPBACK_HOSTS:
        if not (api_token and api_token.strip()) and not allow_unauthenticated_public:
            raise PermissionError(
                f"Refusing to bind to non-loopback address '{host}' without FORGE_API_TOKEN "
                "or allow_unauthenticated_public=True."
            )


class NemotronForgeRequestHandler(BaseHTTPRequestHandler):
    engine: NemotronForgeEngine = NemotronForgeEngine()
    mcp_server: NemotronForgeMCPServer = NemotronForgeMCPServer(engine=engine)
    api_token: str = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _check_security_headers_and_auth(self, is_post: bool = False) -> Optional[Tuple[int, str]]:
        # Check Host header against DNS rebinding when bound to loopback
        host_hdr = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        if host_hdr and host_hdr not in ALLOWED_LOOPBACK_HOSTS and not self.api_token:
            return HTTPStatus.FORBIDDEN, "Untrusted Host header rejected."

        # Check Origin header on POST requests
        if is_post:
            origin = (self.headers.get("Origin") or "").strip()
            if origin:
                parsed = urllib.parse.urlparse(origin)
                origin_host = (parsed.hostname or "").lower()
                if origin_host not in ALLOWED_LOOPBACK_HOSTS and not self.api_token:
                    return HTTPStatus.FORBIDDEN, "Cross-origin POST rejected."

        # Check Bearer token if configured
        if self.api_token:
            auth_hdr = self.headers.get("Authorization") or ""
            expected = f"Bearer {self.api_token}"
            if auth_hdr != expected:
                return HTTPStatus.UNAUTHORIZED, "Missing or invalid Bearer token."

        return None

    def _read_bounded_json(self) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[int, str]]]:
        length_str = self.headers.get("Content-Length")
        if not length_str:
            return None, (HTTPStatus.LENGTH_REQUIRED, "Content-Length header is required.")
        try:
            length = int(length_str)
        except ValueError:
            return None, (HTTPStatus.BAD_REQUEST, "Invalid Content-Length header.")
        if length < 0 or length > MAX_BODY_BYTES:
            return None, (HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"Payload exceeds {MAX_BODY_BYTES} byte limit.")

        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return None, (HTTPStatus.BAD_REQUEST, "Malformed JSON request body.")
        if not isinstance(data, dict):
            return None, (HTTPStatus.BAD_REQUEST, "JSON body must be an object.")
        return data, None

    def do_GET(self) -> None:
        sec_err = self._check_security_headers_and_auth(is_post=False)
        if sec_err:
            self._send_json(sec_err[0], {"error": sec_err[1]})
            return

        path = urllib.parse.urlparse(self.path).path
        if path == "/" or path == "/index.html":
            raw = DASHBOARD_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        if path == "/api/v1/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "nemotron-forge",
                    "version": "1.0.0",
                    "nebius_credentials_configured": self.engine.nebius.has_credentials,
                    "tavily_credentials_configured": self.engine.tavily.has_credentials,
                    "tiers": {k: v.to_dict() for k, v in DEFAULT_MODEL_TIERS.items()},
                },
            )
            return

        if path == "/api/v1/feedback":
            self._send_json(
                HTTPStatus.OK,
                {
                    "events": [e.to_dict() for e in self.engine.feedback.events],
                },
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {path}"})

    def do_POST(self) -> None:
        sec_err = self._check_security_headers_and_auth(is_post=True)
        if sec_err:
            self._send_json(sec_err[0], {"error": sec_err[1]})
            return

        path = urllib.parse.urlparse(self.path).path
        body, read_err = self._read_bounded_json()
        if read_err or body is None:
            self._send_json(read_err[0] if read_err else 400, {"error": read_err[1] if read_err else "Bad request"})
            return

        if path == "/mcp":
            resp = self.mcp_server.handle_jsonrpc(body)
            self._send_json(HTTPStatus.OK, resp or {"jsonrpc": "2.0", "result": "accepted"})
            return

        if path == "/api/v1/run":
            acquired = _RUN_SEMAPHORE.acquire(blocking=False)
            if not acquired:
                self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Server at maximum concurrent run capacity."})
                return
            try:
                req = TaskRequest(
                    objective=str(body.get("objective", "")),
                    task_type=str(body.get("task_type", "hybrid")),
                    mode=str(body.get("mode", "simulated")),
                    max_repair_iterations=int(body.get("max_repair_iterations", 2)),
                    confidence_escalation_threshold=float(body.get("confidence_escalation_threshold", 0.70)),
                    constraints=dict(body.get("constraints") or {}),
                    seed=int(body.get("seed", 42)),
                )
                result = self.engine.execute(req)
                self._send_json(HTTPStatus.OK, result.to_dict())
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            finally:
                _RUN_SEMAPHORE.release()
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown POST endpoint: {path}"})


def create_http_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    engine: Optional[NemotronForgeEngine] = None,
    api_token: Optional[str] = None,
    allow_unauthenticated_public: bool = False,
) -> ThreadingHTTPServer:
    effective_token = api_token if api_token is not None else os.environ.get("FORGE_API_TOKEN", "")
    validate_bind_policy(host, effective_token, allow_unauthenticated_public=allow_unauthenticated_public)
    eng = engine or NemotronForgeEngine()

    class BoundHandler(NemotronForgeRequestHandler):
        pass

    BoundHandler.engine = eng
    BoundHandler.mcp_server = NemotronForgeMCPServer(engine=eng)
    BoundHandler.api_token = effective_token
    return ThreadingHTTPServer((host, port), BoundHandler)
