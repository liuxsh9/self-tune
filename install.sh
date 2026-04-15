#!/usr/bin/env bash
# install.sh — One-command Self-tune installer
set -euo pipefail

SELF_TUNE_HOME="$HOME/.self-tune"
SKILL_DIR="$HOME/.claude/skills/reflect"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Colors ──────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
    BOLD='\033[1m'
    DIM='\033[2m'
    CYAN='\033[36m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    RESET='\033[0m'
else
    BOLD='' DIM='' CYAN='' GREEN='' YELLOW='' RESET=''
fi

# ── Banner ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Self-tune Installer${RESET}"
echo -e "${DIM}────────────────────────────────────────────────────${RESET}"
echo ""
echo -e "  Self-tune silently watches your Claude Code sessions."
echo -e "  When the model fails, retries, or gets corrected, a background"
echo -e "  agent extracts the lesson as structured SFT training data."
echo ""
echo -e "  ${DIM}Your workflow is never blocked — all analysis runs in the background.${RESET}"
echo ""

# ── What will happen ────────────────────────────────────────────────
echo -e "${BOLD}What this installer does:${RESET}"
echo ""
echo -e "  ${CYAN}1.${RESET} Create data directory           ${DIM}~/.self-tune/data/${RESET}"
echo -e "  ${CYAN}2.${RESET} Write default config             ${DIM}~/.self-tune/config.yaml${RESET}"
echo -e "  ${CYAN}3.${RESET} Symlink skill into Claude Code   ${DIM}~/.claude/skills/reflect${RESET}"
echo -e "  ${CYAN}4.${RESET} Install CLI tool (optional)      ${DIM}self-tune${RESET}"
echo ""
echo -e "${DIM}────────────────────────────────────────────────────${RESET}"
echo ""

# ── Step 1: Data directories ───────────────────────────────────────
echo -e "${CYAN}[1/4]${RESET} Creating data directories..."
mkdir -p "$SELF_TUNE_HOME/data/traces"
mkdir -p "$SELF_TUNE_HOME/data/insights"
mkdir -p "$SELF_TUNE_HOME/data/samples"
mkdir -p "$SELF_TUNE_HOME/data/corrections"

# ── Step 2: Config ──────────────────────────────────────────────────
echo -e "${CYAN}[2/4]${RESET} Setting up config..."
if [ ! -f "$SELF_TUNE_HOME/config.yaml" ]; then
    cp "$SCRIPT_DIR/config.yaml.template" "$SELF_TUNE_HOME/config.yaml"
    echo -e "       Created ${DIM}~/.self-tune/config.yaml${RESET}"
else
    echo -e "       Already exists, skipping."
fi

if [ ! -f "$SELF_TUNE_HOME/index.json" ]; then
    echo '{"last_updated": null, "stats": {"total_traces": 0, "total_insights": 0, "total_samples": 0, "total_corrections": 0}}' > "$SELF_TUNE_HOME/index.json"
fi

# ── Step 3: Skill symlink ──────────────────────────────────────────
echo -e "${CYAN}[3/4]${RESET} Installing skill..."
mkdir -p "$HOME/.claude/skills"
if [ -L "$SKILL_DIR" ]; then
    rm "$SKILL_DIR"
fi
if [ -d "$SKILL_DIR" ]; then
    echo -e "       ${YELLOW}WARNING${RESET}: $SKILL_DIR is a real directory, not a symlink. Skipping."
else
    ln -s "$SCRIPT_DIR/skills/reflect" "$SKILL_DIR"
    echo -e "       Symlinked → ${DIM}$SCRIPT_DIR/skills/reflect${RESET}"
fi

# ── Step 4: CLI ─────────────────────────────────────────────────────
echo -e "${CYAN}[4/4]${RESET} Installing CLI..."
if command -v uv &>/dev/null; then
    uv tool install --force --from "$SCRIPT_DIR" self-tune 2>/dev/null \
        && echo -e "       Installed via ${BOLD}uv${RESET}" \
        || echo -e "       ${YELLOW}uv tool install failed — try manually: uv tool install --from $SCRIPT_DIR self-tune${RESET}"
elif command -v pip &>/dev/null; then
    pip install "$SCRIPT_DIR" --quiet \
        && echo -e "       Installed via ${BOLD}pip${RESET}" \
        || echo -e "       ${YELLOW}pip install failed — try manually: pip install $SCRIPT_DIR${RESET}"
else
    echo -e "       ${YELLOW}Skipped${RESET} — neither uv nor pip found."
    echo -e "       Install uv (${DIM}curl -LsSf https://astral.sh/uv/install.sh | sh${RESET}) then re-run."
fi

# ── Done ────────────────────────────────────────────────────────────
echo ""
echo -e "${DIM}────────────────────────────────────────────────────${RESET}"
echo -e "${GREEN}${BOLD}Done!${RESET}"
echo ""
echo -e "${BOLD}How it works:${RESET}"
echo ""
echo -e "  The skill is a ${BOLD}symlink${RESET} — it always points to this repo."
echo -e "  To update, just pull the latest code:"
echo ""
echo -e "    ${DIM}cd $SCRIPT_DIR && git pull${RESET}"
echo ""
echo -e "  No reinstall needed. The skill picks up changes immediately."
echo -e "  (If the CLI itself changed, re-run ${DIM}./install.sh${RESET} to update it.)"
echo ""
echo -e "${BOLD}Getting started:${RESET}"
echo ""
echo -e "  Just use Claude Code normally. Self-tune activates automatically"
echo -e "  when the model retries, gets corrected, or takes an inefficient path."
echo ""
echo -e "  You can also trigger it manually inside Claude Code:"
echo ""
echo -e "    ${CYAN}/reflect${RESET}     tell Claude to analyze the current session for lessons"
echo ""
echo -e "  The skill is registered as ${BOLD}reflect${RESET} in Claude Code."
echo -e "  Typing ${CYAN}/reflect${RESET} invokes it — same as the auto-trigger, but on demand."
echo -e "  Useful when you notice a learning moment the auto-sentinel missed."
echo ""
echo -e "  After a few sessions, check what was captured:"
echo ""
echo -e "    ${CYAN}self-tune stats${RESET}                         overview"
echo -e "    ${CYAN}self-tune list --type samples${RESET}            browse SFT samples"
echo -e "    ${CYAN}self-tune show ${DIM}<id>${RESET}                       inspect one item"
echo -e "    ${CYAN}self-tune validate${RESET}                      check data integrity"
echo -e "    ${CYAN}self-tune export -f sft -o train.jsonl${RESET}  export for fine-tuning"
echo ""
echo -e "${BOLD}File locations:${RESET}"
echo ""
echo -e "    Data    ${DIM}~/.self-tune/data/${RESET}               traces, insights, samples"
echo -e "    Config  ${DIM}~/.self-tune/config.yaml${RESET}         trigger & retention settings"
echo -e "    Skill   ${DIM}~/.claude/skills/reflect${RESET}         symlink → this repo"
echo ""
