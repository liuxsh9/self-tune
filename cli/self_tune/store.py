# cli/self_tune/store.py
"""Local file store for Self-tune data."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .models import Trace, Insight, SFTSample, Correction


class SelfTuneStore:
    """Read/write Self-tune data to ~/.self-tune/."""

    SUBDIRS = ("traces", "insights", "samples", "corrections")

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.data_dir = self.root / "data"
        self.index_path = self.root / "index.json"

    def init(self) -> None:
        """Create directory structure and index."""
        for subdir in self.SUBDIRS:
            (self.data_dir / subdir).mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._write_index(self._empty_index())

    # --- Save ---

    def save_trace(self, trace: Trace) -> Path:
        return self._save("traces", trace.id, trace)

    def save_insight(self, insight: Insight) -> Path:
        return self._save("insights", insight.id, insight)

    def save_sample(self, sample: SFTSample) -> Path:
        return self._save("samples", sample.id, sample)

    def save_correction(self, correction: Correction) -> Path:
        return self._save("corrections", correction.id, correction)

    def update_sample(self, sample_id: str, **updates) -> SFTSample:
        """Update fields on an existing SFT sample."""
        sample = self.load_sample(sample_id)
        data = sample.model_dump()
        data.update(updates)
        updated = SFTSample.model_validate(data)
        self._save("samples", updated.id, updated)
        return updated

    # --- Load ---

    def load_trace(self, id_: str) -> Trace:
        return Trace.model_validate_json(self._read("traces", id_))

    def load_insight(self, id_: str) -> Insight:
        return Insight.model_validate_json(self._read("insights", id_))

    def load_sample(self, id_: str) -> SFTSample:
        return SFTSample.model_validate_json(self._read("samples", id_))

    def load_correction(self, id_: str) -> Correction:
        return Correction.model_validate_json(self._read("corrections", id_))

    # --- List ---

    def list_traces(self) -> list[Trace]:
        return self._list_dir("traces", Trace)

    def list_insights(self) -> list[Insight]:
        return self._list_dir("insights", Insight)

    def list_samples(self) -> list[SFTSample]:
        return self._list_dir("samples", SFTSample)

    def list_corrections(self) -> list[Correction]:
        return self._list_dir("corrections", Correction)

    # --- Stats ---

    def stats(self) -> dict:
        """Return current counts."""
        return {
            "total_traces": len(list((self.data_dir / "traces").glob("*.json"))),
            "total_insights": len(list((self.data_dir / "insights").glob("*.json"))),
            "total_samples": len(list((self.data_dir / "samples").glob("*.json"))),
            "total_corrections": len(list((self.data_dir / "corrections").glob("*.json"))),
        }

    # --- Internal ---

    def _save(self, subdir: str, id_: str, model: object) -> Path:
        path = self.data_dir / subdir / f"{id_}.json"
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with open(fd, "w") as f:
                f.write(model.model_dump_json(indent=2))
            import os
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self._update_index()
        return path

    def _list_dir(self, subdir: str, model_cls: type) -> list:
        results = []
        for p in sorted((self.data_dir / subdir).glob("*.json")):
            try:
                results.append(model_cls.model_validate_json(p.read_text()))
            except Exception as exc:
                print(f"Warning: skipping corrupt file {p}: {exc}", file=sys.stderr)
        return results

    def _read(self, subdir: str, id_: str) -> str:
        path = self.data_dir / subdir / f"{id_}.json"
        return path.read_text()

    def _update_index(self) -> None:
        index = {
            "last_updated": __import__("datetime").datetime.now().isoformat(),
            "stats": self.stats(),
        }
        self._write_index(index)

    def _write_index(self, index: dict) -> None:
        self.index_path.write_text(json.dumps(index, indent=2))

    @staticmethod
    def _empty_index() -> dict:
        return {
            "last_updated": __import__("datetime").datetime.now().isoformat(),
            "stats": {
                "total_traces": 0,
                "total_insights": 0,
                "total_samples": 0,
                "total_corrections": 0,
            },
        }
