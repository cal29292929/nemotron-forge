# Nemotron Forge — Tiered Multi-Agent Orchestrator & Physical/Code Verification Studio

> **Built for the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/) (October 2026)**
> **Submission Deadline**: `2026-10-31 02:00 JST` (`2026-10-30 10:00 PDT` / `17:00 UTC`) — Internal freeze target: `2026-10-30 18:00 JST` (8 hours prior to hard deadline).
> **Author**: Kazutoshi Hayashi (`cal29292929`) | **License**: MIT

---

## 1. Overview & Problem Solved

Deploying open-weight reasoning models for software synthesis and Physical AI robotics faces two critical production bottlenecks:
1. **Monolithic Inference Cost & Latency**: Routing every intent check, search query, and verification pass through a frontier 253B+ parameter model wastes >45% of token budget and doubles end-to-end latency.
2. **Unverified Code & Unsafe Trajectories**: Single-pass LLM outputs frequently contain hallucinated citations, unsafe dynamic Python calls, or robotic trajectories that violate ISO 10218 velocity, acceleration, payload torque, or obstacle clearance limits.

**Nemotron Forge** solves both challenges on **Nebius Token Factory** (`https://api.studio.nebius.ai/v1`) by combining:
- **Tiered NVIDIA Nemotron-3 Routing (`FAST` → `MID` → `DEEP` + `PHYSICAL`)**: Dynamically routes sub-tasks across `nvidia/Llama-3_3-Nemotron-Super-49B-v1` / `nvidia/Nemotron-3-Nano-30B-A3B` (`FAST`), `nvidia/Llama-3_1-Nemotron-Ultra-253B-v1` / `nvidia/Nemotron-3-Super-120B` (`MID`), `nvidia/Nemotron-3-Ultra` (`DEEP`), and `nvidia/Cosmos-Reason1-7B` (`PHYSICAL`), escalating to `DEEP` when confidence drops below `0.70` or verification detects a repairable defect.
- **4-State Tavily Citation Verifier (`supported` / `weak` / `unsupported` / `unverified`)**: Verifies every technical claim against extracted source passages, distinguishing extraction failures (`unverified`) from unsupported/contradicted claims (`unsupported`, which are filtered into `omitted_claims`).
- **Defense-in-Depth Code Gate (`ASTSecurityGate` + `SandboxRunner`)**: Rejects dangerous imports, builtins, and dunder traversal via static AST inspection before executing unit tests inside an isolated temporary directory with OS `RLIMIT_CPU`/`RLIMIT_FSIZE`, scrubbed environment, and a `FORGE_ALLOW_LOCAL_EXEC` policy switch.
- **Analytic + NVIDIA Cosmos Kinematic Verifier (`PhysicalVerifier`)**: Validates 3D robotic waypoint trajectories against velocity ($\le 1.50\text{ m/s}$), acceleration ($\le 4.00\text{ m/s}^2$), workspace bounds, obstacle clearance ($\ge 0.15\text{ m}$), and joint payload torque ($\le 45.0\text{ Nm}$).
- **Tamper-Evident Redacted Audit Trail (`AuditTrail`)**: Redacts credentials/PII prior to logging and maintains a SHA-256 hash chain plus HMAC-SHA256 signatures, explicitly separating `chain_verified`, `hmac_configured`, and `hmac_verified`.

---

## 2. Quickstart (< 10 Seconds, Zero External Dependencies)

```bash
# Run full unit test suite, model catalog selfcheck, and deterministic 5-stage demo
./run_demo.sh

# Launch the hardened local Web Studio & REST/MCP Server (loopback 127.0.0.1:8080)
python3 -m nemotron_forge.cli serve --host 127.0.0.1 --port 8080

# Run as a JSON-RPC 2.0 Model Context Protocol (MCP) stdio server
python3 -m nemotron_forge.cli mcp
```

### Live API Configuration (Optional `.env` / Environment Variables)
- `NEBIUS_API_KEY`: Nebius Token Factory API key (Promo code: `NEBIUS-DEVPOST-GLOBAL26`)
- `NEBIUS_BASE_URL`: Defaults to `https://api.studio.nebius.ai/v1`
- `TAVILY_API_KEY`: Tavily Search & Extract API key for live web grounding
- `FORGE_AUDIT_HMAC_SECRET`: Secret key for HMAC-SHA256 audit log signing
- `FORGE_API_TOKEN`: Required if binding the HTTP server to a non-loopback interface

> **Transparency & Provenance Guarantee**: Every stage trace and run report explicitly labels `effective_mode` (`live` vs `simulated` vs `fallback`) and `is_estimated_telemetry` (`ESTIMATED_SIMULATION_TELEMETRY` vs `LIVE_MEASURED_TELEMETRY`). Permanent authentication (`401`/`403`) or schema (`400`) errors in `live` mode fail fast rather than silently masking configuration errors.
