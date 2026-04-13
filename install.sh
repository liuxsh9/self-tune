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

# 5. Install CLI (optional — requires Python 3.10+)
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
        echo "Installing CLI tool (Python $PYTHON_VERSION)..."
        pip install -e "$SCRIPT_DIR/cli/" --quiet
        echo "CLI installed: run 'self-tune --help'"
    else
        echo "Python $PYTHON_VERSION found but >=3.10 required. Skipping CLI install."
    fi
else
    echo "Python not found. Skipping CLI install. Skill works without it."
fi

echo ""
echo "=== Installation complete ==="
echo "  Data:   $SELF_TUNE_HOME/"
echo "  Skill:  $SKILL_DIR"
echo "  Config: $SELF_TUNE_HOME/config.yaml"
echo ""
echo "The reflect skill will auto-activate in Claude Code sessions."
