# tests/test_export.py
import json
from pathlib import Path

import pytest

from self_tune.models import SFTSample, Insight
from self_tune.store import SelfTuneStore
from self_tune.export import export_sft, export_jsonl, export_anthropic, export_chatml, export_ml2, ExportValidationError, _validate_sample, _warn_sample

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


def test_export_skips_invalid_tool_name(tmp_path, capsys):
    """Export skips samples with invalid tool names and warns on stderr."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-badtool"
    sft_data["action"] = {"tool": "MadeUpTool", "input": "foo"}
    sft_data["response"] = "intent"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 1  # valid sample exported, invalid skipped
    captured = capsys.readouterr()
    assert "MadeUpTool" in captured.err
    assert "skipped 1" in captured.err


def test_export_skips_empty_training_target(tmp_path, capsys):
    """Export skips samples with empty response and no action."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-empty"
    sft_data["response"] = ""
    sft_data["action"] = None
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 1
    captured = capsys.readouterr()
    assert "no training target" in captured.err


def test_export_skips_consecutive_same_role(tmp_path, capsys):
    """Export skips samples with consecutive user or assistant messages."""
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
    count = export_sft(store, output)
    assert count == 1
    captured = capsys.readouterr()
    assert "consecutive 'user'" in captured.err


def test_export_sft_includes_pending_by_default(tmp_path):
    """Default export includes both pending and approved samples; rejected is excluded."""
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))

    # Save a pending sample (no review_status set → defaults to "pending")
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    store.save_sample(SFTSample.model_validate(sft_data))

    # Default export includes pending samples
    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 1

    # Approved sample also included by default
    store.update_sample("sft-20260410-g7h8i9", review_status="approved")
    count = export_sft(store, output)
    assert count == 1

    # include_pending=False restricts to approved only
    store.update_sample("sft-20260410-g7h8i9", review_status="pending")
    count = export_sft(store, output, include_pending=False)
    assert count == 0


def test_export_sft_include_pending(tmp_path):
    """include_pending=True (default) exports pending and approved; False restricts to approved."""
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))

    # Save a pending sample (default review_status)
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    # With include_pending=True (default), pending samples are included
    count = export_sft(store, output, include_pending=True)
    assert count == 1

    # With include_pending=False, pending samples are excluded
    count = export_sft(store, output, include_pending=False)
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


