# tests/test_store.py
import json
from pathlib import Path

from echo_smith.models import Insight, SFTSample, Reminder, Trace, Correction
from echo_smith.store import EchoSmithStore

FIXTURES = Path(__file__).parent / "fixtures"


def test_init_creates_directory_structure(tmp_path):
    """Store.init() creates required subdirectories."""
    store = EchoSmithStore(tmp_path)
    store.init()
    assert (tmp_path / "data" / "traces").is_dir()
    assert (tmp_path / "data" / "insights").is_dir()
    assert (tmp_path / "data" / "samples").is_dir()
    assert (tmp_path / "data" / "reminders").is_dir()
    assert (tmp_path / "data" / "corrections").is_dir()
    assert (tmp_path / "index.json").exists()


def test_save_and_load_insight(tmp_path):
    """Can save an Insight and load it back."""
    store = EchoSmithStore(tmp_path)
    store.init()
    data = json.loads((FIXTURES / "sample_insight.json").read_text())
    insight = Insight.model_validate(data)
    store.save_insight(insight)

    loaded = store.load_insight(insight.id)
    assert loaded.id == insight.id
    assert loaded.insight_type == insight.insight_type


def test_save_and_load_sft_sample(tmp_path):
    """Can save an SFT sample and load it back."""
    store = EchoSmithStore(tmp_path)
    store.init()
    data = json.loads((FIXTURES / "sample_sft.json").read_text())
    sample = SFTSample.model_validate(data)
    store.save_sample(sample)

    loaded = store.load_sample(sample.id)
    assert loaded.id == sample.id
    assert loaded.sft_type == sample.sft_type


def test_list_by_type(tmp_path):
    """Can list all items of a given type."""
    store = EchoSmithStore(tmp_path)
    store.init()

    data = json.loads((FIXTURES / "sample_insight.json").read_text())
    insight = Insight.model_validate(data)
    store.save_insight(insight)

    items = store.list_insights()
    assert len(items) == 1
    assert items[0].id == insight.id


def test_index_updates_on_save(tmp_path):
    """index.json stats update when items are saved."""
    store = EchoSmithStore(tmp_path)
    store.init()

    data = json.loads((FIXTURES / "sample_insight.json").read_text())
    insight = Insight.model_validate(data)
    store.save_insight(insight)

    index = json.loads((tmp_path / "index.json").read_text())
    assert index["stats"]["total_insights"] == 1


def test_stats(tmp_path):
    """stats() returns correct counts."""
    store = EchoSmithStore(tmp_path)
    store.init()

    data_i = json.loads((FIXTURES / "sample_insight.json").read_text())
    store.save_insight(Insight.model_validate(data_i))

    data_s = json.loads((FIXTURES / "sample_sft.json").read_text())
    store.save_sample(SFTSample.model_validate(data_s))

    stats = store.stats()
    assert stats["total_insights"] == 1
    assert stats["total_samples"] == 1
