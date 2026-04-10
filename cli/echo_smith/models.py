"""Echo-smith data models.

Defines the core data contract between the Skill (data producer)
and the CLI (data consumer). All models use Pydantic v2.
"""

from __future__ import annotations

import secrets
from datetime import datetime, date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── ID generation ────────────────────────────────────────────────────


def generate_id(prefix: str) -> str:
    """Generate a unique ID in the format ``{prefix}-{YYYYMMDD}-{hex6}``."""
    today = date.today().strftime("%Y%m%d")
    rand = secrets.token_hex(3)  # 3 bytes → 6 hex chars
    return f"{prefix}-{today}-{rand}"


# ── Enums ────────────────────────────────────────────────────────────


class InsightType(str, Enum):
    knowledge_gap = "knowledge_gap"
    wrong_assumption = "wrong_assumption"
    missed_signal = "missed_signal"
    inefficient_strategy = "inefficient_strategy"
    communication_failure = "communication_failure"
    tool_misuse = "tool_misuse"
    premature_action = "premature_action"
    context_blindness = "context_blindness"


class InsightStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    archived = "archived"


class SFTType(str, Enum):
    exploration_compression = "exploration_compression"
    signal_recognition = "signal_recognition"
    tool_selection = "tool_selection"
    error_recovery = "error_recovery"
    architecture_choice = "architecture_choice"
    communication_style = "communication_style"


class CorrectionAction(str, Enum):
    supersede = "supersede"
    amend = "amend"
    retract = "retract"


class ReminderStatus(str, Enum):
    pending_approval = "pending_approval"
    active = "active"
    expired = "expired"
    rejected = "rejected"


class CorrectionType(str, Enum):
    genuine_improvement = "genuine_improvement"
    stylistic_preference = "stylistic_preference"
    factual_error = "factual_error"


class TaskOutcome(str, Enum):
    success = "success"
    partial = "partial"
    failure = "failure"
    abandoned = "abandoned"


class TriggerMode(str, Enum):
    auto = "auto"
    manual = "manual"
    scheduled = "scheduled"


class GeneralizationLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class ReminderScope(str, Enum):
    global_ = "global"
    project = "project"
    language = "language"

    # Allow "global" as a value even though it's a Python keyword
    @classmethod
    def _missing_(cls, value: object) -> Optional[ReminderScope]:
        for member in cls:
            if member.value == value:
                return member
        return None


class AdversarialVerdict(str, Enum):
    high_confidence = "high_confidence"
    low_confidence = "low_confidence"
    uncertain = "uncertain"


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
    input: Optional[str] = None
    output: Optional[str] = None


class SFTQuery(BaseModel):
    system_context: str
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    decision_point: str


class ReminderLifecycle(BaseModel):
    validation_count: int = 0
    contradiction_count: int = 0
    last_validated: Optional[datetime] = None
    confidence: float = Field(ge=0, le=1)
    written_to_claude_md: bool = False
    user_approved: bool = False


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


class SFTSample(BaseModel):
    id: str
    insight_id: str
    created_at: datetime
    version: str
    sft_type: SFTType
    query: SFTQuery
    cot: str
    response: str
    quality: SFTQualityScore
    dpo_rejected_available: bool = False


class Reminder(BaseModel):
    id: str
    insight_id: str
    created_at: datetime
    status: ReminderStatus
    rule: str
    claude_md_text: str
    lifecycle: ReminderLifecycle
    scope: ReminderScope


class Correction(BaseModel):
    id: str
    created_at: datetime
    target_type: str
    target_id: str
    action: CorrectionAction
    reason: str
    new_insight_id: Optional[str] = None
    lesson: Optional[CorrectionLesson] = None
