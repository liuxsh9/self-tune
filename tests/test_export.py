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
    """SFT export produces messages-format JSONL."""
    store = _seed_store(tmp_path)
    output = tmp_path / "export.jsonl"
    count = export_sft(store, output)
    assert count == 1
    line = json.loads(output.read_text().strip())
    assert "messages" in line
    messages = line["messages"]
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles
    assert "assistant" in roles


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
