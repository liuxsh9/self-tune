# cli/echo_smith/export.py
"""Multi-format export for Echo-smith SFT data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .store import EchoSmithStore
from .models import SFTSample, ConversationMessage

# Tool definitions for agentic coding assistant context.
# These match Claude Code's actual tool set and are included in each
# training example so the model learns tool-call patterns.
AGENTIC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": "Execute a shell command and return its output",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Read a file from the filesystem",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "The absolute path to the file"},
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": "Search file contents with regex",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "The regex pattern to search for"},
                    "path": {"type": "string", "description": "File or directory to search in"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": "Find files by name pattern",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "The glob pattern to match"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Edit",
            "description": "Perform exact string replacements in files",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WebSearch",
            "description": "Search the web and return results",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WebFetch",
            "description": "Fetch content from a URL",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to fetch"},
                    "prompt": {"type": "string", "description": "What to extract from the page"},
                },
                "required": ["url", "prompt"],
            },
        },
    },
]


def export_sft(store: EchoSmithStore, output: Path, min_score: Optional[float] = None) -> int:
    """Export SFT samples in OpenAI chat fine-tuning format (JSONL).

    Format follows OpenAI's supervised fine-tuning spec:
    - messages array with system/user/assistant/tool roles
    - tool_calls on assistant messages (not inlined as user text)
    - tool responses as role:"tool" with tool_call_id
    - weight:0 on context messages (only train on final assistant turn)
    - tools array defining available functions
    """
    samples = _filter(store.list_samples(), min_score)
    with output.open("w") as f:
        for sample in samples:
            example = _to_openai_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
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


def _to_openai_sft(sample: SFTSample) -> dict:
    """Convert SFT sample to OpenAI chat fine-tuning format.

    Key format rules:
    - system message sets context
    - assistant tool usage → tool_calls field (not content)
    - tool results → role:"tool" with tool_call_id
    - context messages get weight:0 (not trained on)
    - final assistant message gets weight:1 (trained on)
    - tools array defines available functions
    """
    messages = []
    call_counter = 0

    # System message (weight:0 — context only)
    messages.append({
        "role": "system",
        "content": sample.query.system_context,
        "weight": 0,
    })

    # Conversation history (all weight:0 — context only)
    for msg in sample.query.conversation_history:
        if msg.role == "tool":
            # Tool interaction = assistant calls tool + tool responds
            call_counter += 1
            call_id = f"call_{call_counter}"

            # Assistant message with tool_calls
            arguments = json.dumps({"command": msg.input} if msg.input else {}, ensure_ascii=False)
            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": msg.name or "Bash",
                        "arguments": arguments,
                    },
                }],
                "weight": 0,
            })

            # Tool response
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": msg.output or "",
                "weight": 0,
            })
        elif msg.role == "user":
            messages.append({
                "role": "user",
                "content": msg.content or "",
                "weight": 0,
            })
        elif msg.role == "assistant":
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "weight": 0,
            })

    # Final assistant turn: the training target (weight:1)
    messages.append({
        "role": "assistant",
        "content": f"<think>\n{sample.cot}\n</think>\n\n{sample.response}",
        "weight": 1,
    })

    example: dict = {"messages": messages}

    # Include tools array if any tool interactions exist
    if call_counter > 0:
        example["tools"] = AGENTIC_TOOLS
        example["parallel_tool_calls"] = False

    return example


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

    # Use inline DPO rejected if available, otherwise placeholder
    if sample.dpo_rejected:
        rejected = sample.dpo_rejected.response
    else:
        rejected = "[original trajectory not stored — link to Trace for full rejected path]"

    return {"prompt": prompt, "chosen": chosen, "rejected": rejected}
