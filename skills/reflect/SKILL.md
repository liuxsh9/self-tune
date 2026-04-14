---
name: reflect
description: >
  Use when the user corrects the agent's approach or provides
  a hint that changes direction, when the agent retried or
  changed strategy after something failed, when the agent
  discovers a previous solution was wrong, or when a task
  succeeded but took significantly more rounds than necessary.
  Do not use when the task proceeds smoothly AND efficiently.
  May be auto-triggered by the reflect sentinel in CLAUDE.md.
---

# Self-tune: Experience Distillation

Extract learning experiences from the current interaction and persist them
as SFT training data. All reflection work
runs in background subagents — never block or pollute the main workflow.

## The Iron Law

NEVER generate SFT data where the CoT references information not present in the query.
NEVER block or degrade the user's main workflow for reflection work.

## Trigger Criteria

> **Auto-trigger**: The sentinel in `~/.claude/CLAUDE.md` runs a quick
> self-check after each user request and invokes this skill automatically.
> You may also invoke it manually (`/reflect`) if the sentinel missed an episode.

Invoke this skill when ANY of these are true:
- You retried an approach after it failed or hit a dead end
- The user corrected your direction or thinking
- You changed strategy after realizing your approach was wrong
- The user provided a key hint that unblocked progress
- You discover that a previous solution was actually incorrect
- A task completed successfully but took significantly more rounds than necessary
  (e.g., 8+ tool calls for something achievable in 2-3)
- A non-trivial task was completed with exceptional efficiency (e.g., correct approach
  on first attempt, minimal tool calls, no backtracking) — use `success_exemplar` type

## When NOT to Invoke

- The task proceeded smoothly, efficiently, and without notable friction
  (UNLESS it was exceptionally efficient on a non-trivial task — that's success_exemplar)
- The only "issue" was gathering routine requirements
- During an active systematic-debugging session (wait until it concludes)
- Inside a subagent (only invoke from the main conversation)
- Already in a reflect cycle
- Uncertain — under-triggering is better than over-triggering

## Common Rationalizations

These are traps. Recognize them and proceed anyway.

| Thought | Reality |
|---------|---------|
| "This correction is too small to log" | Small corrections often reveal systematic patterns. Log it. |
| "I'll just save a reminder, skip the SFT" | SFT is the core value. Always generate if quality passes. |
| "The user's correction was obvious, not worth extracting" | If it was obvious, you should have done it right the first time. That's the learning. |
| "Let me finish the task first, then reflect" | Use sidecar mode — reflection runs in background, doesn't block. |
| "I already know this pattern" | If you knew it, you wouldn't have failed. Your knowledge and behavior are different things. |
| "This is too project-specific to generalize" | Use L1 (most specific) generalization level. The specificity itself is valuable for SFT. |
| "The task succeeded, so there's nothing to learn" | Success doesn't mean efficiency. If you took 8 rounds for a 2-round task, that's training signal. |

## Cost Assessment

Before dispatching, quickly assess:
- Is this interaction truly novel? (not a repeat of a known pattern)
- Is the lesson generalizable? (not a one-off project detail)

If either is NO, skip.

## Execution Protocol

### Step 1: Identify Trigger Type

Determine which mode applies:
- **Sidecar**: You detected a turning point mid-task
- **Retrospective**: The task just completed and the process had friction
- **Correction**: You discovered a historical insight was wrong

### Step 2: Build Context Package

Construct a structured context block for the subagent. Use this exact template:

---BEGIN CONTEXT---
## Task
[One sentence: what you were trying to accomplish]

## Episode
**What went wrong or was suboptimal:** [Describe the incorrect approach, inefficient path,
or unnecessary extra rounds taken]
**User intervention:** [Exact quote, or "none" if self-discovered or efficiency-only]
**Correct approach:** [What actually worked or should have been done]
**Key evidence missed:** [Specific tool output that contained the signal]

## Environment
- Language: [e.g., Python 3.12]
- Framework: [e.g., FastAPI, or "none"]
- Key files: [list 1-3 most relevant files]

## Existing Data
[Run this to gather existing data — copy the output directly:]
```bash
.venv/bin/python3 -c "
import json, os, pathlib
idx = pathlib.Path.home() / '.self-tune' / 'index.json'
if idx.exists():
    d = json.loads(idx.read_text())
    print(f'Total insights: {d[\"stats\"][\"total_insights\"]}')
else:
    print('Total insights: 0')
idir = pathlib.Path.home() / '.self-tune' / 'data' / 'insights'
if idir.exists():
    for f in sorted(idir.glob('*.json'))[-3:]:
        a = json.loads(f.read_text()).get('root_cause',{}).get('abstract','?')
        print(f'  - {a}')
"
```

## Dispatch Parameters
- model_tier: [standard|premium — set by dispatcher based on Step 3 model choice]

## Raw Conversation Excerpt
[Paste the relevant portion of the conversation verbatim — from around the
point where the key signal first appeared through the resolution. Include
tool calls and their results exactly as they occurred. For large tool outputs,
keep the decision-relevant lines and annotate trimmed portions with
[trimmed: N→M lines].

Target: the episode window from ~5 turns before T_optimal through T_actual.
Aim for ≈4,000-8,000 tokens. If the episode spans more, trim aggressively
at the boundaries and annotate [trimmed: N→M turns].]
---END CONTEXT---

After the context block, include the full content of the appropriate prompt template
(sidecar-prompt.md, retrospective-prompt.md, or correction-prompt.md).

Do NOT include: unrelated conversation turns, code you didn't read, the full session if only a small segment is relevant.

### Step 3: Dispatch Subagent

Use the Agent tool with these parameters:
- `run_in_background: true` (never block main workflow)
- `mode: "bypassPermissions"` (subagent needs to write to ~/.self-tune/data/)
- `model`: Choose based on episode value:
  - **"opus"** (default): For all sidecar episodes in Claude Code context — CoT quality is critical
  - **"opus"**: For high-value episodes where CoT quality is critical. Use opus when ANY of:
    - The adversarial verdict is clearly `high_confidence` and wasted_rounds > 5
    - The episode involves complex multi-step reasoning errors
    - The episode captures a rare failure mode (model persisted in wrong direction
      across 3+ attempts, or a previously-accepted solution turned out to be wrong)
  - **"sonnet"**: For lower-value episodes — straightforward corrections, simple patterns
  - When in doubt, use opus in Claude Code context. CoT quality matters more than cost here.

The prompt MUST include:
1. The context package from Step 2 (above), including the raw conversation excerpt —
   this is the primary evidence source the subagent will use for building SFT queries.
2. The FULL content of the prompt template file — read it with the Read tool and paste it in.
   Do NOT tell the subagent to "read ./sidecar-prompt.md" — it cannot access skill files.
3. The FULL content of output-schema.md — same reason.

### Step 4: Handle Result

When the subagent completes:
- **SFT data generated**: Silent, or one-line summary ("Self-tune: extracted 2 insights, 1 SFT sample").
- **Subagent failed or produced no output**: Log silently, do not bother the user.
- **NEVER** expand details unless the user asks.
- **NEVER** let self-tune activity interrupt or slow the user's primary task.

## Interaction with Other Skills

- Wait for `systematic-debugging` to conclude before triggering
- Only trigger from the main conversation, never from within a subagent
- Do not trigger during an active reflect cycle