def test_export_ml2_format(tmp_path):
    """ML2 format has version, meta_info, messages, and tools."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_ml2(store, output)
    assert count == 1
    row = json.loads(output.read_text().strip())
    assert row["version"] == "2.0.0"
    assert "meta_info" in row
    meta = row["meta_info"]
    assert meta["teacher"] == "claude-sonnet-4-6"
    assert meta["query_source"] == "self-tune"
    assert meta["category"] == "agent"
    assert isinstance(meta["rounds"], int)
    assert "messages" in row
    assert "tools" in row  # fixture has tool interactions


def test_export_ml2_reasoning_content(tmp_path):
    """Every assistant message has a reasoning_content field."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_ml2(store, output)
    row = json.loads(output.read_text().strip())
    assistant_msgs = [m for m in row["messages"] if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 2  # at least context + final
    for msg in assistant_msgs:
        assert "reasoning_content" in msg, "assistant message missing reasoning_content"
        assert isinstance(msg["reasoning_content"], str)
    # Context assistant messages should have empty reasoning_content
    for msg in assistant_msgs[:-1]:
        assert msg["reasoning_content"] == ""
    # Final assistant should have non-empty reasoning_content (the CoT)
    assert assistant_msgs[-1]["reasoning_content"] != ""


def test_export_ml2_final_turn_no_action(tmp_path):
    """Without action: reasoning_content=cot, content=response, no tool_calls."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_ml2(store, output)
    row = json.loads(output.read_text().strip())
    final = row["messages"][-1]
    assert final["role"] == "assistant"
    assert final["reasoning_content"] != ""
    assert final["content"] != ""  # response text
    assert "tool_calls" not in final
    # No <think> tags — CoT is in reasoning_content, not content
    assert "<think>" not in final["content"]


def test_export_ml2_final_turn_with_action(tmp_path):
    """With action: reasoning_content=cot, content='', tool_calls present."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-pmlact"
    sft_data["action"] = {"tool": "Bash", "input": "date"}
    sft_data["response"] = "Check current time"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    export_ml2(store, output)
    lines = output.read_text().strip().split("\n")
    # "g7h8i9" < "pmlact" alphabetically → action sample is second line
    action_row = json.loads(lines[1])
    final = action_row["messages"][-1]
    assert final["role"] == "assistant"
    assert final["reasoning_content"] != ""
    assert final["content"] == ""
    assert "tool_calls" in final
    assert final["tool_calls"][0]["function"]["name"] == "Bash"
    assert final["weight"] == 1


def test_export_ml2_weight(tmp_path):
    """Only final assistant turn has weight:1, context messages have no weight key."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_ml2(store, output)
    row = json.loads(output.read_text().strip())
    messages = row["messages"]

    # All messages except the last should NOT have weight
    for msg in messages[:-1]:
        assert "weight" not in msg, f"Context {msg['role']} message should not have weight"

    # Last message (training target) should have weight:1
    last = messages[-1]
    assert last["role"] == "assistant"
    assert last.get("weight") == 1


def test_export_no_consecutive_assistant_sft(tmp_path):
    """SFT export merges tool_calls into preceding assistant when history has assistant→tool."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    row = json.loads(output.read_text().strip().split("\n")[0])
    roles = [m["role"] for m in row["messages"]]
    for i in range(1, len(roles)):
        assert not (roles[i] == "assistant" and roles[i - 1] == "assistant"), (
            f"Consecutive assistant at positions {i - 1},{i}: {roles}"
        )


def test_export_no_consecutive_assistant_ml2(tmp_path):
    """ML2 export merges tool_calls into preceding assistant when history has assistant→tool."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_ml2(store, output)
    row = json.loads(output.read_text().strip().split("\n")[0])
    roles = [m["role"] for m in row["messages"]]
    for i in range(1, len(roles)):
        assert not (roles[i] == "assistant" and roles[i - 1] == "assistant"), (
            f"Consecutive assistant at positions {i - 1},{i}: {roles}"
        )


def test_export_tool_arguments_use_correct_key(tmp_path):
    """Tool arguments use the correct parameter name per tool, not always 'command'."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    row = json.loads(output.read_text().strip().split("\n")[0])
    messages = row["messages"]

    # Find tool_calls and verify argument keys match the tool
    for msg in messages:
        if "tool_calls" not in msg:
            continue
        for tc in msg["tool_calls"]:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            if not args:
                continue
            key = list(args.keys())[0]
            if name == "Bash":
                assert key == "command", f"Bash should use 'command', got '{key}'"
            elif name == "Read":
                assert key == "file_path", f"Read should use 'file_path', got '{key}'"
            elif name == "Grep":
                assert key == "pattern", f"Grep should use 'pattern', got '{key}'"
            elif name == "Glob":
                assert key == "pattern", f"Glob should use 'pattern', got '{key}'"
            elif name == "Edit":
                assert key == "file_path", f"Edit should use 'file_path', got '{key}'"


def test_export_skips_not_evidence_anchored(tmp_path, capsys):
    """Export skips samples where evidence_anchored is False."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-noevid"
    sft_data["quality"]["evidence_anchored"] = False
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 1
    captured = capsys.readouterr()
    assert "evidence_anchored" in captured.err


def test_export_allows_evidence_anchored_none(tmp_path):
    """Export allows samples where evidence_anchored is None (not yet assessed)."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-evnone"
    sft_data["quality"]["evidence_anchored"] = None
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 2  # fixture + this one


def _make_edit_action_sample(store, sample_id="sft-20260410-eddict"):
    """Helper: create a sample with Edit dict action."""
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = sample_id
    sft_data["action"] = {
        "tool": "Edit",
        "input": {
            "file_path": "src/main.py",
            "old_string": "foo",
            "new_string": "bar",
        },
    }
    sft_data["response"] = "Replace foo with bar in main.py"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))


def test_export_sft_action_dict_input(tmp_path):
    """SFT export preserves all dict keys for multi-param tool actions."""
    store = _seed_store(tmp_path)
    _make_edit_action_sample(store)

    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    lines = output.read_text().strip().split("\n")
    # "eddict" < "g7h8i9" → first line
    row = json.loads(lines[0])
    final = row["messages"][-1]
    assert final["weight"] == 1
    args = json.loads(final["tool_calls"][0]["function"]["arguments"])
    assert args["file_path"] == "src/main.py"
    assert args["old_string"] == "foo"
    assert args["new_string"] == "bar"


