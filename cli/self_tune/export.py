# cli/self_tune/export.py
"""Multi-format export for Self-tune SFT data."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Optional

from .store import SelfTuneStore
from .models import SFTSample, ConversationMessage, SFTAction

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

VALID_TOOL_NAMES = {t["function"]["name"] for t in AGENTIC_TOOLS}


class ExportValidationError(ValueError):
    """Raised when an SFT sample fails export validation."""


def _validate_sample(sample: SFTSample) -> None:
    """Validate SFT sample before export. Raises ExportValidationError on failure."""
    # 1. action.tool must be a known agentic tool
    if sample.action and sample.action.tool not in VALID_TOOL_NAMES:
        raise ExportValidationError(
            f"Sample {sample.id}: action.tool '{sample.action.tool}' not in "
            f"valid tools {sorted(VALID_TOOL_NAMES)}"
        )

    # 2. Must have a training target — either response text or action
    if not sample.response.strip() and sample.action is None:
        raise ExportValidationError(
            f"Sample {sample.id}: empty response with no action — "
            f"no training target"
        )

    # 3. Conversation history role transitions must be valid
    #    No consecutive user-user or assistant-assistant (tool can repeat)
    history = sample.query.conversation_history
    for i in range(1, len(history)):
        prev_role = history[i - 1].role
        curr_role = history[i].role
        if prev_role == curr_role and curr_role in ("user", "assistant"):
            raise ExportValidationError(
                f"Sample {sample.id}: consecutive '{curr_role}' messages "
                f"at positions {i - 1} and {i}"
            )


def export_sft(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False) -> int:
    """Export SFT samples in OpenAI chat fine-tuning format (JSONL).

    Format follows OpenAI's supervised fine-tuning spec:
    - messages array with system/user/assistant/tool roles
    - tool_calls on assistant messages (not inlined as user text)
    - tool responses as role:"tool" with tool_call_id
    - weight:0 on context messages (only train on final assistant turn)
    - tools array defining available functions
    """
    samples = _filter(store.list_samples(), min_score, include_pending)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            example = _to_openai_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return len(samples)


def export_dpo(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False) -> int:
    """Export DPO pairs in prompt/chosen/rejected format."""
    samples = _filter(store.list_samples(), min_score, include_pending)
    with output.open("w") as f:
        for sample in samples:
            pair = _to_dpo_pair(sample)
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    return len(samples)


def export_jsonl(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False) -> int:
    """Export raw SFT sample objects as JSONL."""
    samples = _filter(store.list_samples(), min_score, include_pending)
    with output.open("w") as f:
        for sample in samples:
            f.write(sample.model_dump_json() + "\n")
    return len(samples)


def _filter(samples: list[SFTSample], min_score: Optional[float], include_pending: bool = False) -> list[SFTSample]:
    result = samples
    if include_pending:
        result = [s for s in result if s.review_status in ("approved", "pending")]
    else:
        result = [s for s in result if s.review_status == "approved"]
    if min_score is not None:
        result = [s for s in result if (s.quality.local_score or 0) >= min_score]
    return result


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
    # When action is present, emit CoT as content + tool_calls as the action.
    # When action is absent, emit CoT + response as plain text (fallback).
    if sample.action:
        call_counter += 1
        call_id = f"call_{call_counter}"
        arguments = json.dumps({"command": sample.action.input}, ensure_ascii=False)
        final_msg: dict = {
            "role": "assistant",
            "content": f"<think>\n{sample.cot}\n</think>",
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {
                    "name": sample.action.tool,
                    "arguments": arguments,
                },
            }],
            "weight": 1,
        }
    else:
        final_msg = {
            "role": "assistant",
            "content": f"<think>\n{sample.cot}\n</think>\n\n{sample.response}",
            "weight": 1,
        }
    messages.append(final_msg)

    example: dict = {"messages": messages}

    # Include tools array if any tool interactions exist (context or action)
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


def _to_anthropic_sft(sample: SFTSample) -> dict:
    """Convert SFT sample to Anthropic Messages API fine-tuning format.

    Anthropic requires strict user/assistant alternation. Consecutive tool
    messages are merged into a single assistant (tool_use) + user (tool_result)
    turn pair to maintain alternation.
    """
    messages = []
    has_tools = False

    # Build messages maintaining strict user/assistant alternation.
    # When an assistant text message is followed by tool messages, merge
    # the text into the same assistant turn as the tool_use blocks.
    history = sample.query.conversation_history
    i = 0
    while i < len(history):
        msg = history[i]
        if msg.role == "tool":
            has_tools = True
            # Gather consecutive tool messages into one turn pair
            tool_uses: list[dict] = []
            tool_results: list[dict] = []
            while i < len(history) and history[i].role == "tool":
                m = history[i]
                tool_use_id = f"toolu_{secrets.token_hex(12)}"
                tool_uses.append({
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": m.name or "Bash",
                    "input": {"command": m.input} if m.input else {},
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": m.output or "",
                })
                i += 1

            # If previous message is assistant text, merge tool_use into it
            # to avoid consecutive assistant messages.
            if messages and messages[-1]["role"] == "assistant" and isinstance(messages[-1]["content"], str):
                prev = messages.pop()
                assistant_content: list[dict] = [{"type": "text", "text": prev["content"]}]
                assistant_content.extend(tool_uses)
                messages.append({"role": "assistant", "content": assistant_content})
            else:
                messages.append({"role": "assistant", "content": tool_uses})
            messages.append({"role": "user", "content": tool_results})
        elif msg.role == "user":
            messages.append({"role": "user", "content": msg.content or ""})
            i += 1
        elif msg.role == "assistant":
            messages.append({"role": "assistant", "content": msg.content or ""})
            i += 1
        else:
            i += 1

    # Final assistant turn: CoT in thinking block + action as tool_use
    if sample.action:
        has_tools = True
        tool_use_id = f"toolu_{secrets.token_hex(12)}"
        final_content = [
            {"type": "thinking", "thinking": sample.cot},
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": sample.action.tool,
                "input": {"command": sample.action.input},
            },
        ]
    else:
        final_content = [
            {"type": "thinking", "thinking": sample.cot},
            {"type": "text", "text": sample.response},
        ]
    messages.append({"role": "assistant", "content": final_content})

    result: dict = {
        "system": sample.query.system_context,
        "messages": messages,
    }

    # Include Anthropic-style tool definitions when tool interactions exist
    if has_tools:
        result["tools"] = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in AGENTIC_TOOLS
        ]

    return result


def _to_chatml_sft(sample: SFTSample) -> dict:
    """Convert SFT sample to generic ChatML format for open-source models."""
    messages = []

    messages.append({"role": "system", "content": sample.query.system_context})

    for msg in sample.query.conversation_history:
        if msg.role == "tool":
            # ChatML: tool calls as assistant function_call + function response
            messages.append({
                "role": "assistant",
                "content": None,
                "function_call": {
                    "name": msg.name or "Bash",
                    "arguments": json.dumps({"command": msg.input} if msg.input else {}),
                },
            })
            messages.append({
                "role": "function",
                "name": msg.name or "Bash",
                "content": msg.output or "",
            })
        elif msg.role == "user":
            messages.append({"role": "user", "content": msg.content or ""})
        elif msg.role == "assistant":
            messages.append({"role": "assistant", "content": msg.content or ""})

    # Final assistant turn
    if sample.action:
        messages.append({
            "role": "assistant",
            "content": f"<think>\n{sample.cot}\n</think>",
            "function_call": {
                "name": sample.action.tool,
                "arguments": json.dumps({"command": sample.action.input}),
            },
        })
    else:
        messages.append({
            "role": "assistant",
            "content": f"<think>\n{sample.cot}\n</think>\n\n{sample.response}",
        })

    return {"messages": messages}


def export_anthropic(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False) -> int:
    """Export SFT samples in Anthropic Messages API format (JSONL)."""
    samples = _filter(store.list_samples(), min_score, include_pending)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            example = _to_anthropic_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return len(samples)


def export_chatml(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False) -> int:
    """Export SFT samples in ChatML format for open-source models (JSONL)."""
    samples = _filter(store.list_samples(), min_score, include_pending)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            example = _to_chatml_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return len(samples)
