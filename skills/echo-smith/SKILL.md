---
name: echo-smith
description: >
  Use when the agent just received a user correction,
  when the agent is about to retry an approach for the
  third time, or when the agent realizes a previous
  solution was wrong. Do not use when the task is
  proceeding smoothly without notable friction.
---

# Echo-smith: Experience Distillation

Extract learning experiences from the current interaction and persist them
as SFT training data and CLAUDE.md reminder candidates. All reflection work
runs in background subagents — never block or pollute the main workflow.

## Trigger Criteria

Invoke this skill when ANY of these are true:
- You retried an approach 3+ times before succeeding
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

Prepare a concise context snapshot for the subagent. Include ONLY:
1. **Task description** (one sentence)
2. **Episode summary**:
   - What you did that was wrong or inefficient
   - What the user said (if they intervened)
   - What the correct approach turned out to be
   - Key tool results that contained signals you missed
3. **Project context** (language, framework, architecture)

Do NOT include: full conversation history, unrelated code, other task discussions.

### Step 3: Dispatch Subagent

Use the Agent tool with `run_in_background=true`.

Choose the appropriate prompt template:
- Sidecar/Retrospective: Read `./sidecar-prompt.md` and include it in the agent prompt
- Correction: Read `./correction-prompt.md` and include it in the agent prompt

Pass the context package from Step 2 as the opening section of the prompt.

### Step 4: Handle Result

When the subagent completes:
- If Reminder candidates were generated: **briefly** notify the user (one sentence)
  and ask if they want to review. If approved, write to CLAUDE.md under
  `## Echo-smith Reminders`.
- If only SFT data was generated: silent, or one-line summary
  ("Echo-smith: extracted 2 insights from this session").
- **NEVER** expand details unless the user asks.

## Interaction with Other Skills

- Wait for `systematic-debugging` to conclude before triggering
- Only trigger from the main conversation, never from within a subagent
- Do not trigger during an active echo-smith cycle
