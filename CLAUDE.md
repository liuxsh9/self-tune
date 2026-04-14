# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Self-tune is a Claude Code skill + CLI that extracts SFT training data from coding interactions where the model failed or was corrected. A background subagent analyzes the episode, produces structured insights, and writes training-ready samples to `~/.self-tune/data/`.

## Commands

```bash
# Tests (use the project venv)
.venv/bin/pytest tests/ -v              # full suite (25 tests)
.venv/bin/pytest tests/test_export.py   # single file
.venv/bin/pytest tests/ -k "test_name"  # single test

# Install package in dev mode
.venv/bin/python -m pip install -e cli/

# CLI
self-tune stats
self-tune list --type samples
self-tune show sft-20260410-a1b2c3
self-tune export --format sft -o training.jsonl
```

## Architecture

Two independent halves that share a data contract:

**Skill side** (`skills/reflect/`) — prompt templates consumed by Claude Code subagents:
- `SKILL.md` — manifest, trigger criteria, dispatch protocol
- `sidecar-prompt.md` — mid-task extraction (most common)
- `retrospective-prompt.md` — full-session review after completion
- `correction-prompt.md` — fix historical insights found to be wrong
- `output-schema.md` — JSON structure reference (generated from models.py)

**CLI side** (`cli/self_tune/`) — Python package for storage and export:
- `models.py` — **single source of truth** for all data schemas (Pydantic v2)
- `store.py` — file-based persistence at `~/.self-tune/data/`
- `export.py` — converts samples to OpenAI SFT, DPO, or raw JSONL format
- `cli.py` — Click entry point

**Data flow**: Skill detects trigger → dispatches background subagent with prompt template + schema → subagent writes JSON to `~/.self-tune/data/` → CLI reads/exports.

## Key Design Decisions

**models.py is the source of truth.** When prompts and models disagree, models.py wins. If you change a model, update output-schema.md and the inline JSON templates in the prompt files.

**SFT training target = CoT + first correct action.** The `response` field is a brief intent statement. The `action` field (optional `SFTAction`) holds the tool call. Response must NEVER contain fabricated tool outputs — that trains hallucination.

**The Iron Law:** Every claim in SFT CoT must be derivable from evidence in the query's conversation_history. No post-hoc rationalization, no information leakage.

**Export validation** (`ExportValidationError`): action.tool must be in AGENTIC_TOOLS (Bash, Read, Grep, Glob, Edit, WebSearch, WebFetch), empty response + null action is rejected, consecutive same-role messages (user-user, assistant-assistant) are rejected.

**version field** on SFTSample is `Literal["concrete", "abstract"]`, not a free string.

**Subagents run in background** with `model: "sonnet"` to avoid blocking the user or consuming opus tokens.

## ID Format

`{prefix}-{YYYYMMDD}-{6hex}` — prefixes: `trace`, `ins`, `sft`, `cor`. The prefix determines which store loader to use.

## Auto-Trigger Sentinel

The sentinel in `~/.claude/CLAUDE.md` checks after each user request whether the interaction had friction AND the lesson is generalizable. Both conditions must be true to call `Skill("reflect")`. "Friction" includes inefficiency — a task that succeeded but took significantly more rounds than necessary still qualifies. This mirrors how auto memory works but produces SFT samples instead of memory entries — they are complementary, not substitutes.
