# cli/echo_smith/export.py
"""Multi-format export for Echo-smith SFT data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .store import EchoSmithStore
from .models import SFTSample


def export_sft(store: EchoSmithStore, output: Path, min_score: Optional[float] = None) -> int:
    """Export SFT samples in messages format (OpenAI-compatible JSONL)."""
    samples = _filter(store.list_samples(), min_score)
    with output.open("w") as f:
        for sample in samples:
            messages = _to_messages(sample)
            f.write(json.dumps(messages, ensure_ascii=False) + "\n")
    return len(samples)


def export_dpo(store: EchoSmithStore, output: Path, min_score: Optional[float] = None) -> int:
    """Export DPO pairs in prompt/chosen/rejected format."""
    samples = _filter(store.list_samples(), min_score)
    with output.open("w") as f:
        for sample in samples:
            pair = _to_dpo_pair(sample)
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    return len(samples)


def export_jsonl(store: EchoSmithStore, output: Path, min_score: Optional[float] = None) -> int:
    """Export raw SFT sample objects as JSONL."""
    samples = _filter(store.list_samples(), min_score)
    with output.open("w") as f:
        for sample in samples:
            f.write(sample.model_dump_json() + "\n")
    return len(samples)


def _filter(samples: list[SFTSample], min_score: Optional[float]) -> list[SFTSample]:
    if min_score is None:
        return samples
    return [s for s in samples if (s.quality.local_score or 0) >= min_score]


def _to_messages(sample: SFTSample) -> dict:
    """Convert SFT sample to messages format."""
    messages = [{"role": "system", "content": sample.query.system_context}]
    for msg in sample.query.conversation_history:
        if msg.role == "tool":
            messages.append({
                "role": "user",
                "content": f"[Tool: {msg.name}]\nInput: {msg.input}\nOutput: {msg.output}",
            })
        elif msg.role == "user":
            messages.append({"role": "user", "content": msg.content or ""})
        elif msg.role == "assistant":
            messages.append({"role": "assistant", "content": msg.content or ""})
    # Final assistant turn: CoT + response
    messages.append({
        "role": "assistant",
        "content": f"<think>\n{sample.cot}\n</think>\n\n{sample.response}",
    })
    return {"messages": messages}


def _to_dpo_pair(sample: SFTSample) -> dict:
    """Convert SFT sample to DPO pair format."""
    prompt_parts = [f"System: {sample.query.system_context}"]
    for msg in sample.query.conversation_history:
        if msg.role == "tool":
            prompt_parts.append(f"[Tool: {msg.name}] {msg.output}")
        elif msg.content:
            prompt_parts.append(f"{msg.role}: {msg.content}")
    prompt = "\n".join(prompt_parts)

    chosen = f"<think>\n{sample.cot}\n</think>\n\n{sample.response}"

    rejected = "[original trajectory not stored — link to Trace for full rejected path]"

    return {"prompt": prompt, "chosen": chosen, "rejected": rejected}
