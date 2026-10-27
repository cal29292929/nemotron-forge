"""
Nebius Token Factory, NVIDIA Nemotron/Cosmos, and Tavily Grounding Providers
with explicit live/simulated/fallback provenance, permanent-error surfacing,
and structured platform feedback telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    CitationVerdict,
    DEFAULT_MODEL_TIERS,
    ModelTierSpec,
    jst_now_iso,
    redact_sensitive_text,
    redact_structure,
)


class ProviderAuthError(RuntimeError):
    """Raised on permanent 401/403 authentication or authorization failures."""


class ProviderSchemaError(RuntimeError):
    """Raised on permanent 400 request schema errors."""


@dataclass
class FeedbackEvent:
    event_id: str
    timestamp_jst: str
    source: str  # "live_api_observation" | "architecture_pre_flight"
    endpoint: str
    requested_model: str
    served_model: str
    http_status: Optional[int]
    latency_ms: float
    category: str
    observation: str
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FeedbackRecorder:
    """
    Collects developer experience and model routing observations for the Nebius Token Factory
    Platform Feedback Track, strictly separating live API observations from pre-flight analysis.
    """

    def __init__(self) -> None:
        self._events: List[FeedbackEvent] = []

    @property
    def events(self) -> List[FeedbackEvent]:
        return list(self._events)

    def record(
        self,
        source: str,
        endpoint: str,
        requested_model: str,
        served_model: str,
        http_status: Optional[int],
        latency_ms: float,
        category: str,
        observation: str,
        recommendation: str,
    ) -> FeedbackEvent:
        if source not in ("live_api_observation", "architecture_pre_flight"):
            raise ValueError(f"Invalid FeedbackEvent source: {source}")
        idx = len(self._events) + 1
        evt = FeedbackEvent(
            event_id=f"NTF-FB-{idx:03d}",
            timestamp_jst=jst_now_iso(),
            source=source,
            endpoint=redact_sensitive_text(endpoint),
            requested_model=requested_model,
            served_model=served_model,
            http_status=http_status,
            latency_ms=round(latency_ms, 2),
            category=category,
            observation=redact_sensitive_text(observation),
            recommendation=redact_sensitive_text(recommendation),
        )
        self._events.append(evt)
        return evt


_NEGATION_WORDS = frozenset({"not", "never", "no", "cannot", "false", "unsupported", "forbidden", "disabled", "without"})
_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "by", "is", "are", "was", "were", "be", "as", "at", "that", "this", "from"}
)


def _tokenize_content(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9_.\-]+", text.lower())
    return [t for t in tokens if len(t) > 2 and t not in _STOPWORDS]


def verify_claim_against_sources(
    citation_id: str,
    claim_text: str,
    sources: List[Dict[str, Any]],
    extract_failed: bool = False,
    execution_mode: str = "simulated",
) -> CitationVerdict:
    """
    Deterministic 4-state citation verifier (`supported` / `weak` / `unsupported` / `unverified`).
    Distinguishes extraction failures (`unverified`) from content mismatch (`unsupported`).
    """
    if extract_failed or not sources:
        top_url = sources[0].get("url", "https://docs.nebius.com") if sources else "https://docs.nebius.com"
        top_title = sources[0].get("title", "Unverified Source") if sources else "Unverified Source"
        return CitationVerdict(
            citation_id=citation_id,
            claim_text=claim_text,
            url=top_url,
            title=top_title,
            status="unverified",
            overlap_score=0.0,
            supporting_passage="",
            reason="Source extraction failed, timed out, or returned empty content; claim marked unverified.",
            execution_mode=execution_mode,
        )

    claim_tokens = set(_tokenize_content(claim_text))
    claim_negated = bool(claim_tokens & _NEGATION_WORDS)
    content_claim_tokens = claim_tokens - _NEGATION_WORDS
    if not content_claim_tokens:
        content_claim_tokens = {"nemotron"}

    best_score = -1.0
    best_source = sources[0]
    best_passage = ""
    best_negation_conflict = False

    for src in sources:
        passage = str(src.get("content") or src.get("raw_content") or "")
        passage_tokens = set(_tokenize_content(passage))
        passage_negated = bool(passage_tokens & _NEGATION_WORDS)
        matched = content_claim_tokens & (passage_tokens - _NEGATION_WORDS)
        overlap = len(matched) / float(len(content_claim_tokens))
        neg_conflict = claim_negated != passage_negated and ("not" in claim_tokens or "never" in claim_tokens or "not" in passage_tokens or "never" in passage_tokens)
        effective = overlap * (0.25 if neg_conflict else 1.0)
        if effective > best_score:
            best_score = effective
            best_source = src
            best_passage = passage[:320].strip()
            best_negation_conflict = neg_conflict

    score = round(max(0.0, min(1.0, best_score)), 4)
    if best_negation_conflict:
        status = "unsupported"
        reason = f"Polarity/negation conflict detected against source passage (effective score {score:.2f})."
    elif score >= 0.65:
        status = "supported"
        reason = f"High lexical/technical token overlap ({score:.2f} >= 0.65) with extracted passage."
    elif score >= 0.35:
        status = "weak"
        reason = f"Partial lexical overlap ({score:.2f} in [0.35, 0.65)); requires qualification."
    else:
        status = "unsupported"
        reason = f"Insufficient passage support ({score:.2f} < 0.35); claim omitted from verified output."

    return CitationVerdict(
        citation_id=citation_id,
        claim_text=claim_text,
        url=str(best_source.get("url", "https://docs.nebius.com")),
        title=str(best_source.get("title", "Technical Reference")),
        status=status,
        overlap_score=score,
        supporting_passage=best_passage,
        reason=reason,
        execution_mode=execution_mode,
    )


class TavilyGroundingClient:
    """
    Tavily Search & Extract client with deterministic simulation support and 4-state claim verification.
    """

    def __init__(self, api_key: Optional[str] = None, timeout_sec: float = 12.0) -> None:
        self.api_key = (api_key if api_key is not None else os.environ.get("TAVILY_API_KEY", "")).strip()
        self.timeout_sec = timeout_sec

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def search_and_extract(
        self,
        query: str,
        mode: str = "simulated",
    ) -> Tuple[List[Dict[str, Any]], str, bool]:
        """
        Returns (sources, execution_mode, extract_failed).
        """
        if mode == "simulated" or (mode == "hybrid" and not self.has_credentials):
            return self._simulated_sources(query), "simulated", False

        if not self.has_credentials:
            raise ProviderAuthError("TAVILY_API_KEY is required when running Tavily in strict 'live' mode.")

        payload = json.dumps(
            {
                "api_key": self.api_key,
                "query": query,
                "search_depth": "advanced",
                "include_raw_content": True,
                "max_results": 4,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                results = body.get("results", [])
                return results, "live", False
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ProviderAuthError(f"Tavily authentication failed with HTTP {exc.code}.") from exc
            if mode == "live":
                return [], "live", True
            return self._simulated_sources(query), "fallback", False
        except Exception:
            if mode == "live":
                return [], "live", True
            return self._simulated_sources(query), "fallback", False

    @staticmethod
    def _simulated_sources(query: str) -> List[Dict[str, Any]]:
        return [
            {
                "title": "NVIDIA Nemotron-3 Open Model Family & MoE Reasoning Architecture",
                "url": "https://developer.nvidia.com/nemotron",
                "content": (
                    "NVIDIA Nemotron-3 open models including Nano 30B, Super 120B, and Ultra provide "
                    "high-throughput hybrid Mamba-Transformer / MoE reasoning for agentic coding, tool calling, "
                    "and safety-critical verification workflows deployed via OpenAI-compatible inference endpoints."
                ),
            },
            {
                "title": "Nebius Token Factory OpenAI-Compatible Inference API Documentation",
                "url": "https://docs.nebius.com/studio/inference/quickstart",
                "content": (
                    "Nebius Token Factory exposes an OpenAI-compatible /v1/chat/completions endpoint at "
                    "https://api.studio.nebius.ai/v1 supporting low-latency token streaming, model routing, "
                    "and structured JSON tool invocation across open-weight NVIDIA Nemotron and Llama models."
                ),
            },
            {
                "title": "ISO 10218 / Collaborative Robotics Kinematic & Torque Safety Envelope Reference",
                "url": "https://docs.nvidia.com/cosmos/latest/physical-ai-safety.html",
                "content": (
                    "Robotic trajectory planners must bound end-effector velocity below 1.5 m/s, linear acceleration "
                    "below 4.0 m/s2, joint payload torque below 45.0 Nm, and maintain a minimum 0.15 m obstacle "
                    "clearance margin within workspace boundaries before physical actuator execution."
                ),
            },
        ]


class NebiusTokenFactoryClient:
    """
    OpenAI-compatible client for Nebius Token Factory (`https://api.studio.nebius.ai/v1`)
    with tiered NVIDIA Nemotron routing, live model probing (`selfcheck`), and structured feedback recording.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        promo_code: Optional[str] = None,
        feedback_recorder: Optional[FeedbackRecorder] = None,
        timeout_sec: float = 20.0,
    ) -> None:
        self.api_key = (api_key if api_key is not None else os.environ.get("NEBIUS_API_KEY", "")).strip()
        self.base_url = (base_url or os.environ.get("NEBIUS_BASE_URL") or "https://api.studio.nebius.ai/v1").rstrip("/")
        self.promo_code = (promo_code or os.environ.get("NEBIUS_PROMO_CODE") or "NEBIUS-DEVPOST-GLOBAL26").strip()
        self.feedback = feedback_recorder or FeedbackRecorder()
        self.timeout_sec = timeout_sec

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key)

    def probe_models(self) -> Dict[str, Any]:
        """
        Live `/v1/models` diagnostic probe for `nemotron_forge.cli selfcheck`.
        Never mutates tier mappings automatically on ambiguous regex hits; reports candidates cleanly.
        """
        url = f"{self.base_url}/models"
        if not self.has_credentials:
            return {
                "endpoint": url,
                "authenticated": False,
                "status": "skipped_no_api_key",
                "http_status": None,
                "discovered_nemotron_models": [],
                "discovered_cosmos_models": [],
                "configured_tiers": {k: v.primary_model_id for k, v in DEFAULT_MODEL_TIERS.items()},
                "message": "NEBIUS_API_KEY not set in environment; running in deterministic simulation mode.",
            }

        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
            method="GET",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                body = json.loads(resp.read().decode("utf-8"))
                model_ids = [str(item.get("id", "")) for item in body.get("data", []) if isinstance(item, dict)]
                nemotron_ids = sorted([m for m in model_ids if "nemotron" in m.lower()])
                cosmos_ids = sorted([m for m in model_ids if "cosmos" in m.lower()])
                self.feedback.record(
                    source="live_api_observation",
                    endpoint=url,
                    requested_model="GET /v1/models",
                    served_model=f"{len(model_ids)} models returned",
                    http_status=resp.status,
                    latency_ms=latency_ms,
                    category="model_catalog_discovery",
                    observation=f"Catalog returned {len(nemotron_ids)} Nemotron models and {len(cosmos_ids)} Cosmos models.",
                    recommendation="Expose standardized capability tags (tier, max_context, tool_call_support) in /v1/models metadata.",
                )
                return {
                    "endpoint": url,
                    "authenticated": True,
                    "status": "ok",
                    "http_status": resp.status,
                    "latency_ms": round(latency_ms, 2),
                    "total_models": len(model_ids),
                    "discovered_nemotron_models": nemotron_ids,
                    "discovered_cosmos_models": cosmos_ids,
                    "configured_tiers": {k: v.primary_model_id for k, v in DEFAULT_MODEL_TIERS.items()},
                }
        except urllib.error.HTTPError as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "endpoint": url,
                "authenticated": exc.code not in (401, 403),
                "status": "http_error",
                "http_status": exc.code,
                "latency_ms": round(latency_ms, 2),
                "discovered_nemotron_models": [],
                "discovered_cosmos_models": [],
                "configured_tiers": {k: v.primary_model_id for k, v in DEFAULT_MODEL_TIERS.items()},
                "message": f"HTTP {exc.code} from {url}",
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "endpoint": url,
                "authenticated": False,
                "status": "network_error",
                "http_status": None,
                "latency_ms": round(latency_ms, 2),
                "discovered_nemotron_models": [],
                "discovered_cosmos_models": [],
                "configured_tiers": {k: v.primary_model_id for k, v in DEFAULT_MODEL_TIERS.items()},
                "message": redact_sensitive_text(str(exc)),
            }

    def invoke_tier(
        self,
        tier_id: str,
        stage_name: str,
        messages: List[Dict[str, str]],
        mode: str = "simulated",
        seed: int = 42,
        simulated_response: str = "",
        simulated_confidence: float = 0.91,
    ) -> Dict[str, Any]:
        spec: ModelTierSpec = DEFAULT_MODEL_TIERS.get(tier_id, DEFAULT_MODEL_TIERS["MID"])

        if mode == "simulated" or (mode == "hybrid" and not self.has_credentials):
            prompt_chars = sum(len(m.get("content", "")) for m in messages)
            prompt_tokens = max(64, prompt_chars // 4)
            completion_tokens = max(96, len(simulated_response) // 4)
            cost_usd = (
                (prompt_tokens / 1_000_000.0) * spec.cost_per_1m_input_usd
                + (completion_tokens / 1_000_000.0) * spec.cost_per_1m_output_usd
            )
            return {
                "tier_id": tier_id,
                "stage_name": stage_name,
                "requested_model_id": spec.primary_model_id,
                "served_model_id": spec.primary_model_id,
                "execution_mode": "simulated",
                "is_estimated_telemetry": True,
                "content": simulated_response,
                "confidence": simulated_confidence,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": float(spec.typical_latency_ms),
                "estimated_cost_usd": round(cost_usd, 6),
                "degraded_reason": None,
            }

        if not self.has_credentials:
            raise ProviderAuthError("NEBIUS_API_KEY is required when invoking NebiusTokenFactoryClient in strict 'live' mode.")

        candidates = (spec.primary_model_id,) + spec.fallback_model_ids
        url = f"{self.base_url}/chat/completions"
        last_err: Optional[str] = None

        for idx, candidate_model in enumerate(candidates):
            payload = json.dumps(
                {
                    "model": candidate_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 1024,
                    "seed": seed,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Nebius-Promo": self.promo_code,
                },
                method="POST",
            )
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    latency_ms = (time.perf_counter() - t0) * 1000.0
                    body = json.loads(resp.read().decode("utf-8"))
                    choice = (body.get("choices") or [{}])[0]
                    msg = choice.get("message") or {}
                    content = str(msg.get("content") or msg.get("reasoning_content") or "")
                    usage = body.get("usage") or {}
                    p_tok = int(usage.get("prompt_tokens") or 128)
                    c_tok = int(usage.get("completion_tokens") or max(64, len(content) // 4))
                    cost_usd = (
                        (p_tok / 1_000_000.0) * spec.cost_per_1m_input_usd
                        + (c_tok / 1_000_000.0) * spec.cost_per_1m_output_usd
                    )
                    exec_mode = "live" if idx == 0 else "fallback"
                    if idx > 0:
                        self.feedback.record(
                            source="live_api_observation",
                            endpoint=url,
                            requested_model=spec.primary_model_id,
                            served_model=candidate_model,
                            http_status=resp.status,
                            latency_ms=latency_ms,
                            category="tier_model_fallback",
                            observation=f"Primary model {spec.primary_model_id} unavailable; succeeded via fallback {candidate_model}.",
                            recommendation="Provide canonical model alias slugs for Nemotron-3 tiers across regions.",
                        )
                    return {
                        "tier_id": tier_id,
                        "stage_name": stage_name,
                        "requested_model_id": spec.primary_model_id,
                        "served_model_id": body.get("model", candidate_model),
                        "execution_mode": exec_mode,
                        "is_estimated_telemetry": False,
                        "content": content or simulated_response,
                        "confidence": simulated_confidence,
                        "prompt_tokens": p_tok,
                        "completion_tokens": c_tok,
                        "latency_ms": round(latency_ms, 2),
                        "estimated_cost_usd": round(cost_usd, 6),
                        "degraded_reason": None if idx == 0 else f"Fell back from {spec.primary_model_id} to {candidate_model}",
                    }
            except urllib.error.HTTPError as exc:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                if exc.code in (401, 403):
                    raise ProviderAuthError(f"Nebius Token Factory rejected credentials with HTTP {exc.code}.") from exc
                if exc.code == 400:
                    raise ProviderSchemaError(f"Nebius Token Factory rejected request schema with HTTP 400.") from exc
                last_err = f"HTTP {exc.code} on {candidate_model}"
                self.feedback.record(
                    source="live_api_observation",
                    endpoint=url,
                    requested_model=candidate_model,
                    served_model="none",
                    http_status=exc.code,
                    latency_ms=latency_ms,
                    category="http_transient_or_model_id",
                    observation=f"Received HTTP {exc.code} when requesting {candidate_model}.",
                    recommendation="Return suggested active Nemotron model IDs in 404 error payloads.",
                )
            except Exception as exc:
                last_err = redact_sensitive_text(str(exc))

        if mode == "live":
            raise RuntimeError(f"All Nebius model candidates failed for tier {tier_id}: {last_err}")

        # Hybrid fallback to deterministic simulation with explicit fallback provenance
        prompt_tokens = 160
        completion_tokens = max(96, len(simulated_response) // 4)
        cost_usd = (
            (prompt_tokens / 1_000_000.0) * spec.cost_per_1m_input_usd
            + (completion_tokens / 1_000_000.0) * spec.cost_per_1m_output_usd
        )
        return {
            "tier_id": tier_id,
            "stage_name": stage_name,
            "requested_model_id": spec.primary_model_id,
            "served_model_id": spec.primary_model_id,
            "execution_mode": "fallback",
            "is_estimated_telemetry": True,
            "content": simulated_response,
            "confidence": simulated_confidence,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": float(spec.typical_latency_ms),
            "estimated_cost_usd": round(cost_usd, 6),
            "degraded_reason": f"Fallback to deterministic simulation after error: {last_err}",
        }
