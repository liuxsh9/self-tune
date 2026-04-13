# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] - 2026-04-13

Initial release as **self-tune** (renamed from echo-smith).

### Added

- **Data models** (`models.py`) -- Pydantic v2 schemas for Trace, Insight, SFT Sample, and Correction
- **File store** (`store.py`) -- JSON-based persistence at `~/.self-tune/data/`
- **Export engine** (`export.py`) -- SFT (OpenAI chat format), DPO (chosen/rejected pairs), and raw JSONL export
- **CLI** (`cli.py`) -- `stats`, `list`, `show`, `export` commands via Click
- **Skill** (`SKILL.md`) -- auto-trigger manifest with dispatch protocol for background subagents
- **Prompt templates** -- sidecar, retrospective, and correction subagent prompts with inline schemas
- **Install script** -- one-command setup for data directory, skill symlink, and CLI
- **Test suite** -- 25+ pytest tests covering models, store, and export
- **CI** -- GitHub Actions workflow for Python 3.10/3.11/3.12
- **Documentation** -- design spec, implementation plan, brainstorming log
