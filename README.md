# Self-tune

Extract learning experiences from AI coding assistant interactions.
Produces SFT training data from real coding interactions.

## Quick Start

```bash
git clone <repo-url>
cd self-tune
./install.sh
```

This installs:
- **Skill** → `~/.claude/skills/self-tune/` (auto-activates in Claude Code)
- **CLI** → `self-tune` command (requires Python 3.10+)
- **Data** → `~/.self-tune/data/`

## How It Works

The self-tune skill auto-activates when Claude Code detects:
- Repeated trial-and-error (3+ retries)
- User corrections or strategy changes
- Discovery that a previous solution was wrong

A background subagent extracts the learning and saves:
- **SFT training data** (for post-training model improvement)
- **DPO pairs** (chosen/rejected for preference learning)

Your main workflow is never blocked or interrupted.

## CLI Usage

```bash
self-tune stats              # View data statistics
self-tune list --type samples  # Browse SFT samples
self-tune show sft-20260410-a1b2c3  # View specific item
self-tune export --format sft -o training.jsonl  # Export for training
self-tune export --format dpo -o preference.jsonl  # Export DPO pairs
```

## Data Location

All data is stored at `~/.self-tune/`:
```
~/.self-tune/
├── config.yaml
├── index.json
└── data/
    ├── traces/
    ├── insights/
    ├── samples/
    └── corrections/
```
