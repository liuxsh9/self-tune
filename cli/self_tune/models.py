"""Self-tune data models.

Defines the core data contract between the Skill (data producer)
and the CLI (data consumer). All models use Pydantic v2.
"""

from __future__ import annotations

import secrets
from datetime import datetime, date
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── ID generation ────────────────────────────────────────────────────


def generate_id(prefix: str) -> str:
    """Generate a unique ID in the format ``{prefix}-{YYYYMMDD}-{hex6}``."""
    today = date.today().strftime("%Y%m%d")
    rand = secrets.token_hex(3)  # 3 bytes → 6 hex chars
    return f"{prefix}-{today}-{rand}"


# ── Enums ────────────────────────────────────────────────────────────


class InsightType(str, Enum):
    skill_gap = "skill_gap"
    knowledge_gap = "knowledge_gap"
    reasoning_error = "reasoning_error"
    exploration_inefficiency = "exploration_inefficiency"
    tool_orchestration = "tool_orchestration"
    backtrack_failure = "backtrack_failure"
    preference_probe = "preference_probe"
    env_specific = "env_specific"


class InsightStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    archived = "archived"


class SFTType(str, Enum):
    user_prompt_internalization = "user_prompt_internalization"
    exploration_compression = "exploration_compression"
    error_correction = "error_correction"
    preference_to_inquiry = "preference_to_inquiry"
    backtrack_decision = "backtrack_decision"
    tool_orchestration = "tool_orchestration"


class CorrectionAction(str, Enum):
    supersede = "supersede"
    amend = "amend"
    retract = "retract"



class CorrectionType(str, Enum):
    genuine_improvement = "genuine_improvement"
    stylistic_preference = "stylistic_preference"
    factual_error = "factual_error"


class TaskOutcome(str, Enum):
    success = "success"
    success_after_correction = "success_after_correction"
    partial = "partial"
    failure = "failure"
    abandoned = "abandoned"


class TriggerMode(str, Enum):
    auto = "auto"
    manual = "manual"
    scheduled = "scheduled"
    sidecar = "sidecar"
    retrospective = "retrospective"
    user_correction = "user_correction"


class GeneralizationLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"



class AdversarialVerdict(str, Enum):
    high_confidence = "high_confidence"
    moderate = "moderate"
    contested = "contested"


# ── Sub-models ───────────────────────────────────────────────────────


class ProjectContext(BaseModel):
    language: str
    framework: Optional[str] = None
    repo: Optional[str] = None


class ConversationSegment(BaseModel):
    role: str
    summary: Optional[str] = None
    name: Optional[str] = None
    is_key_signal: Optional[bool] = None
    is_correction: Optional[bool] = None


class ConversationSnapshot(BaseModel):
    segments: list[ConversationSegment] = Field(default_factory=list)


class RootCause(BaseModel):
    concrete: str
    abstract: str


class UserCorrection(BaseModel):
    type: CorrectionType
    description: str


class Attribution(BaseModel):
    argument: str
    confidence: float = Field(ge=0, le=1)


class AdversarialReflection(BaseModel):
    attribution_a: Attribution
    attribution_b: Attribution
    verdict: AdversarialVerdict


class GeneralizationLadder(BaseModel):
    L1: str
    L2: str
    L3: str
    selected_level: GeneralizationLevel


class MissedSignal(BaseModel):
    round: int
    tool: str
    signal: str
    why_missed: str


class EfficiencyMetrics(BaseModel):
    actual_rounds: int
    optimal_rounds: int
    wasted_rounds: int
    t_optimal: int
    missed_signals: list[MissedSignal] = Field(default_factory=list)


class QualityScore(BaseModel):
    local_score: Optional[float] = None
    server_score: Optional[float] = None


class SFTQualityScore(BaseModel):
    local_score: Optional[float] = None
    server_score: Optional[float] = None
    evidence_anchored: Optional[bool] = None
    no_post_hoc_rationalization: Optional[bool] = None
    no_content_free_hedging: Optional[bool] = None


class ConversationMessage(BaseModel):
    role: str
    content: Optional[str] = None
    name: Optional[str] = None
    input: Optional[str | dict[str, Any]] = None
    output: Optional[str] = None
    source: Optional[Literal["verbatim", "reconstructed"]] = None


class SFTQuery(BaseModel):
    system_context: str
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    decision_point: str



class CorrectionLesson(BaseModel):
    abstract: str
    generates_new_sample: bool = False


# ── Top-level models ─────────────────────────────────────────────────


class Trace(BaseModel):
    id: str
    created_at: datetime
    source: str
    model: str
    trigger: TriggerMode
    task_description: str
    task_outcome: TaskOutcome
    project_context: ProjectContext
    episodes: list[str] = Field(default_factory=list)
    conversation_snapshot: ConversationSnapshot


class Insight(BaseModel):
    id: str
    trace_id: str
    created_at: datetime
    insight_type: InsightType
    status: InsightStatus
    root_cause: RootCause
    user_correction: Optional[UserCorrection] = None
    adversarial_reflection: AdversarialReflection
    generalization_ladder: GeneralizationLadder
    efficiency_metrics: Optional[EfficiencyMetrics] = None
    independent_value: bool = True
    value_rationale: Optional[str] = None
    quality: QualityScore


class SFTAction(BaseModel):
    """The correct tool call the model should make at the decision point."""
    tool: str
    input: str | dict[str, Any]


class DPORejected(BaseModel):
    response: str
    failure_mode: str


class SFTSample(BaseModel):
    id: str
    insight_id: str
    trace_id: Optional[str] = None
    created_at: datetime
    version: Literal["concrete", "abstract"]
    sft_type: SFTType
    query: SFTQuery
    cot: str
    response: str
    action: Optional[SFTAction] = None
    quality: SFTQualityScore
    dpo_rejected_available: bool = False
    dpo_rejected: Optional[DPORejected] = None
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    quality_tier: Literal["standard", "premium"] = "standard"


class Correction(BaseModel):
    id: str
    created_at: datetime
    target_type: str
    target_id: str
    action: CorrectionAction
    reason: str
    new_insight_id: Optional[str] = None
    lesson: Optional[CorrectionLesson] = None
