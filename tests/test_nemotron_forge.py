"""
Comprehensive Unit & Security Test Suite for Nemotron Forge (`02-nebius-nvidia`).
Covers all requirements from DESIGN_OPUS55.md and REVIEW_LUNA56.md.
"""

from __future__ import annotations

import json
import unittest
import urllib.request

from nemotron_forge.engine import (
    ASTSecurityGate,
    NemotronForgeEngine,
    PhysicalVerifier,
    SandboxRunner,
)
from nemotron_forge.mcp_server import NemotronForgeMCPServer
from nemotron_forge.models import (
    AuditTrail,
    TaskRequest,
    redact_sensitive_text,
    redact_structure,
)
from nemotron_forge.providers import (
    FeedbackRecorder,
    NebiusTokenFactoryClient,
    ProviderAuthError,
    verify_claim_against_sources,
)
from nemotron_forge.server import create_http_server, validate_bind_policy


class TestModelsAndAuditRedaction(unittest.TestCase):
    def test_secret_and_pii_redaction(self) -> None:
        raw = {
            "NEBIUS_API_KEY": "secret-token-123456789",
            "note": "Authorization: Bearer abcdef0123456789 and tvly-9876543210 plus user@example.com",
        }
        redacted = redact_structure(raw)
        self.assertEqual(redacted["NEBIUS_API_KEY"], "[REDACTED]")
        self.assertNotIn("abcdef0123456789", redacted["note"])
        self.assertNotIn("tvly-9876543210", redacted["note"])
        self.assertNotIn("user@example.com", redacted["note"])

    def test_audit_trail_separates_chain_and_hmac_verification(self) -> None:
        # Without HMAC secret configured
        audit_unconfigured = AuditTrail(hmac_secret="")
        audit_unconfigured.append("stage1", "init", "simulated", {"NEBIUS_API_KEY": " leaked "})
        v1 = audit_unconfigured.verify()
        self.assertTrue(v1["chain_verified"])
        self.assertFalse(v1["hmac_configured"])
        self.assertFalse(v1["hmac_verified"])

        # With HMAC secret configured
        audit_configured = AuditTrail(hmac_secret="super-secret-hmac-key")
        entry = audit_configured.append("stage1", "init", "simulated", {"msg": "Bearer secret12345678"})
        self.assertIn("[REDACTED_BEARER]", entry.payload_redacted["msg"])
        v2 = audit_configured.verify()
        self.assertTrue(v2["chain_verified"])
        self.assertTrue(v2["hmac_configured"])
        self.assertTrue(v2["hmac_verified"])

        # Tamper detection
        audit_configured._entries[0].payload_redacted["msg"] = "tampered"
        v3 = audit_configured.verify()
        self.assertFalse(v3["chain_verified"])


class TestCitationVerifierFourStates(unittest.TestCase):
    def setUp(self) -> None:
        self.sources = [
            {
                "title": "Nebius Token Factory Docs",
                "url": "https://docs.nebius.com/studio/inference/quickstart",
                "content": "Nebius Token Factory exposes an OpenAI-compatible /v1/chat/completions endpoint supporting low-latency token streaming and model routing across NVIDIA Nemotron models.",
            }
        ]

    def test_supported_claim(self) -> None:
        v = verify_claim_against_sources(
            "C1",
            "Nebius Token Factory exposes an OpenAI-compatible /v1/chat/completions endpoint supporting model routing across NVIDIA Nemotron models.",
            self.sources,
        )
        self.assertEqual(v.status, "supported")
        self.assertGreaterEqual(v.overlap_score, 0.65)

    def test_weak_claim(self) -> None:
        v = verify_claim_against_sources(
            "C2",
            "Nebius Token Factory endpoint supports custom quantized batching jobs on multi-node clusters.",
            self.sources,
        )
        self.assertEqual(v.status, "weak")
        self.assertGreaterEqual(v.overlap_score, 0.35)
        self.assertLess(v.overlap_score, 0.65)

    def test_unsupported_claim_and_negation(self) -> None:
        v = verify_claim_against_sources(
            "C3",
            "Nebius Token Factory never exposes an OpenAI-compatible /v1/chat/completions endpoint for NVIDIA Nemotron models.",
            self.sources,
        )
        self.assertEqual(v.status, "unsupported")

    def test_unverified_when_extract_fails(self) -> None:
        v = verify_claim_against_sources(
            "C4",
            "Nebius Token Factory exposes an OpenAI-compatible endpoint.",
            self.sources,
            extract_failed=True,
        )
        self.assertEqual(v.status, "unverified")


