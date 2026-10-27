"""
Data models, strict validation, deterministic digests, and audit/redaction primitives
for Nemotron Forge (Nebius x NVIDIA Global AI Hackathon).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
import datetime
import hashlib
import hmac
import json
import re
from typing import Any, Dict, List, Optional, Tuple


SIM_VERSION = "nemotron-forge-sim-v1.2"
ALLOWED_TASK_TYPES = ("code", "physical", "research", "hybrid")
ALLOWED_MODES = ("live", "simulated", "hybrid")
ALLOWED_EXECUTION_MODES = ("live", "simulated", "fallback")
ALLOWED_CITATION_STATUSES = ("supported", "weak", "unsupported", "unverified")


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def jst_now_iso() -> str:
    jst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(jst).isoformat(timespec="seconds")


# Secret & PII redaction regexes for AuditTrail and FeedbackRecorder
_SECRET_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE), r"\1[REDACTED_BEARER]"),
    (re.compile(r"(tvly-[A-Za-z0-9._\-]{6,})"), "[REDACTED_TAVILY_KEY]"),
    (re.compile(r"(nvapi-[A-Za-z0-9._\-]{6,})"), "[REDACTED_NVIDIA_KEY]"),
    (re.compile(r"([A-Za-z0-9_]*API_KEY['\"\s:=]+)([A-Za-z0-9._\-]{6,})", re.IGNORECASE), r"\1[REDACTED_KEY]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
]


def redact_sensitive_text(text: str) -> str:
    if not isinstance(text, str):
        return str(text)
    out = text
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


def redact_structure(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_sensitive_text(obj)
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            key_str = str(k)
            if any(tok in key_str.upper() for tok in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "AUTHORIZATION")):
                result[k] = "[REDACTED]"
            else:
                result[k] = redact_structure(v)
        return result
    if isinstance(obj, list):
        return [redact_structure(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(redact_structure(x) for x in obj)
    return obj


@dataclass(frozen=True)
class ModelTierSpec:
    tier_id: str  # "FAST" | "MID" | "DEEP" | "PHYSICAL"
    primary_model_id: str
    fallback_model_ids: Tuple[str, ...]
    cost_per_1m_input_usd: float
    cost_per_1m_output_usd: float
    typical_latency_ms: int
    role_description: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


DEFAULT_MODEL_TIERS: Dict[str, ModelTierSpec] = {
    "FAST": ModelTierSpec(
        tier_id="FAST",
        primary_model_id="nvidia/Llama-3_3-Nemotron-Super-49B-v1",
        fallback_model_ids=("nvidia/Nemotron-3-Nano-30B-A3B", "meta-llama/Llama-3.3-70B-Instruct"),
        cost_per_1m_input_usd=0.12,
        cost_per_1m_output_usd=0.30,
        typical_latency_ms=340,
        role_description="Fast intent classification, complexity scoring, and Tavily query synthesis",
    ),
    "MID": ModelTierSpec(
        tier_id="MID",
        primary_model_id="nvidia/Llama-3_1-Nemotron-Ultra-253B-v1",
        fallback_model_ids=("nvidia/Nemotron-3-Super-120B", "nvidia/Llama-3_3-Nemotron-Super-49B-v1"),
        cost_per_1m_input_usd=0.60,
        cost_per_1m_output_usd=1.80,
        typical_latency_ms=920,
        role_description="Code & test synthesis, kinematic planning, and security critique",
    ),
    "DEEP": ModelTierSpec(
        tier_id="DEEP",
        primary_model_id="nvidia/Nemotron-3-Ultra",
        fallback_model_ids=("nvidia/Llama-3_1-Nemotron-Ultra-253B-v1", "nvidia/Nemotron-3-Super-120B"),
        cost_per_1m_input_usd=1.20,
        cost_per_1m_output_usd=3.60,
        typical_latency_ms=1650,
        role_description="Deep architectural planning, escalated code repair, and final adjudication",
    ),
    "PHYSICAL": ModelTierSpec(
        tier_id="PHYSICAL",
        primary_model_id="nvidia/Cosmos-Reason1-7B",
        fallback_model_ids=("nvidia/Llama-3_1-Nemotron-Ultra-253B-v1",),
        cost_per_1m_input_usd=0.40,
        cost_per_1m_output_usd=1.20,
        typical_latency_ms=780,
        role_description="Spatial/kinematic trajectory plausibility critic paired with analytic physics checks",
    ),
}


@dataclass
class TaskRequest:
    objective: str
    task_type: str = "hybrid"  # "code" | "physical" | "research" | "hybrid"
    mode: str = "simulated"    # "live" | "simulated" | "hybrid"
    max_repair_iterations: int = 2
    confidence_escalation_threshold: float = 0.70
    constraints: Dict[str, Any] = field(default_factory=dict)
    seed: int = 42

    def validate(self) -> None:
        if not isinstance(self.objective, str) or not self.objective.strip():
            raise ValueError("TaskRequest.objective must be a non-empty string.")
        if len(self.objective) > 16000:
            raise ValueError("TaskRequest.objective exceeds maximum length of 16,000 characters.")
        if self.task_type not in ALLOWED_TASK_TYPES:
            raise ValueError(f"Invalid task_type '{self.task_type}'. Must be one of {ALLOWED_TASK_TYPES}.")
        if self.mode not in ALLOWED_MODES:
            raise ValueError(f"Invalid mode '{self.mode}'. Must be one of {ALLOWED_MODES}.")
        import math
        if isinstance(self.max_repair_iterations, bool) or not isinstance(self.max_repair_iterations, int) or not (0 <= self.max_repair_iterations <= 5):
            raise ValueError("max_repair_iterations must be an integer between 0 and 5.")
        if isinstance(self.confidence_escalation_threshold, bool) or not isinstance(self.confidence_escalation_threshold, (int, float)) or not math.isfinite(self.confidence_escalation_threshold) or not (0.0 <= float(self.confidence_escalation_threshold) <= 1.0):
            raise ValueError("confidence_escalation_threshold must be a finite float in [0.0, 1.0].")


@dataclass
class CitationVerdict:
    citation_id: str
    claim_text: str
    url: str
    title: str
    status: str  # "supported" | "weak" | "unsupported" | "unverified"
    overlap_score: float
    supporting_passage: str
    reason: str
    execution_mode: str = "simulated"

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class CodeVerificationReport:
    passed: bool
    ast_safe: bool
    ast_violations: List[str]
    execution_attempted: bool
    execution_policy: str
    exit_code: int
    tests_run: int
    tests_passed: int
    stdout_excerpt: str
    stderr_excerpt: str
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class KinematicWaypoint:
    t_sec: float
    x_m: float
    y_m: float
    z_m: float
    vx_mps: float = 0.0
    vy_mps: float = 0.0
    vz_mps: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class PhysicalVerificationReport:
    passed: bool
    plausibility_score: float
    max_velocity_mps: float
    velocity_limit_mps: float
    max_acceleration_mps2: float
    acceleration_limit_mps2: float
    min_obstacle_clearance_m: float
    clearance_limit_m: float
    workspace_bounds_ok: bool
    payload_torque_nm: float
    torque_limit_nm: float
    violations: List[str]
    waypoints: List[KinematicWaypoint]
    cosmos_critic_summary: str
    cosmos_execution_mode: str = "simulated"

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["waypoints"] = [w.to_dict() for w in self.waypoints]
        return d


@dataclass
class AgentStageTrace:
    stage_index: int
    stage_name: str
    tier_id: str
    requested_model_id: str
    served_model_id: str
    execution_mode: str  # "live" | "simulated" | "fallback"
    is_estimated_telemetry: bool
    confidence: float
    escalated_to_deep: bool
    escalation_reason: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    estimated_cost_usd: float
    summary: str
    degraded_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class AuditEntry:
    seq: int
    timestamp_utc: str
    stage_name: str
    action: str
    execution_mode: str
    payload_redacted: Dict[str, Any]
    prev_hash: str
    entry_hash: str
    hmac_signature: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


class AuditTrail:
    """
    Tamper-evident SHA-256 hash chain + HMAC-SHA256 audit log with automatic secret/PII redaction.
    Separates `chain_verified` from `hmac_verified` and `hmac_configured` as required by Luna 5.6 review.
    """

    def __init__(self, hmac_secret: Optional[str] = None) -> None:
        self._hmac_configured = bool(hmac_secret and hmac_secret.strip())
        self._secret_bytes = (hmac_secret.strip() if self._hmac_configured else "ephemeral-unconfigured-key").encode("utf-8")
        self._entries: List[AuditEntry] = []

    @property
    def hmac_configured(self) -> bool:
        return self._hmac_configured

    @property
    def entries(self) -> List[AuditEntry]:
        return list(self._entries)

    def append(
        self,
        stage_name: str,
        action: str,
        execution_mode: str,
        payload: Dict[str, Any],
        timestamp_utc: Optional[str] = None,
    ) -> AuditEntry:
        seq = len(self._entries) + 1
        ts = timestamp_utc or utc_now_iso()
        prev_hash = self._entries[-1].entry_hash if self._entries else "0" * 64
        safe_payload = redact_structure(payload)
        canonical = json.dumps(
            {
                "seq": seq,
                "timestamp_utc": ts,
                "stage_name": stage_name,
                "action": action,
                "execution_mode": execution_mode,
                "payload": safe_payload,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        sig = hmac.new(self._secret_bytes, entry_hash.encode("utf-8"), hashlib.sha256).hexdigest()
        entry = AuditEntry(
            seq=seq,
            timestamp_utc=ts,
            stage_name=stage_name,
            action=action,
            execution_mode=execution_mode,
            payload_redacted=safe_payload,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
            hmac_signature=sig,
        )
        self._entries.append(entry)
        return entry

    def verify(self) -> Dict[str, Any]:
        prev_hash = "0" * 64
        chain_ok = True
        hmac_ok = True
        failed_seq: Optional[int] = None

        for entry in self._entries:
            if entry.prev_hash != prev_hash:
                chain_ok = False
                failed_seq = entry.seq
                break
            canonical = json.dumps(
                {
                    "seq": entry.seq,
                    "timestamp_utc": entry.timestamp_utc,
                    "stage_name": entry.stage_name,
                    "action": entry.action,
                    "execution_mode": entry.execution_mode,
                    "payload": entry.payload_redacted,
                    "prev_hash": entry.prev_hash,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if expected_hash != entry.entry_hash:
                chain_ok = False
                failed_seq = entry.seq
                break
            expected_sig = hmac.new(self._secret_bytes, expected_hash.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_sig, entry.hmac_signature):
                hmac_ok = False
                failed_seq = entry.seq
                break
            prev_hash = entry.entry_hash

        return {
            "chain_verified": chain_ok,
            "hmac_verified": hmac_ok and self._hmac_configured,
            "signature_Check_passed": hmac_ok,
            "hmac_configured": self._hmac_configured,
            "entry_count": len(self._entries),
            "head_hash": self._entries[-1].entry_hash if self._entries else "0" * 64,
            "failed_seq": failed_seq,
        }


@dataclass
class RunResult:
    run_id: str
    objective: str
    task_type: str
    requested_mode: str
    effective_mode: str  # "live" | "simulated" | "fallback"
    is_estimated_telemetry: bool
    sim_version: str
    seed: int
    result_digest: str
    final_answer: str
    generated_code: str
    generated_tests: str
    stages: List[AgentStageTrace]
    citations: List[CitationVerdict]
    omitted_claims: List[CitationVerdict]
    code_verification: CodeVerificationReport
    physical_verification: PhysicalVerificationReport
    cost_summary: Dict[str, Any]
    audit_verification: Dict[str, Any]
    audit_entries: List[AuditEntry]
    created_at_jst: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "objective": self.objective,
            "task_type": self.task_type,
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "is_estimated_telemetry": self.is_estimated_telemetry,
            "sim_version": self.sim_version,
            "seed": self.seed,
            "result_digest": self.result_digest,
            "final_answer": self.final_answer,
            "generated_code": self.generated_code,
            "generated_tests": self.generated_tests,
            "stages": [s.to_dict() for s in self.stages],
            "citations": [c.to_dict() for c in self.citations],
            "omitted_claims": [c.to_dict() for c in self.omitted_claims],
            "code_verification": self.code_verification.to_dict(),
            "physical_verification": self.physical_verification.to_dict(),
            "cost_summary": self.cost_summary,
            "audit_verification": self.audit_verification,
            "audit_entries": [a.to_dict() for a in self.audit_entries],
            "created_at_jst": self.created_at_jst,
        }


def compute_deterministic_digest(
    objective: str,
    task_type: str,
    seed: int,
    generated_code: str,
    citations: List[CitationVerdict],
    code_passed: bool,
    physical_passed: bool,
) -> str:
    """
    Computes a wall-clock-independent SHA-256 digest over semantic outputs so
    simulation runs with the same (objective, task_type, seed, SIM_VERSION) produce
    an identical `result_digest`.
    """
    payload = {
        "sim_version": SIM_VERSION,
        "objective": objective.strip(),
        "task_type": task_type,
        "seed": seed,
        "generated_code_sha256": hashlib.sha256(generated_code.encode("utf-8")).hexdigest(),
        "citations": [
            {"id": c.citation_id, "status": c.status, "overlap": round(c.overlap_score, 4)}
            for c in citations
        ],
        "code_passed": code_passed,
        "physical_passed": physical_passed,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
