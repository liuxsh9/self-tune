# tests/test_export.py
import json
from pathlib import Path

import pytest

from self_tune.models import SFTSample, Insight
from self_tune.store import SelfTuneStore
from self_tune.export import export_sft, export_dpo, export_jsonl, export_anthropic, export_chatml, ExportValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_store(tmp_path) -> SelfTuneStore:
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))
    return store


def test_export_sft_format(tmp_path):
    """SFT export produces OpenAI-compatible messages-format JSONL."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 1
    line = json.loads(output.read_text().strip())
    assert "messages" in line
    messages = line["messages"]
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "assistant" in roles


def test_export_sft_tool_calls_format(tmp_path):
    """SFT export uses proper tool_calls on assistant + role:tool for results."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    line = json.loads(output.read_text().strip())
    messages = line["messages"]

    # Find tool interaction pair: assistant with tool_calls + tool response
    tool_call_msgs = [m for m in messages if "tool_calls" in m]
    tool_response_msgs = [m for m in messages if m["role"] == "tool"]

    # The fixture has tool interactions (Read, Grep)
    assert len(tool_call_msgs) > 0, "Should have assistant messages with tool_calls"
    assert len(tool_response_msgs) > 0, "Should have tool response messages"

    # Verify tool_calls structure
    tc = tool_call_msgs[0]["tool_calls"][0]
    assert "id" in tc
    assert tc["type"] == "function"
    assert "name" in tc["function"]
    assert "arguments" in tc["function"]

    # Verify tool response references the call
    tr = tool_response_msgs[0]
    assert "tool_call_id" in tr
    assert tr["tool_call_id"] == tc["id"]


def test_export_sft_has_tools_array(tmp_path):
    """SFT export includes tools array when tool interactions exist."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    line = json.loads(output.read_text().strip())

    assert "tools" in line, "Should include tools array"
    assert len(line["tools"]) > 0
    tool = line["tools"][0]
    assert tool["type"] == "function"
    assert "name" in tool["function"]


def test_export_sft_weight_field(tmp_path):
    """Context messages have weight:0, final assistant has weight:1."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    line = json.loads(output.read_text().strip())
    messages = line["messages"]

    # All messages except the last should have weight:0
    for msg in messages[:-1]:
        assert msg.get("weight") == 0, f"Context message should have weight:0: {msg['role']}"

    # Last message (training target) should have weight:1
    last = messages[-1]
    assert last["role"] == "assistant"
    assert last.get("weight") == 1


def test_export_dpo_format(tmp_path):
    """DPO export produces prompt/chosen/rejected JSONL."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_dpo(store, output)
    assert count == 1
    line = json.loads(output.read_text().strip())
    assert "prompt" in line
    assert "chosen" in line
    assert "rejected" in line


def test_export_jsonl_format(tmp_path):
    """JSONL export dumps raw sample objects."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_jsonl(store, output)
    assert count == 1
    line = json.loads(output.read_text().strip())
    assert "id" in line
    assert "sft_type" in line


def test_export_with_score_filter(tmp_path):
    """Export with min_score filters low-quality samples."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_sft(store, output, min_score=0.99)
    assert count == 0
    assert output.read_text().strip() == ""


def test_export_sft_action_as_tool_call(tmp_path):
    """When SFT sample has action field, weight:1 turn emits tool_calls."""
    store = _seed_store(tmp_path)

    # Create a sample with action field
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-action"
    sft_data["action"] = {"tool": "Bash", "input": "date"}
    sft_data["response"] = "Check current time before scheduling"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    export_sft(store, output)

    # Find the action sample (sorted by ID, "action" < "g7h8i9" so it's first)
    lines = output.read_text().strip().split("\n")
    assert len(lines) == 2
    action_line = json.loads(lines[0])
    messages = action_line["messages"]

    # Last message should have tool_calls + weight:1
    last = messages[-1]
    assert last["role"] == "assistant"
    assert last["weight"] == 1
    assert "tool_calls" in last
    assert last["tool_calls"][0]["function"]["name"] == "Bash"
    assert "<think>" in last["content"]
    # Content should NOT include the response text (it's in CoT only)
    assert "date" in last["tool_calls"][0]["function"]["arguments"]


def test_export_rejects_invalid_tool_name(tmp_path):
    """Export raises ExportValidationError when action.tool is not in AGENTIC_TOOLS."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-badtool"
    sft_data["action"] = {"tool": "MadeUpTool", "input": "foo"}
    sft_data["response"] = "intent"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    with pytest.raises(ExportValidationError, match="MadeUpTool"):
        export_sft(store, output)


def test_export_rejects_empty_training_target(tmp_path):
    """Export raises ExportValidationError when response is empty and action is None."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-empty"
    sft_data["response"] = ""
    sft_data["action"] = None
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    with pytest.raises(ExportValidationError, match="no training target"):
        export_sft(store, output)


def test_export_rejects_consecutive_same_role(tmp_path):
    """Export raises ExportValidationError on consecutive user or assistant messages."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-badrole"
    sft_data["query"]["conversation_history"] = [
        {"role": "user", "content": "first question"},
        {"role": "user", "content": "second question"},  # invalid consecutive user
        {"role": "assistant", "content": "answer"},
    ]
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    with pytest.raises(ExportValidationError, match="consecutive 'user'"):
        export_sft(store, output)


