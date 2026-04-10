# cli/echo_smith/store.py
"""Local file store for Echo-smith data."""

from __future__ import annotations

import json
from pathlib import Path

from .models import Trace, Insight, SFTSample, Reminder, Correction


class EchoSmithStore:
    """Read/write Echo-smith data to ~/.echo-smith/."""

    SUBDIRS = ("traces", "insights", "samples", "reminders", "corrections")

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

    def save_reminder(self, reminder: Reminder) -> Path:
        return self._save("reminders", reminder.id, reminder)

    def save_correction(self, correction: Correction) -> Path:
        return self._save("corrections", correction.id, correction)

    # --- Load ---

    def load_trace(self, id_: str) -> Trace:
        return Trace.model_validate_json(self._read("traces", id_))

    def load_insight(self, id_: str) -> Insight:
        return Insight.model_validate_json(self._read("insights", id_))

    def load_sample(self, id_: str) -> SFTSample:
        return SFTSample.model_validate_json(self._read("samples", id_))

    def load_reminder(self, id_: str) -> Reminder:
        return Reminder.model_validate_json(self._read("reminders", id_))

    def load_correction(self, id_: str) -> Correction:
        return Correction.model_validate_json(self._read("corrections", id_))

    # --- List ---

    def list_traces(self) -> list[Trace]:
        return [Trace.model_validate_json(p.read_text()) for p in sorted((self.data_dir / "traces").glob("*.json"))]

    def list_insights(self) -> list[Insight]:
        return [Insight.model_validate_json(p.read_text()) for p in sorted((self.data_dir / "insights").glob("*.json"))]

    def list_samples(self) -> list[SFTSample]:
        return [SFTSample.model_validate_json(p.read_text()) for p in sorted((self.data_dir / "samples").glob("*.json"))]

    def list_reminders(self) -> list[Reminder]:
        return [Reminder.model_validate_json(p.read_text()) for p in sorted((self.data_dir / "reminders").glob("*.json"))]

    def list_corrections(self) -> list[Correction]:
        return [Correction.model_validate_json(p.read_text()) for p in sorted((self.data_dir / "corrections").glob("*.json"))]

    # --- Stats ---

    def stats(self) -> dict:
        """Return current counts."""
        return {
            "total_traces": len(list((self.data_dir / "traces").glob("*.json"))),
            "total_insights": len(list((self.data_dir / "insights").glob("*.json"))),
            "total_samples": len(list((self.data_dir / "samples").glob("*.json"))),
            "total_reminders": len(list((self.data_dir / "reminders").glob("*.json"))),
            "total_corrections": len(list((self.data_dir / "corrections").glob("*.json"))),
        }

    # --- Internal ---

    def _save(self, subdir: str, id_: str, model: object) -> Path:
        path = self.data_dir / subdir / f"{id_}.json"
        path.write_text(model.model_dump_json(indent=2))
        self._update_index()
        return path

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
                "total_reminders": 0,
                "total_corrections": 0,
            },
        }
