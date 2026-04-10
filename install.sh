#!/usr/bin/env bash
# install.sh — One-command Echo-smith installer
set -euo pipefail

ECHO_SMITH_HOME="$HOME/.echo-smith"
SKILL_DIR="$HOME/.claude/skills/echo-smith"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Echo-smith Installer ==="

# 1. Create data directory structure
echo "Creating data directories..."
mkdir -p "$ECHO_SMITH_HOME/data/traces"
mkdir -p "$ECHO_SMITH_HOME/data/insights"
mkdir -p "$ECHO_SMITH_HOME/data/samples"
mkdir -p "$ECHO_SMITH_HOME/data/reminders"
mkdir -p "$ECHO_SMITH_HOME/data/corrections"

# 2. Create default config if not exists
if [ ! -f "$ECHO_SMITH_HOME/config.yaml" ]; then
    echo "Creating default config..."
    cp "$SCRIPT_DIR/config.yaml.template" "$ECHO_SMITH_HOME/config.yaml"
else
    echo "Config already exists, skipping."
fi

# 3. Create index.json if not exists
if [ ! -f "$ECHO_SMITH_HOME/index.json" ]; then
    echo '{"last_updated": null, "stats": {"total_traces": 0, "total_insights": 0, "total_samples": 0, "total_reminders": 0, "total_corrections": 0}}' > "$ECHO_SMITH_HOME/index.json"
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
    ln -s "$SCRIPT_DIR/skills/echo-smith" "$SKILL_DIR"
    echo "Skill symlinked: $SKILL_DIR -> $SCRIPT_DIR/skills/echo-smith"
fi

# 5. Install CLI (optional — requires Python 3.10+)
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
        echo "Installing CLI tool (Python $PYTHON_VERSION)..."
        pip install -e "$SCRIPT_DIR/cli/" --quiet
        echo "CLI installed: run 'echo-smith --help'"
    else
        echo "Python $PYTHON_VERSION found but >=3.10 required. Skipping CLI install."
    fi
else
    echo "Python not found. Skipping CLI install. Skill works without it."
fi

echo ""
echo "=== Installation complete ==="
echo "  Data:   $ECHO_SMITH_HOME/"
echo "  Skill:  $SKILL_DIR"
echo "  Config: $ECHO_SMITH_HOME/config.yaml"
echo ""
echo "The echo-smith skill will auto-activate in Claude Code sessions."
