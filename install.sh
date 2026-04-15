#!/usr/bin/env bash
# install.sh — One-command Self-tune installer
set -euo pipefail

SELF_TUNE_HOME="$HOME/.self-tune"
SKILL_DIR="$HOME/.claude/skills/reflect"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Self-tune Installer ==="

# 1. Create data directory structure
echo "Creating data directories..."
mkdir -p "$SELF_TUNE_HOME/data/traces"
mkdir -p "$SELF_TUNE_HOME/data/insights"
mkdir -p "$SELF_TUNE_HOME/data/samples"
mkdir -p "$SELF_TUNE_HOME/data/corrections"

# 2. Create default config if not exists
if [ ! -f "$SELF_TUNE_HOME/config.yaml" ]; then
    echo "Creating default config..."
    cp "$SCRIPT_DIR/config.yaml.template" "$SELF_TUNE_HOME/config.yaml"
else
    echo "Config already exists, skipping."
fi

# 3. Create index.json if not exists
if [ ! -f "$SELF_TUNE_HOME/index.json" ]; then
    echo '{"last_updated": null, "stats": {"total_traces": 0, "total_insights": 0, "total_samples": 0, "total_corrections": 0}}' > "$SELF_TUNE_HOME/index.json"
fi

# 4. Symlink skill to Claude Code skills directory
echo "Installing skill..."
mkdir -p "$HOME/.claude/skills"
if [ -L "$SKILL_DIR" ]; then
    rm "$SKILL_DIR"
fi
if [ -d "$SKILL_DIR" ]; then
    echo "WARNING: $SKILL_DIR is a real directory, not a symlink. Skipping."
else
    ln -s "$SCRIPT_DIR/skills/reflect" "$SKILL_DIR"
    echo "Skill symlinked: $SKILL_DIR -> $SCRIPT_DIR/skills/reflect"
fi

# 5. Install CLI (optional — prefers uv, falls back to pip)
if command -v uv &>/dev/null; then
    echo "Installing CLI tool via uv..."
    uv tool install --from "$SCRIPT_DIR" self-tune
    echo "CLI installed: run 'self-tune --help'"
elif command -v pip &>/dev/null; then
    echo "uv not found, falling back to pip..."
    pip install "$SCRIPT_DIR" --quiet
    echo "CLI installed: run 'self-tune --help'"
else
    echo "Neither uv nor pip found. Skipping CLI install. Skill works without it."
fi

echo ""
echo "=== Installation complete ==="
echo "  Data:   $SELF_TUNE_HOME/"
echo "  Skill:  $SKILL_DIR"
echo "  Config: $SELF_TUNE_HOME/config.yaml"
echo ""
echo "The reflect skill will auto-activate in Claude Code sessions."
