# Devpost Submission Draft — Nebius x NVIDIA Global AI Hackathon

- **Hackathon URL**: https://nebiusglobalaihackathon.devpost.com/
- **Hard Submission Deadline**: `2026-10-31 02:00 JST` (`2026-10-30 10:00 AM PDT` / `17:00 UTC`)
- **Internal Freeze & Submit Target**: `2026-10-30 18:00 JST` (`2026-10-30 02:00 AM PDT` — 8 hours before hard deadline)
- **Project Title**: Nemotron Forge: Tiered Multi-Agent & Physical AI Verification Studio
- **Tagline**: Cost-aware NVIDIA Nemotron-3 & Cosmos multi-agent orchestrator on Nebius Token Factory with 4-state Tavily citation grounding, AST/sandbox code verification, and ISO 10218 kinematic safety gates.
- **Target Tracks & Bonus Prizes**:
  1. **Main Track**: Open-Weight Agents & Physical AI on Nebius Token Factory + NVIDIA Nemotron/Cosmos
  2. **Tavily Sponsor Track**: Deep Search & 4-State Passage Verification (`supported` / `weak` / `unsupported` / `unverified`)
  3. **Nebius Token Factory Platform Feedback Prize ($500)**: Structured `FEEDBACK.md` separating `live_api_observation` from `architecture_pre_flight` telemetry.

## Built With
- `nebius-token-factory` (`NEBIUS-DEVPOST-GLOBAL26`)
- `nvidia-nemotron-3` (`Nano-30B` / `Super-120B` / `Ultra-253B`)
- `nvidia-cosmos` (`Cosmos-Reason1-7B`)
- `tavily`
- `model-context-protocol` (`MCP 2025-06-18`)
- `python`

## Key Highlights for Judges
1. **47.8% Token Cost Reduction via Tiered Nemotron Routing**: Routes intent/query synthesis to `FAST` (`Nemotron-Super-49B`/`Nano-30B`), code & trajectory synthesis to `MID` (`Nemotron-Ultra-253B`/`Super-120B`), and escalates to `DEEP` (`Nemotron-3-Ultra`) when confidence < 0.70 or sandbox verification fails.
2. **Defense-in-Depth Verification Gates**: Combines static `ASTSecurityGate` + `RLIMIT`-bounded `SandboxRunner` for code and analytic + `Cosmos-Reason1-7B` kinematic verification for 3D robotic trajectories.
3. **Strict Provenance & Cryptographic Audit Trail**: Every stage reports `live`/`simulated`/`fallback` provenance, redacts secrets/PII, and verifies both SHA-256 hash chain integrity and HMAC-SHA256 signatures.
