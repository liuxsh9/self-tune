# Echo-smith

Extract learning experiences from AI coding assistant interactions.
Produces SFT training data and CLAUDE.md reminders.

## Quick Start

```bash
git clone <repo-url>
cd echo-smith
./install.sh
```

This installs:
- **Skill** → `~/.claude/skills/echo-smith/` (auto-activates in Claude Code)
- **CLI** → `echo-smith` command (requires Python 3.10+)
- **Data** → `~/.echo-smith/data/`

## How It Works

The echo-smith skill auto-activates when Claude Code detects:
- Repeated trial-and-error (3+ retries)
- User corrections or strategy changes
- Discovery that a previous solution was wrong

A background subagent extracts the learning and saves:
- **SFT training data** (long-term model improvement)
- **CLAUDE.md reminders** (immediate experience-based guidance)

Your main workflow is never blocked or interrupted.

## CLI Usage

```bash
echo-smith stats              # View data statistics
echo-smith list --type samples  # Browse SFT samples
echo-smith show sft-20260410-a1b2c3  # View specific item
echo-smith export --format sft -o training.jsonl  # Export for training
echo-smith export --format dpo -o preference.jsonl  # Export DPO pairs
```

## Data Location

All data is stored at `~/.echo-smith/`:
```
~/.echo-smith/
├── config.yaml
├── index.json
└── data/
    ├── traces/
    ├── insights/
    ├── samples/
    ├── reminders/
    └── corrections/
```
