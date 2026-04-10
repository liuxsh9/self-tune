# tests/test_export.py
import json
from pathlib import Path

from echo_smith.models import SFTSample, Insight
from echo_smith.store import EchoSmithStore
from echo_smith.export import export_sft, export_dpo, export_jsonl

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_store(tmp_path) -> EchoSmithStore:
    store = EchoSmithStore(tmp_path)
    store.init()
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))
    store.save_sample(SFTSample.model_validate_json((FIXTURES / "sample_sft.json").read_text()))
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