def test_export_sft_filters_unapproved(tmp_path):
    """Default export only includes approved samples; pending/rejected are excluded."""
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))

    # Save a pending sample (no review_status set → defaults to "pending")
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    store.save_sample(SFTSample.model_validate(sft_data))

    # Default export excludes pending samples
    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 0
    assert output.read_text().strip() == ""

    # Approve the sample and verify it's now included
    store.update_sample("sft-20260410-g7h8i9", review_status="approved")
    count = export_sft(store, output)
    assert count == 1


def test_export_sft_include_pending(tmp_path):
    """--include-pending flag exports pending and approved samples."""
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))

    # Save a pending sample (default review_status)
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    # With include_pending=True, pending samples are included
    count = export_sft(store, output, include_pending=True)
    assert count == 1

    # With include_pending=False (default), pending samples are excluded
    count = export_sft(store, output)
    assert count == 0


def test_export_sft_excludes_rejected(tmp_path):
    """Rejected samples are never exported, even with --include-pending."""
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["review_status"] = "rejected"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    # Rejected excluded by default
    count = export_sft(store, output)
    assert count == 0
    # Rejected excluded even with include_pending
    count = export_sft(store, output, include_pending=True)
    assert count == 0


def test_export_anthropic_format(tmp_path):
    """Anthropic format has system + messages with tool_use/tool_result blocks."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_anthropic(store, output)
    assert count == 1
    row = json.loads(output.read_text().strip())
    assert "system" in row
    assert "messages" in row
    has_tool_use = any(
        isinstance(m.get("content"), list) and
        any(b.get("type") == "tool_use" for b in m["content"])
        for m in row["messages"] if m["role"] == "assistant"
    )
    assert has_tool_use, "Anthropic format must have tool_use content blocks"

    # Must include Anthropic-style tool definitions
    assert "tools" in row
    assert len(row["tools"]) > 0
    tool = row["tools"][0]
    assert "name" in tool
    assert "input_schema" in tool


def test_export_anthropic_final_turn(tmp_path):
    """Anthropic format final turn has thinking block (fixture has no action → text path)."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_anthropic(store, output)
    row = json.loads(output.read_text().strip())
    final = row["messages"][-1]
    assert final["role"] == "assistant"
    assert isinstance(final["content"], list)
    thinking_blocks = [b for b in final["content"] if b.get("type") == "thinking"]
    assert len(thinking_blocks) == 1
    # No action in fixture → text block, not tool_use
    text_blocks = [b for b in final["content"] if b.get("type") == "text"]
    assert len(text_blocks) == 1


def test_export_anthropic_action_as_tool_use(tmp_path):
    """Anthropic format final turn emits tool_use when action is present."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-antact"
    sft_data["action"] = {"tool": "Bash", "input": "date"}
    sft_data["response"] = "Check current time"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    export_anthropic(store, output)
    lines = output.read_text().strip().split("\n")
    # "antact" < "g7h8i9" alphabetically → first line
    action_row = json.loads(lines[0])
    final = action_row["messages"][-1]
    assert final["role"] == "assistant"
    assert isinstance(final["content"], list)
    tool_use_blocks = [b for b in final["content"] if b.get("type") == "tool_use"]
    assert len(tool_use_blocks) == 1
    assert tool_use_blocks[0]["name"] == "Bash"
    thinking_blocks = [b for b in final["content"] if b.get("type") == "thinking"]
    assert len(thinking_blocks) == 1


def test_export_anthropic_role_alternation(tmp_path):
    """Anthropic format maintains strict user/assistant alternation."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_anthropic(store, output)
    row = json.loads(output.read_text().strip())
    roles = [m["role"] for m in row["messages"]]
    for i in range(1, len(roles)):
        assert roles[i] != roles[i - 1], (
            f"Consecutive same role at {i - 1},{i}: '{roles[i]}'"
        )


def test_export_chatml_format(tmp_path):
    """ChatML format has messages array with system/user/assistant/function roles."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_chatml(store, output)
    assert count == 1
    row = json.loads(output.read_text().strip())
    assert "messages" in row
    roles = [m["role"] for m in row["messages"]]
    assert roles[0] == "system"
    assert "function" in roles, "ChatML format must have function role for tool responses"


def test_export_chatml_final_turn(tmp_path):
    """ChatML final turn has think tags (fixture has no action → text-only path)."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_chatml(store, output)
    row = json.loads(output.read_text().strip())
    final = row["messages"][-1]
    assert final["role"] == "assistant"
    assert "<think>" in final["content"]
    # No action in fixture → no function_call on final turn
    assert "function_call" not in final


def test_export_chatml_action_as_function_call(tmp_path):
    """ChatML final turn emits function_call when action is present."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-cmlact"
    sft_data["action"] = {"tool": "Bash", "input": "date"}
    sft_data["response"] = "Check current time"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    export_chatml(store, output)
    lines = output.read_text().strip().split("\n")
    action_row = json.loads(lines[0])
    final = action_row["messages"][-1]
    assert final["role"] == "assistant"
    assert "function_call" in final
    assert final["function_call"]["name"] == "Bash"
    assert "<think>" in final["content"]
