---
name: echo-smith
description: >
  Use when the user corrects the agent's approach or provides
  a hint that changes direction, when the agent retried or
  changed strategy after something failed, or when the agent
  discovers a previous solution was wrong. Do not use when
  the task is proceeding smoothly without friction.
---

# Echo-smith: Experience Distillation

Extract learning experiences from the current interaction and persist them
as SFT training data and CLAUDE.md reminder candidates. All reflection work
runs in background subagents — never block or pollute the main workflow.

## The Iron Law

NEVER generate SFT data where the CoT references information not present in the query.
NEVER block or degrade the user's main workflow for reflection work.

## Trigger Criteria

Invoke this skill when ANY of these are true:
- You retried an approach after it failed or hit a dead end
- The user corrected your direction or thinking
- You changed strategy after realizing your approach was wrong
- The user provided a key hint that unblocked progress
- You discover that a previous solution was actually incorrect

## When NOT to Invoke

- The task proceeded smoothly without notable friction
- The only "issue" was gathering routine requirements
- During an active systematic-debugging session (wait until it concludes)
- Inside a subagent (only invoke from the main conversation)
- Already in an echo-smith reflection cycle
- Uncertain — under-triggering is better than over-triggering

## Common Rationalizations

These are traps. Recognize them and proceed anyway.

| Thought | Reality |
|---------|---------|
| "This correction is too small to log" | Small corrections often reveal systematic patterns. Log it. |
| "I'll just save a reminder, skip the SFT" | SFT is the long-term value; reminders are byproduct. Always generate both if quality passes. |
| "The user's correction was obvious, not worth extracting" | If it was obvious, you should have done it right the first time. That's the learning. |
| "Let me finish the task first, then reflect" | Use sidecar mode — reflection runs in background, doesn't block. |
| "I already know this pattern" | If you knew it, you wouldn't have failed. Your knowledge and behavior are different things. |
| "This is too project-specific to generalize" | Use L1 (most specific) generalization level. The specificity itself is valuable for SFT. |

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
**What went wrong:** [Describe the incorrect approach or inefficient path]
**User intervention:** [Exact quote or "none" if self-discovered]
**Correct approach:** [What actually worked or should have been done]
**Key evidence missed:** [Specific tool output that contained the signal]

## Environment
- Language: [e.g., Python 3.12]
- Framework: [e.g., FastAPI, or "none"]
- Key files: [list 1-3 most relevant files]

## Existing Data
- Total insights: [number from ~/.echo-smith/index.json]
- Recent insight topics: [list last 3 root_cause.abstract if any]
---END CONTEXT---

After the context block, include the full content of the appropriate prompt template
(sidecar-prompt.md, retrospective-prompt.md, or correction-prompt.md).

Do NOT include: full conversation history, unrelated code, code you didn't read.

### Step 3: Dispatch Subagent

Use the Agent tool with these parameters:
- `run_in_background: true` (never block main workflow)
- `mode: "bypassPermissions"` (subagent needs to write to ~/.echo-smith/data/)
- `model: "sonnet"` (sufficient for reflection; save opus for the user's main work)

The prompt MUST include:
1. The context package from Step 2 (above)
2. The FULL content of the prompt template file — read it with the Read tool and paste it in.
   Do NOT tell the subagent to "read ./sidecar-prompt.md" — it cannot access skill files.
3. The FULL content of output-schema.md — same reason.

### Step 4: Handle Result

When the subagent completes:
- **Reminder candidates generated**: Briefly notify user (one sentence), ask to review.
  If approved, write to CLAUDE.md under `## Echo-smith Reminders`.
- **SFT data only**: Silent, or one-line summary ("Echo-smith: extracted 2 insights").
- **Subagent failed or produced no output**: Log silently, do not bother the user.
- **NEVER** expand details unless the user asks.
- **NEVER** let echo-smith activity interrupt or slow the user's primary task.

## Interaction with Other Skills

- Wait for `systematic-debugging` to conclude before triggering
- Only trigger from the main conversation, never from within a subagent
- Do not trigger during an active echo-smith cycle
