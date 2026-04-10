"""Tests for Echo-smith Pydantic data models."""

import json
import re
from pathlib import Path

import pytest

from echo_smith.models import (
    Correction,
    Insight,
    Reminder,
    SFTSample,
    SFTType,
    Trace,
    generate_id,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ── generate_id ──────────────────────────────────────────────────────

def test_generate_id_format():
    """IDs follow {type}-{YYYYMMDD}-{random6} format."""
    id_ = generate_id("trace")
    pattern = r"^trace-\d{8}-[0-9a-f]{6}$"
    assert re.match(pattern, id_), f"ID '{id_}' does not match pattern {pattern}"


def test_generate_id_uniqueness():
    """Two calls produce different IDs."""
    a = generate_id("ins")
    b = generate_id("ins")
    assert a != b


# ── Fixture-based model validation ───────────────────────────────────

def test_trace_from_fixture():
    """Trace model validates fixture JSON."""
    data = load_fixture("sample_trace.json")
    trace = Trace.model_validate(data)
    assert trace.id == "trace-20260410-a1b2c3"
    assert trace.task_outcome.value == "success"
    assert len(trace.conversation_snapshot.segments) == 3
    assert trace.project_context.language == "typescript"


def test_insight_from_fixture():
    """Insight model validates fixture, including adversarial_reflection and generalization_ladder."""
    data = load_fixture("sample_insight.json")
    insight = Insight.model_validate(data)
    assert insight.id == "ins-20260410-d4e5f6"
    assert insight.insight_type.value == "knowledge_gap"
    # adversarial_reflection
    assert insight.adversarial_reflection.attribution_a.confidence == 0.88
    assert insight.adversarial_reflection.verdict.value == "high_confidence"
    # generalization_ladder
    assert insight.generalization_ladder.selected_level.value == "L1"
    assert "RS256" in insight.generalization_ladder.L1


def test_sft_sample_from_fixture():
    """SFT sample model validates fixture, checks all SFT types."""
    data = load_fixture("sample_sft.json")
    sample = SFTSample.model_validate(data)
    assert sample.id == "sft-20260410-g7h8i9"
    assert sample.sft_type == SFTType.exploration_compression
    # Ensure all 6 SFT types exist
    expected_types = {
        "user_prompt_internalization",
        "exploration_compression",
        "error_correction",
        "preference_to_inquiry",
        "backtrack_decision",
        "tool_orchestration",
    }
    actual_types = {t.value for t in SFTType}
    assert expected_types == actual_types


def test_reminder_from_fixture():
    """Reminder model validates fixture."""
    data = load_fixture("sample_reminder.json")
    reminder = Reminder.model_validate(data)
    assert reminder.id == "rem-20260410-j0k1l2"
    assert reminder.status.value == "pending_approval"
    assert reminder.lifecycle.confidence == 0.82
    assert reminder.lifecycle.written_to_claude_md is False


def test_correction_from_fixture():
    """Correction model validates fixture."""
    data = load_fixture("sample_correction.json")
    correction = Correction.model_validate(data)
    assert correction.id == "cor-20260412-m3n4o5"
    assert correction.action.value == "supersede"
    assert correction.new_insight_id == "ins-20260412-p6q7r8"
    assert correction.lesson.generates_new_sample is True


# ── Constraint / edge-case tests ─────────────────────────────────────

def test_sft_sample_query_has_tool_interactions():
    """SFT query must contain tool role in conversation_history."""
    data = load_fixture("sample_sft.json")
    sample = SFTSample.model_validate(data)
    roles = [msg.role for msg in sample.query.conversation_history]
    assert "tool" in roles, "SFT query conversation_history must contain at least one tool message"


def test_insight_adversarial_confidence_range():
    """Confidence scores must be 0-1."""
    data = load_fixture("sample_insight.json")
    insight = Insight.model_validate(data)
    a_conf = insight.adversarial_reflection.attribution_a.confidence
    b_conf = insight.adversarial_reflection.attribution_b.confidence
    assert 0 <= a_conf <= 1, f"attribution_a confidence {a_conf} out of range"
    assert 0 <= b_conf <= 1, f"attribution_b confidence {b_conf} out of range"

    # Also verify the model rejects out-of-range values
    data["adversarial_reflection"]["attribution_a"]["confidence"] = 1.5
    with pytest.raises(Exception):
        Insight.model_validate(data)