def test_export_ml2_action_dict_input(tmp_path):
    """ML2 export preserves all dict keys for multi-param tool actions."""
    store = _seed_store(tmp_path)
    _make_edit_action_sample(store)

    output = tmp_path / "export.jsonl"
    export_ml2(store, output)
    lines = output.read_text().strip().split("\n")
    row = json.loads(lines[0])
    final = row["messages"][-1]
    assert final["weight"] == 1
    args = json.loads(final["tool_calls"][0]["function"]["arguments"])
    assert args["file_path"] == "src/main.py"
    assert args["old_string"] == "foo"
    assert args["new_string"] == "bar"


def test_export_anthropic_action_dict_input(tmp_path):
    """Anthropic export preserves all dict keys for multi-param tool actions."""
    store = _seed_store(tmp_path)
    _make_edit_action_sample(store)

    output = tmp_path / "export.jsonl"
    export_anthropic(store, output)
    lines = output.read_text().strip().split("\n")
    row = json.loads(lines[0])
    final = row["messages"][-1]
    assert final["role"] == "assistant"
    tool_use_blocks = [b for b in final["content"] if b.get("type") == "tool_use"]
    assert len(tool_use_blocks) == 1
    inp = tool_use_blocks[0]["input"]
    assert inp["file_path"] == "src/main.py"
    assert inp["old_string"] == "foo"
    assert inp["new_string"] == "bar"


def test_export_tool_arguments_dict_passthrough(tmp_path):
    """When conversation_history has dict input, export passes it through unchanged."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-dicthist"
    sft_data["query"]["conversation_history"] = [
        {"role": "user", "content": "Fix the typo"},
        {"role": "assistant", "content": "Let me edit that file."},
        {
            "role": "tool",
            "name": "Edit",
            "input": {"file_path": "src/app.py", "old_string": "teh", "new_string": "the"},
            "output": "ok",
        },
    ]
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    lines = output.read_text().strip().split("\n")
    # "dicthist" < "g7h8i9" → first line
    row = json.loads(lines[0])
    # Find the Edit tool_call in context
    for msg in row["messages"]:
        if "tool_calls" not in msg:
            continue
        for tc in msg["tool_calls"]:
            if tc["function"]["name"] == "Edit":
                args = json.loads(tc["function"]["arguments"])
                assert args["file_path"] == "src/app.py"
                assert args["old_string"] == "teh"
                assert args["new_string"] == "the"
                return
    pytest.fail("Edit tool_call not found in exported messages")


# ── max_per_type tests ──────────────────────────────────────────────


def test_export_max_per_type_caps_output(tmp_path):
    """max_per_type limits how many samples of each sft_type are exported."""
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))

    # Create 3 exploration_compression samples
    for i in range(3):
        sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
        sft_data["id"] = f"sft-20260410-cap{i:03d}"
        sft_data["review_status"] = "approved"
        store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    # Without cap: all 3
    count = export_sft(store, output)
    assert count == 3

    # With cap: max 2 per type
    count = export_sft(store, output, max_per_type=2)
    assert count == 2


def test_export_max_per_type_caps_per_type_independently(tmp_path):
    """max_per_type applies independently to each sft_type."""
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))

    # 3 exploration_compression + 2 backtrack_decision
    for i in range(3):
        sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
        sft_data["id"] = f"sft-20260410-exp{i:03d}"
        sft_data["sft_type"] = "exploration_compression"
        sft_data["review_status"] = "approved"
        store.save_sample(SFTSample.model_validate(sft_data))

    for i in range(2):
        sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
        sft_data["id"] = f"sft-20260410-bck{i:03d}"
        sft_data["sft_type"] = "backtrack_decision"
        sft_data["review_status"] = "approved"
        store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    # Cap at 2 per type: should keep 2 exploration + 2 backtrack = 4
    count = export_sft(store, output, max_per_type=2)
    assert count == 4


# ── success_exemplar tests ──────────────────────────────────────────


def test_export_success_exemplar_sample(tmp_path):
    """success_exemplar samples export correctly in all formats."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-succes"
    sft_data["sft_type"] = "success_exemplar"
    sft_data["action"] = {"tool": "Edit", "input": {"file_path": "a.py", "old_string": "x", "new_string": "y"}}
    sft_data["response"] = "Applying the efficient fix"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    for exporter in [export_sft, export_ml2, export_anthropic, export_chatml]:
        output = tmp_path / f"export_{exporter.__name__}.jsonl"
        count = exporter(store, output)
        assert count == 2  # fixture + success_exemplar
        lines = output.read_text().strip().split("\n")
        assert len(lines) == 2


