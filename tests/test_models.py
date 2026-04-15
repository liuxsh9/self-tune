"""Tests for Self-tune Pydantic data models."""

import json
import re
from pathlib import Path

import pytest

from self_tune.models import (
    Correction,
    Insight,
    SFTAction,
    SFTSample,
    SFTType,
    Trace,
    ConversationMessage,
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
    # Ensure all SFT types exist
    expected_types = {
        "user_prompt_internalization",
        "exploration_compression",
        "error_correction",
        "preference_to_inquiry",
        "backtrack_decision",
        "tool_orchestration",
        "success_exemplar",
        "diagnostic_recovery",
    }
    actual_types = {t.value for t in SFTType}
    assert expected_types == actual_types


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


# ── ConversationMessage source field ────────────────────────────────

def test_conversation_message_source_verbatim():
    """source field accepts 'verbatim'."""
    m = ConversationMessage(role="user", content="hello", source="verbatim")
    assert m.source == "verbatim"


def test_conversation_message_source_reconstructed():
    """source field accepts 'reconstructed'."""
    m = ConversationMessage(role="tool", name="Bash", source="reconstructed")
    assert m.source == "reconstructed"


def test_conversation_message_source_default_none():
    """source field defaults to None for backwards compatibility."""
    m = ConversationMessage(role="assistant", content="ok")
    assert m.source is None


def test_conversation_message_source_rejects_invalid():
    """source field rejects values outside the Literal."""
    with pytest.raises(Exception):
        ConversationMessage(role="user", content="x", source="raw")


def test_sft_sample_review_status_default():
    """review_status defaults to 'pending' for new and legacy samples."""
    data = load_fixture("sample_sft.json")
    sample = SFTSample.model_validate(data)
    assert sample.review_status == "pending"


def test_sft_sample_review_status_values():
    """review_status accepts valid values and rejects invalid ones."""
    data = load_fixture("sample_sft.json")
    for status in ["pending", "approved", "rejected"]:
        data["review_status"] = status
        sample = SFTSample.model_validate(data)
        assert sample.review_status == status

    data["review_status"] = "maybe"
    with pytest.raises(Exception):
        SFTSample.model_validate(data)


def test_sft_sample_quality_tier_default():
    """quality_tier defaults to 'standard' for new and legacy samples."""
    data = load_fixture("sample_sft.json")
    sample = SFTSample.model_validate(data)
    assert sample.quality_tier == "standard"


def test_sft_sample_quality_tier_values():
    """quality_tier accepts valid values and rejects invalid ones."""
    data = load_fixture("sample_sft.json")
    for tier in ["standard", "premium"]:
        data["quality_tier"] = tier
        sample = SFTSample.model_validate(data)
        assert sample.quality_tier == tier

    data["quality_tier"] = "ultra"
    with pytest.raises(Exception):
        SFTSample.model_validate(data)


# ── input field accepts str and dict ──────────────────────────────


def test_sft_action_input_accepts_str():
    """SFTAction.input accepts a plain string (single-param tools)."""
    action = SFTAction(tool="Bash", input="date")
    assert action.input == "date"


def test_sft_action_input_accepts_dict():
    """SFTAction.input accepts a dict (multi-param tools like Edit)."""
    action = SFTAction(tool="Edit", input={
        "file_path": "src/main.py",
        "old_string": "foo",
        "new_string": "bar",
    })
    assert isinstance(action.input, dict)
    assert action.input["file_path"] == "src/main.py"
    assert action.input["old_string"] == "foo"


def test_conversation_message_input_accepts_dict():
    """ConversationMessage.input accepts a dict for multi-param tools."""
    msg = ConversationMessage(
        role="tool",
        name="Edit",
        input={"file_path": "a.py", "old_string": "x", "new_string": "y"},
        output="ok",
    )
    assert isinstance(msg.input, dict)
    assert msg.input["file_path"] == "a.py"


def test_conversation_message_input_accepts_str():
    """ConversationMessage.input still accepts a plain string."""
    msg = ConversationMessage(role="tool", name="Bash", input="ls", output="file.txt")
    assert msg.input == "ls"


def test_sft_sample_with_dict_action_roundtrips():
    """SFTSample with dict action survives JSON serialization round-trip."""
    data = load_fixture("sample_sft.json")
    data["action"] = {"tool": "Edit", "input": {
        "file_path": "src/main.py",
        "old_string": "foo",
        "new_string": "bar",
    }}
    sample = SFTSample.model_validate(data)
    dumped = json.loads(sample.model_dump_json())
    assert dumped["action"]["input"]["old_string"] == "foo"
