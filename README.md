# Self-tune

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](cli/pyproject.toml)

A Claude Code skill + CLI that automatically extracts SFT training data from coding interactions where the model failed or was corrected.

## How It Works

Self-tune runs silently alongside your normal Claude Code workflow. After each interaction, a sentinel checks whether the session contained a **learning moment** -- a retry, a user correction, a strategy change, a discovered mistake, or a task that succeeded but took far more rounds than necessary. If the lesson is generalizable (not just a one-off fact), it dispatches a background subagent to analyze the episode.

The subagent produces two artifacts:

- **Insight** -- a structured diagnosis of what went wrong and why, with adversarial reflection and a generalization ladder (project-specific through universal)
- **SFT Sample** -- a training-ready (query, chain-of-thought, response) tuple anchored to evidence from the conversation

Your main workflow is never blocked or interrupted. The subagent runs on Sonnet in the background to avoid consuming Opus tokens.

### Data Flow

```
 Claude Code session
        |
        v
 [Sentinel in CLAUDE.md]
   "Was there friction AND is the lesson generalizable?"
        |
       YES
        |
        v
 [Skill dispatch]  ──>  background subagent (Sonnet)
                              |
                         reads prompt template
                         + output schema
                              |
                              v
                       analyzes episode
                              |
                    ┌─────────┴─────────┐
                    v                   v
               Insight             SFT Sample
                    |                   |
                    └─────────┬─────────┘
                              v
                    ~/.self-tune/data/
                              |
                              v
                     CLI reads / exports
```

### Trigger Criteria

Self-tune activates when ANY of these occurred:

- You retried an approach after it failed or hit a dead end
- The user corrected your direction or thinking
- You changed strategy mid-task
- The user provided a key hint that unblocked progress
- You discovered a previous solution was wrong

It stays silent when the task went smoothly with zero friction.

## Architecture

Two independent halves that share a data contract (defined in `models.py`):

```
self-tune/
├── skills/reflect/            # Skill side (prompt templates)
│   ├── SKILL.md               # Manifest + trigger criteria + dispatch protocol
│   ├── sidecar-prompt.md      # Mid-task extraction (most common path)
│   ├── retrospective-prompt.md  # Full-session review after completion
│   ├── correction-prompt.md   # Fix historical insights found to be wrong
│   └── output-schema.md       # JSON structure reference (from models.py)
│
├── cli/self_tune/             # CLI side (Python package)
│   ├── models.py              # Single source of truth for all schemas
│   ├── store.py               # File-based persistence (~/.self-tune/data/)
│   ├── export.py              # Multi-format SFT export (OpenAI, Anthropic, ChatML, ML2)
│   └── cli.py                 # Click entry point
│
└── tests/                     # Pytest suite
```

```
┌─────────────────────────────────────────────────────────────────┐
│                     Claude Code Session                         │
│                                                                 │
│  Sentinel ──> Skill (SKILL.md) ──> Background Subagent          │
│                                        │                        │
│               reads prompt template +  │                        │
│               output-schema.md         │                        │
└────────────────────────────────────────┼────────────────────────┘
                                         │  writes JSON
                                         v
┌─────────────────────────────────────────────────────────────────┐
│                    ~/.self-tune/data/                            │
│                                                                 │
│  traces/    insights/    samples/    corrections/                │
└───────────────────────────────┬─────────────────────────────────┘
                                │  reads
                                v
┌─────────────────────────────────────────────────────────────────┐
│                      CLI (self-tune)                             │
│                                                                 │
│  stats · list · show · validate · export · review                │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
git clone https://github.com/liuxsh9/self-tune.git
cd self-tune
./install.sh
```

The installer does three things:

1. **Data directory** -- creates `~/.self-tune/data/` with subdirectories for traces, insights, samples, and corrections
2. **Skill** -- symlinks `skills/reflect/` into `~/.claude/skills/reflect/` so Claude Code discovers it automatically
3. **CLI** -- installs the `self-tune` command via pip (requires Python 3.10+; consider using a virtualenv)

After installation, the reflect skill activates automatically in future Claude Code sessions. No configuration required.

## CLI Usage

```bash
# Overview of collected data
self-tune stats

# Browse items by type (traces, insights, samples, corrections)
self-tune list --type samples

# Inspect a specific item by ID
self-tune show sft-20260410-a1b2c3

# Export SFT training data (OpenAI chat format)
self-tune export --format sft -o training.jsonl

# Export everything as raw JSONL
self-tune export --format raw -o dump.jsonl
```

## Data Location

All data lives under `~/.self-tune/` (created by `./install.sh`):

```
~/.self-tune/
├── config.yaml          # Optional config (server, trigger thresholds, retention)
├── index.json           # Stats and metadata
└── data/
    ├── traces/          # Session-level records of what happened
    ├── insights/        # Structured diagnoses (root cause, generalization)
    ├── samples/         # Training-ready SFT samples
    └── corrections/     # Amendments to historical insights
```

Each file is standalone JSON, named by its ID. No database required.

## Key Concepts

**Trace** -- A session-level record capturing what task was attempted, whether it succeeded, and a compressed snapshot of the conversation. One trace can produce multiple insights. ID prefix: `trace`.

**Insight** -- A structured diagnosis of a single failure or inefficiency. Contains a root cause (concrete + abstract), adversarial reflection (two competing attributions with a verdict), a generalization ladder (L1 project-specific through L3 universal), and efficiency metrics. ID prefix: `ins`.

**SFT Sample** -- A training-ready tuple of (query, chain-of-thought, response/action). The query reconstructs the decision point from conversation history. The CoT must be evidence-anchored -- every claim derivable from the query context, no post-hoc rationalization. Comes in `concrete` (project-specific) and `abstract` (generalized) versions. ID prefix: `sft`.

**Correction** -- An amendment to a historical insight that was found to be wrong. Can supersede, amend, or retract the original. Optionally generates a new insight from the lesson learned. ID prefix: `cor`.

## Development

```bash
# Set up dev environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e cli/

# Run the test suite
.venv/bin/pytest tests/ -v

# Run a single test file
.venv/bin/pytest tests/test_export.py

# Run a specific test
.venv/bin/pytest tests/ -k "test_name"
```

## Contributing

Contributions are welcome. Please open an issue to discuss changes before submitting a pull request.

When modifying data schemas, remember: `models.py` is the single source of truth. Update `output-schema.md` and the inline JSON templates in prompt files to match.

## License

[MIT](LICENSE)
