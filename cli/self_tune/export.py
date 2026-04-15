# cli/self_tune/export.py
"""Multi-format export for Self-tune SFT data."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Optional

from .store import SelfTuneStore
from .models import SFTSample, ConversationMessage, SFTAction, SFTType

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
                    "offset": {"type": "integer", "description": "Line number to start reading from"},
                    "limit": {"type": "integer", "description": "Number of lines to read"},
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
                    "output_mode": {"type": "string", "enum": ["content", "files_with_matches", "count"], "description": "Output format"},
                    "glob": {"type": "string", "description": "Glob pattern to filter files (e.g. '*.py')"},
                    "type": {"type": "string", "description": "File type to search (e.g. 'py', 'js')"},
                    "-i": {"type": "boolean", "description": "Case insensitive search"},
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
                    "path": {"type": "string", "description": "Directory to search in"},
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
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences"},
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
    {
        "type": "function",
        "function": {
            "name": "Write",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Agent",
            "description": "Launch a specialized subagent for complex tasks",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Task description for the subagent"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "LSP",
            "description": "Query the Language Server Protocol for code intelligence",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "filePath": {"type": "string"},
                    "line": {"type": "integer"},
                    "character": {"type": "integer"},
                },
                "required": ["operation", "filePath", "line", "character"],
            },
        },
    },
]

VALID_TOOL_NAMES = {t["function"]["name"] for t in AGENTIC_TOOLS}

# Map tool names to their primary input parameter name.
# Used when ConversationMessage.input is a flat string that needs to be
# wrapped into the correct argument key for the tool_calls schema.
TOOL_INPUT_KEY = {
    "Bash": "command",
    "Read": "file_path",
    "Edit": "file_path",
    "Write": "file_path",
    "Grep": "pattern",
    "Glob": "pattern",
    "WebSearch": "query",
    "WebFetch": "url",
    "Agent": "prompt",
    "LSP": "operation",
}


def _tool_arguments(tool_name: str, input_val: str | dict | None) -> str:
    """Build JSON arguments string for a tool call.

    If input_val is already a dict (structured arguments), serialize it directly.
    If it's a flat string, wrap it in the tool's primary parameter key.
    """
    if input_val is None:
        return "{}"
    if isinstance(input_val, dict):
        return json.dumps(input_val, ensure_ascii=False)
    key = TOOL_INPUT_KEY.get(tool_name or "Bash", "command")
    return json.dumps({key: input_val}, ensure_ascii=False)


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

    # 4. Evidence grounding: reject samples explicitly flagged as not evidence-anchored
    if sample.quality.evidence_anchored is False:
        raise ExportValidationError(
            f"Sample {sample.id}: quality.evidence_anchored=False — "
            f"CoT may reference information not present in conversation_history"
        )

    # 5. Post-hoc rationalization: reject samples flagged as containing rationalization
    if sample.quality.no_post_hoc_rationalization is False:
        raise ExportValidationError(
            f"Sample {sample.id}: quality.no_post_hoc_rationalization=False — "
            f"CoT contains post-hoc rationalization"
        )


def _warn_sample(sample: SFTSample) -> list[str]:
    """Return non-blocking warnings for an SFT sample."""
    warnings = []
    hist_len = len(sample.query.conversation_history)
    _min_recommended: dict[SFTType, int] = {
        SFTType.diagnostic_recovery: 4,
        SFTType.backtrack_decision: 6,
        SFTType.tool_orchestration: 6,
        SFTType.error_correction: 6,
    }
    threshold = _min_recommended.get(sample.sft_type, 8)
    if hist_len < threshold:
        warnings.append(
            f"Sample {sample.id}: conversation_history has {hist_len} messages "
            f"(recommended minimum for {sample.sft_type.value}: {threshold})"
        )
    return warnings


def export_sft(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False, max_per_type: Optional[int] = None) -> int:
    """Export SFT samples in OpenAI chat fine-tuning format (JSONL).

    Format follows OpenAI's supervised fine-tuning spec:
    - messages array with system/user/assistant/tool roles
    - tool_calls on assistant messages (not inlined as user text)
    - tool responses as role:"tool" with tool_call_id
    - weight:0 on context messages (only train on final assistant turn)
    - tools array defining available functions
    """
    samples = _filter(store.list_samples(), min_score, include_pending, max_per_type)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            example = _to_openai_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return len(samples)



def export_jsonl(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False, max_per_type: Optional[int] = None) -> int:
    """Export raw SFT sample objects as JSONL."""
    samples = _filter(store.list_samples(), min_score, include_pending, max_per_type)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            f.write(sample.model_dump_json() + "\n")
    return len(samples)


def _filter(samples: list[SFTSample], min_score: Optional[float], include_pending: bool = False, max_per_type: Optional[int] = None) -> list[SFTSample]:
    result = samples
    if include_pending:
        result = [s for s in result if s.review_status in ("approved", "pending")]
    else:
        result = [s for s in result if s.review_status == "approved"]
    if min_score is not None:
        result = [s for s in result if (s.quality.local_score or 0) >= min_score]
    if max_per_type is not None:
        result = _cap_by_type(result, max_per_type)
    return result


def _cap_by_type(samples: list[SFTSample], max_count: int) -> list[SFTSample]:
    """Cap each sft_type to at most max_count samples.

    Sorts each group by quality score (descending) before truncating,
    so higher-quality samples survive the cap.
    """
    if max_count <= 0:
        return []
    from collections import defaultdict
    by_type: dict[SFTType, list[SFTSample]] = defaultdict(list)
    for s in samples:
        by_type[s.sft_type].append(s)
    capped = []
    for group in by_type.values():
        group.sort(key=lambda s: s.quality.local_score or 0, reverse=True)
        capped.extend(group[:max_count])
    capped.sort(key=lambda s: s.id)
    return capped


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

            arguments = _tool_arguments(msg.name, msg.input)
            tool_call = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": msg.name or "Bash",
                    "arguments": arguments,
                },
            }

            # Merge into preceding assistant message to avoid consecutive assistant roles
            if messages and messages[-1]["role"] == "assistant" and "tool_calls" not in messages[-1]:
                messages[-1]["tool_calls"] = [tool_call]
            else:
                messages.append({
                    "role": "assistant",
                    "tool_calls": [tool_call],
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
        arguments = _tool_arguments(sample.action.tool, sample.action.input)
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
                    "input": json.loads(_tool_arguments(m.name, m.input)),
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
                "input": json.loads(_tool_arguments(sample.action.tool, sample.action.input)),
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
            function_call = {
                "name": msg.name or "Bash",
                "arguments": _tool_arguments(msg.name, msg.input),
            }

            # Merge into preceding assistant message to avoid consecutive assistant roles
            if messages and messages[-1]["role"] == "assistant" and "function_call" not in messages[-1]:
                messages[-1]["function_call"] = function_call
                messages[-1]["content"] = messages[-1].get("content") or None
            else:
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "function_call": function_call,
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
                "arguments": _tool_arguments(sample.action.tool, sample.action.input),
            },
        })
    else:
        messages.append({
            "role": "assistant",
            "content": f"<think>\n{sample.cot}\n</think>\n\n{sample.response}",
        })

    return {"messages": messages}


def export_anthropic(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False, max_per_type: Optional[int] = None) -> int:
    """Export SFT samples in Anthropic Messages API format (JSONL)."""
    samples = _filter(store.list_samples(), min_score, include_pending, max_per_type)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            example = _to_anthropic_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return len(samples)


def export_chatml(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False, max_per_type: Optional[int] = None) -> int:
    """Export SFT samples in ChatML format for open-source models (JSONL)."""
    samples = _filter(store.list_samples(), min_score, include_pending, max_per_type)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            example = _to_chatml_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return len(samples)


def _to_ml2_sft(sample: SFTSample) -> dict:
    """Convert SFT sample to extended OpenAI format with reasoning_content and meta_info.

    Key differences from standard OpenAI SFT:
    - Every assistant message has a reasoning_content field (String)
    - CoT goes into reasoning_content, not <think> tags in content
    - Context assistant messages have reasoning_content: "" (fast thinking)
    - weight only on final assistant turn (1), not on context messages
    - Top-level version and meta_info fields
    """
    messages = []
    call_counter = 0

    # System message
    messages.append({
        "role": "system",
        "content": sample.query.system_context,
    })

    # Conversation history
    for msg in sample.query.conversation_history:
        if msg.role == "tool":
            call_counter += 1
            call_id = f"call_{call_counter}"

            arguments = _tool_arguments(msg.name, msg.input)
            tool_call = {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": msg.name or "Bash",
                    "arguments": arguments,
                },
            }

            # Merge into preceding assistant message to avoid consecutive assistant roles
            if messages and messages[-1]["role"] == "assistant" and "tool_calls" not in messages[-1]:
                messages[-1]["tool_calls"] = [tool_call]
            else:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "",
                    "tool_calls": [tool_call],
                })

            # Tool response
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": msg.output or "",
            })
        elif msg.role == "user":
            messages.append({
                "role": "user",
                "content": msg.content or "",
            })
        elif msg.role == "assistant":
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "reasoning_content": "",
            })

    # Final assistant turn: the training target (weight:1)
    if sample.action:
        call_counter += 1
        call_id = f"call_{call_counter}"
        arguments = _tool_arguments(sample.action.tool, sample.action.input)
        final_msg: dict = {
            "role": "assistant",
            "content": "",
            "reasoning_content": sample.cot,
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
            "content": sample.response,
            "reasoning_content": sample.cot,
            "weight": 1,
        }
    messages.append(final_msg)

    # Count conversation rounds (user messages in history)
    rounds = sum(1 for m in sample.query.conversation_history if m.role == "user")

    example: dict = {
        "version": "2.0.0",
        "meta_info": {
            "teacher": "claude-sonnet-4-6",
            "query_source": "self-tune",
            "response_generate_time": sample.created_at.strftime("%Y-%m-%d"),
            "response_update_time": sample.created_at.strftime("%Y-%m-%d"),
            "owner": "",
            "language": "auto",
            "category": "agent",
            "rounds": rounds,
            "unique_info": {
                "quality_tier": sample.quality_tier,
                "sft_type": sample.sft_type.value,
                "insight_id": sample.insight_id,
            },
        },
        "messages": messages,
    }

    if call_counter > 0:
        example["tools"] = AGENTIC_TOOLS

    return example


def export_ml2(store: SelfTuneStore, output: Path, min_score: Optional[float] = None, include_pending: bool = False, max_per_type: Optional[int] = None) -> int:
    """Export SFT samples in extended OpenAI format with reasoning_content (JSONL)."""
    samples = _filter(store.list_samples(), min_score, include_pending, max_per_type)
    with output.open("w") as f:
        for sample in samples:
            _validate_sample(sample)
            example = _to_ml2_sft(sample)
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    return len(samples)