# ── new tool names in export ────────────────────────────────────────


def test_export_write_tool_in_action(tmp_path):
    """Write tool in action.tool passes validation and exports correctly."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-writea"
    sft_data["action"] = {"tool": "Write", "input": {"file_path": "out.txt", "content": "hello"}}
    sft_data["response"] = "Creating the file"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 2


def test_export_agent_tool_in_action(tmp_path):
    """Agent tool in action.tool passes validation and exports correctly."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-agentt"
    sft_data["action"] = {"tool": "Agent", "input": "Investigate the auth bug"}
    sft_data["response"] = "Delegating to subagent"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 2


def test_export_lsp_tool_in_action(tmp_path):
    """LSP tool in action.tool passes validation and exports correctly."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-lsptol"
    sft_data["action"] = {"tool": "LSP", "input": {"operation": "goToDefinition", "filePath": "a.py", "line": 10, "character": 5}}
    sft_data["response"] = "Finding definition"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 2


# ── _warn_sample tests ──────────────────────────────────────────────


def test_warn_sample_short_history():
    """_warn_sample flags conversation_history shorter than 8 messages."""
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sample = SFTSample.model_validate(data)
    # Fixture has 5 messages → should warn
    warnings = _warn_sample(sample)
    assert len(warnings) == 1
    assert "conversation_history" in warnings[0]


def test_warn_sample_recovery_type_lower_threshold():
    """diagnostic_recovery with 5 messages should NOT warn (threshold is 4)."""
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    data["sft_type"] = "diagnostic_recovery"
    # Fixture has 5 messages, threshold for diagnostic_recovery is 4 → no warning
    sample = SFTSample.model_validate(data)
    warnings = _warn_sample(sample)
    assert len(warnings) == 0


def test_warn_sample_long_history_no_warning():
    """_warn_sample returns empty list for history with >= 8 messages."""
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    # Build a history with 10 messages
    data["query"]["conversation_history"] = [
        {"role": "user", "content": "task"},
    ] + [
        item
        for i in range(4)
        for item in [
            {"role": "assistant", "content": f"step {i}"},
            {"role": "tool", "name": "Bash", "input": f"cmd{i}", "output": f"out{i}"},
        ]
    ] + [
        {"role": "assistant", "content": "done"},
    ]
    sample = SFTSample.model_validate(data)
    warnings = _warn_sample(sample)
    assert len(warnings) == 0


# ── C1: _cap_by_type guard tests ──────────────────────────────────────


def test_export_max_per_type_zero_returns_empty(tmp_path):
    """max_per_type=0 returns no samples."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_sft(store, output, max_per_type=0)
    assert count == 0


def test_export_max_per_type_negative_returns_empty(tmp_path):
    """max_per_type with negative value returns no samples."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_sft(store, output, max_per_type=-1)
    assert count == 0


# ── C2: _tool_arguments empty string/dict tests ──────────────────────


def test_tool_arguments_empty_string():
    """_tool_arguments with empty string wraps it (not treated as falsy)."""
    from self_tune.export import _tool_arguments
    result = json.loads(_tool_arguments("Bash", ""))
    assert result == {"command": ""}


def test_tool_arguments_empty_dict():
    """_tool_arguments with empty dict serializes it (not treated as falsy)."""
    from self_tune.export import _tool_arguments
    result = json.loads(_tool_arguments("Edit", {}))
    assert result == {}


def test_tool_arguments_none():
    """_tool_arguments with None returns empty object."""
    from self_tune.export import _tool_arguments
    result = json.loads(_tool_arguments("Bash", None))
    assert result == {}


# ── I1: export_jsonl validation tests ────────────────────────────────


def test_export_jsonl_skips_invalid_tool(tmp_path, capsys):
    """export_jsonl skips samples with invalid tool names and warns on stderr."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-jlbadtl"
    sft_data["action"] = {"tool": "FakeTool", "input": "x"}
    sft_data["response"] = "intent"
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_jsonl(store, output)
    assert count == 1
    captured = capsys.readouterr()
    assert "FakeTool" in captured.err


