# tests/test_cli.py
"""Tests for CLI commands (validate, stats, etc.)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from self_tune.cli import main
from self_tune.models import SFTSample, Insight
from self_tune.store import SelfTuneStore

FIXTURES = Path(__file__).parent / "fixtures"


def _init_store(tmp_path) -> SelfTuneStore:
    store = SelfTuneStore(tmp_path)
    store.init()
    return store


def _seed_valid_data(store: SelfTuneStore):
    store.save_insight(Insight.model_validate_json((FIXTURES / "sample_insight.json").read_text()))
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))


def test_validate_happy_path(tmp_path):
    """validate reports all files valid when data is clean."""
    store = _init_store(tmp_path)
    _seed_valid_data(store)

    runner = CliRunner()
    with patch("self_tune.cli.DEFAULT_ROOT", tmp_path):
        result = runner.invoke(main, ["validate"])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_validate_detects_malformed_json(tmp_path):
    """validate catches files with invalid JSON."""
    store = _init_store(tmp_path)
    # Write a malformed JSON file to samples dir
    bad_path = store.data_dir / "samples" / "sft-20260410-badjsn.json"
    bad_path.write_text("{this is not valid json")

    runner = CliRunner()
    with patch("self_tune.cli.DEFAULT_ROOT", tmp_path):
        result = runner.invoke(main, ["validate"])
    assert result.exit_code == 1
    assert "invalid" in result.output.lower() or "1" in result.output


def test_validate_detects_semantic_issues(tmp_path):
    """validate reports semantic errors for samples with evidence_anchored=False."""
    store = _init_store(tmp_path)
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["quality"]["evidence_anchored"] = False
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    runner = CliRunner()
    with patch("self_tune.cli.DEFAULT_ROOT", tmp_path):
        result = runner.invoke(main, ["validate"])
    # ExportValidationError is now treated as an error (exit 1)
    assert result.exit_code == 1
    assert "invalid" in result.output.lower() or "evidence_anchored" in result.output


def test_validate_warns_short_history(tmp_path):
    """validate warns about short conversation_history via _warn_sample."""
    store = _init_store(tmp_path)
    # Fixture has 5 messages (< 8 minimum) → should produce a warning
    sft_data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sft_data["review_status"] = "approved"
    store.save_sample(SFTSample.model_validate(sft_data))

    runner = CliRunner()
    with patch("self_tune.cli.DEFAULT_ROOT", tmp_path):
        result = runner.invoke(main, ["validate"])
    assert result.exit_code == 0
    assert "warning" in result.output.lower() or "conversation_history" in result.output
