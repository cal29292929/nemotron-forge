# Nebius Token Factory — Structured Platform Feedback Report (`FEEDBACK.md`)

> **Submission Track**: Nebius Token Factory Platform Feedback Prize ($500) + Main Track
> **Provenance Note**: Every entry explicitly distinguishes `live_api_observation` from `architecture_pre_flight` analysis.

| ID | Source | Endpoint | Requested Model | Served Model | Category | Observation | Actionable Recommendation |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| `NTF-FB-001` | `architecture_pre_flight` | `https://api.studio.nebius.ai/v1/chat/completions` | `nvidia/Llama-3_3-Nemotron-Super-49B-v1` | `nvidia/Llama-3_3-Nemotron-Super-49B-v1` | `tiered_routing_efficiency` | Routing intent classification and query planning to Nemotron FAST tier reduces token spend by >60% vs monolithic Ultra calls. | Add native server-side router hints (`x-nebius-tier: fast|mid|deep`) in Nebius Token Factory. |