class TestASTAndSandboxSecurity(unittest.TestCase):
    def test_ast_blocks_dangerous_imports_and_dunders(self) -> None:
        bad_samples = [
            "import os\nos.system('id')",
            "import subprocess\nsubprocess.Popen(['ls'])",
            "from urllib import request",
            "x = ().__class__.__bases__[0].__subclasses__()",
            "eval('2 + 2')",
            "getattr(object, '__subclasses__')",
        ]
        for code in bad_samples:
            ok, violations = ASTSecurityGate.scan(code)
            self.assertFalse(ok, f"Expected AST gate to reject: {code}")
            self.assertTrue(len(violations) > 0)

    def test_sandbox_executes_safe_code_and_blocks_unsafe(self) -> None:
        runner = SandboxRunner(timeout_sec=3.0, allow_local_exec=True)
        safe_report = runner.verify_code(
            "def add(a, b):\n    return a + b\n",
            "def test_add():\n    assert add(2, 3) == 5\nif __name__ == '__main__':\n    test_add()\n",
        )
        self.assertTrue(safe_report.passed)
        self.assertTrue(safe_report.ast_safe)
        self.assertEqual(safe_report.exit_code, 0)

        unsafe_report = runner.verify_code("import socket\ns = socket.socket()")
        self.assertFalse(unsafe_report.passed)
        self.assertFalse(unsafe_report.ast_safe)
        self.assertFalse(unsafe_report.execution_attempted)

    def test_sandbox_respects_local_exec_disable_flag(self) -> None:
        runner = SandboxRunner(timeout_sec=2.0, allow_local_exec=False)
        report = runner.verify_code("x = 1 + 1")
        self.assertFalse(report.passed)
        self.assertTrue(report.ast_safe)
        self.assertFalse(report.execution_attempted)
        self.assertEqual(report.execution_policy, "disabled_by_FORGE_ALLOW_LOCAL_EXEC")


class TestPhysicalVerifierAndEngineDeterminism(unittest.TestCase):
    def test_physical_verifier_detects_velocity_and_clearance_violations(self) -> None:
        safe = PhysicalVerifier.verify_trajectory()
        self.assertTrue(safe.passed)
        self.assertLessEqual(safe.max_velocity_mps, PhysicalVerifier.VELOCITY_LIMIT_MPS)

        # Colliding & high-speed trajectory
        unsafe_wps = [
            {"t_sec": 0.0, "x_m": 0.0, "y_m": 0.0, "z_m": 0.2},
            {"t_sec": 0.1, "x_m": 0.45, "y_m": 0.30, "z_m": 0.40},  # Exact obstacle center + >5 m/s
        ]
        unsafe = PhysicalVerifier.verify_trajectory(waypoints_raw=unsafe_wps)
        self.assertFalse(unsafe.passed)
        self.assertGreater(len(unsafe.violations), 0)

    def test_deterministic_digest_and_escalation(self) -> None:
        eng = NemotronForgeEngine(hmac_secret="test-hmac-key")
        req1 = TaskRequest(objective="Verify robotic controller", task_type="hybrid", mode="simulated", seed=42)
        req2 = TaskRequest(objective="Verify robotic controller", task_type="hybrid", mode="simulated", seed=42)
        r1 = eng.execute(req1)
        r2 = eng.execute(req2)
        self.assertEqual(r1.result_digest, r2.result_digest)
        self.assertEqual(r1.effective_mode, "simulated")
        self.assertTrue(r1.is_estimated_telemetry)
        self.assertTrue(r1.audit_verification["chain_verified"])
        self.assertTrue(r1.audit_verification["hmac_verified"])
        self.assertGreater(len(r1.omitted_claims), 0)

        # Low MID confidence triggers escalation flag
        req_esc = TaskRequest(
            objective="Complex edge case",
            task_type="code",
            mode="simulated",
            seed=42,
            constraints={"simulated_mid_confidence": 0.55},
        )
        r_esc = eng.execute(req_esc)
        self.assertTrue(r_esc.stages[-1].escalated_to_deep)
        self.assertIn("MID confidence", r_esc.stages[-1].escalation_reason or "")

    def test_live_mode_without_api_key_raises_auth_error(self) -> None:
        client = NebiusTokenFactoryClient(api_key="")
        with self.assertRaises(ProviderAuthError):
            client.invoke_tier("FAST", "stage", [{"role": "user", "content": "hi"}], mode="live")


class TestMCPAndHTTPServerSecurity(unittest.TestCase):
    def test_mcp_jsonrpc_lifecycle(self) -> None:
        mcp = NemotronForgeMCPServer()
        init_resp = mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(init_resp["result"]["protocolVersion"], "2025-06-18")

        # Notifications return None
        notif_resp = mcp.handle_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(notif_resp)

        tools_resp = mcp.handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(tools_resp["result"]["tools"]), 4)

        call_resp = mcp.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "forge_verify_code", "arguments": {"code": "x = 2 + 2"}},
            }
        )
        self.assertFalse(call_resp["result"]["isError"])

    def test_public_bind_refused_without_token(self) -> None:
        with self.assertRaises(PermissionError):
            validate_bind_policy("0.0.0.0", api_token="", allow_unauthenticated_public=False)

    def test_http_server_endpoints(self) -> None:
        srv = create_http_server(host="127.0.0.1", port=0)
        port = srv.server_address[1]
        import threading

        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["status"], "ok")
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