# ── I2: no_post_hoc_rationalization validation tests ─────────────────


def test_export_skips_post_hoc_rationalization(tmp_path, capsys):
    """Export skips samples where no_post_hoc_rationalization is False."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-posthoc"
    sft_data["quality"]["no_post_hoc_rationalization"] = False
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 1
    captured = capsys.readouterr()
    assert "no_post_hoc_rationalization" in captured.err


def test_export_allows_post_hoc_rationalization_none(tmp_path):
    """Export allows samples where no_post_hoc_rationalization is None."""
    store = _seed_store(tmp_path)

    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["id"] = "sft-20260410-phnone"
    sft_data["quality"]["no_post_hoc_rationalization"] = None
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 2  # fixture + this one


# ── I6: _cap_by_type quality-sorted truncation ───────────────────────


def test_cap_by_type_keeps_highest_quality(tmp_path):
    """_cap_by_type keeps samples with highest quality scores when capping."""
    from self_tune.export import _cap_by_type

    # Create 3 samples with different quality scores, same sft_type
    samples = []
    for i, score in enumerate([0.3, 0.9, 0.6]):
        sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
        sft_data["id"] = f"sft-20260410-qs{i:04d}"
        sft_data["quality"]["local_score"] = score
        samples.append(SFTSample.model_validate(sft_data))

    capped = _cap_by_type(samples, 2)
    assert len(capped) == 2
    scores = {s.quality.local_score for s in capped}
    # Should keep 0.9 and 0.6, drop 0.3
    assert scores == {0.9, 0.6}


# ── consecutive role validation tests ────────────────────────────────


def test_validate_rejects_consecutive_assistant():
    """_validate_sample rejects consecutive assistant messages."""
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    data["query"]["conversation_history"] = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "first response"},
        {"role": "assistant", "content": "second response"},
        {"role": "tool", "name": "Bash", "input": "ls", "output": "files"},
    ]
    sample = SFTSample.model_validate(data)
    with pytest.raises(ExportValidationError, match="consecutive 'assistant'"):
        _validate_sample(sample)


def test_validate_allows_consecutive_tool():
    """_validate_sample allows consecutive tool messages (multiple tool calls)."""
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    data["query"]["conversation_history"] = [
        {"role": "user", "content": "fix the bug"},
        {"role": "assistant", "content": "let me check"},
        {"role": "tool", "name": "Read", "input": "src/app.py", "output": "code"},
        {"role": "tool", "name": "Grep", "input": "error", "output": "line 42"},
        {"role": "assistant", "content": "found it"},
    ]
    sample = SFTSample.model_validate(data)
    _validate_sample(sample)  # should not raise


def test_openai_sft_assistant_messages_always_have_content_key(tmp_path):
    """Every assistant message in OpenAI SFT format must have a 'content' key.

    When two consecutive tool messages appear in history, the second creates a
    new standalone assistant message (no preceding assistant text to merge into).
    That message must still carry content=None to satisfy the OpenAI API.
    """
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    data["review_status"] = "approved"
    # Two consecutive tool messages — the second triggers the else-branch
    # in _to_openai_sft that creates a fresh assistant+tool_calls message.
    data["query"]["conversation_history"] = [
        {"role": "user", "content": "fix the bug"},
        {"role": "tool", "name": "Bash", "input": "ls", "output": "files"},
        {"role": "tool", "name": "Read", "input": "src/app.py", "output": "code"},
    ]
    store = SelfTuneStore(tmp_path)
    store.init()
    store.save_sample(SFTSample.model_validate(data))
    output = tmp_path / "export.jsonl"
    export_sft(store, output)
    row = json.loads(output.read_text().strip())
    assistant_msgs = [m for m in row["messages"] if m["role"] == "assistant"]
    for msg in assistant_msgs:
        assert "content" in msg, (
            f"Assistant message missing 'content' key: {msg}"
        )


def test_export_allows_content_free_hedging_false():
    """no_content_free_hedging=False does NOT block export (informational only)."""
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    data["id"] = "sft-20260410-hedge"
    data["quality"]["no_content_free_hedging"] = False
    data["review_status"] = "approved"
    sample = SFTSample.model_validate(data)
    _validate_sample(sample)  # should not raise
