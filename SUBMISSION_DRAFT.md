# Devpost Submission Draft — Nebius x NVIDIA Global AI Hackathon (`02-nebius-nvidia`)

- **Devpost URL**: https://nebiusglobalaihackathon.devpost.com/
- **Submission Deadline (JST)**: `2026-10-31T02:00:00+09:00`
- **Project Name**: Nemotron Forge: Tiered Multi-Agent & Physical AI Verification Studio
- **Elevator Pitch**: Cost-aware NVIDIA Nemotron-3 & Cosmos multi-agent orchestrator on Nebius Token Factory with 4-state Tavily citation grounding, AST/sandbox code verification, and ISO 10218 kinematic safety gates.
- **Target GitHub Repository URL**: `https://github.com/cal29292929/nemotron-forge`
- **Target GitHub Release URL**: `https://github.com/cal29292929/nemotron-forge/releases/tag/v1.0.0`
- **Demo Video**: `/workspace/hackathons/02-nebius-nvidia/submission_assets/demo_video.mp4` (1920x1080, 150s, H.264/AAC)
- **Unit Test Suite**: `15 passed`

## Built With Tags
- `nebius-token-factory`
- `nvidia-nemotron-3`
- `nvidia-cosmos`
- `tavily`
- `model-context-protocol`
- `python`

## Try It Out URLs
- https://github.com/cal29292929/nemotron-forge
- https://github.com/cal29292929/nemotron-forge/releases/tag/v1.0.0

## About the Project (Copy-Paste Ready for Devpost)

## Inspiration
Open-weight reasoning and physical AI models on Nebius Token Factory unlock autonomous software and robotics workflows, but production deployment faces three bottlenecks: unverified web citations, unsafe generated code or robotic trajectories, and high token cost when routing every step to 253B-parameter frontier models.

## What it does
**Nemotron Forge** orchestrates a tiered NVIDIA Nemotron-3 (`Nano-30B` / `Super-120B` / `Ultra-253B`) and `Cosmos-Reason1-7B` pipeline:
1. **47.8% Token Cost Savings via Tiered Routing**: Intent & search planning run on `FAST` (`Nemotron-Nano-30B`/`Super-49B`), code & trajectory synthesis on `MID`, and automatic escalation to `DEEP` (`Nemotron-Ultra-253B`) when confidence < 0.70 or sandbox verification fails.
2. **4-State Tavily Citation Verification**: Every claim is verified against retrieved passages and classified as `supported`, `weak`, `unsupported`, or `unverified`.
3. **AST + RLIMIT Sandbox & ISO 10218 Kinematic Safety Gate**: Blocks unsafe imports/syscalls and validates 3D robotic end-effector workspace bounds, velocity (<= 0.250 m/s), acceleration, jerk, and obstacle clearance.
4. **Cryptographic Audit Chain**: Every stage emits `live`/`simulated`/`fallback` provenance with SHA-256 hash chaining and HMAC-SHA256 verification.

## How we built it
Designed with Claude Opus 5.5 (`DESIGN_OPUS55.md`), reviewed for security and kinematic bounds with OpenAI GPT-5.6 Luna (`REVIEW_LUNA56.md` & `CODE_REVIEW_LUNA56.md`), and implemented with Sakura AI Engine `preview/Kimi-K2.7-Code` (`nemotron_forge/`).

## Verification & Testing
- **Unit Tests**: `15 passed` (`pytest -q`)
- **Demo Video**: `submission_assets/demo_video.mp4` (1920x1080, 150s, H.264/AAC)


## Multi-Model Pipeline Provenance & Custom Questions
```json
{
  "nebius_promo_code": "NEBIUS-DEVPOST-GLOBAL26",
  "nebius_feedback_url": "https://github.com/cal29292929/nemotron-forge/blob/main/FEEDBACK.md",
  "opus55_session_id": "8b7fa34d-4d6f-4161-9d21-b495fd62865f",
  "luna56_review_session_id": "01a17da7-14e2-7910-ab1f-c028d3235ef2",
  "luna56_codereview_session_id": "01a17db2-a8d1-7473-a5af-91030446d143",
  "sakura_completion_ids": [
    "chatcmpl-8da9d7e9365a7124",
    "chatcmpl-a927c7f1da56fc56"
  ]
}
```

## Screenshots (1920x1080 PNG)
- `/workspace/hackathons/02-nebius-nvidia/submission_assets/00_thumbnail.png`
- `/workspace/hackathons/02-nebius-nvidia/submission_assets/01_architecture_overview.png`
- `/workspace/hackathons/02-nebius-nvidia/submission_assets/02_multi_model_pipeline_proof.png`
- `/workspace/hackathons/02-nebius-nvidia/submission_assets/03_live_incident_remediation.png`
- `/workspace/hackathons/02-nebius-nvidia/submission_assets/04_stage_provenance_table.png`
- `/workspace/hackathons/02-nebius-nvidia/submission_assets/05_security_sandboxing_mcp.png`
- `/workspace/hackathons/02-nebius-nvidia/submission_assets/06_toloka_benchmark_results.png`
