# Self-tune Design Specification

> Version: 1.0 | Date: 2026-04-10
> Status: Draft

## 1. Overview

### 1.1 Problem Statement

AI coding assistants (Claude Code, Cursor, Copilot, etc.) frequently require multiple rounds of trial-and-error, user corrections, and strategy changes to complete tasks. These interaction trajectories contain valuable learning signals — moments where the model's reasoning failed, where a user's hint unlocked progress, or where an inefficient exploration path could have been compressed. Currently, these signals are lost after each session.

### 1.2 Solution

Self-tune is a system that automatically extracts learning experiences from AI coding assistant interactions and produces two outputs:

- **SFT training data** (long-term): Structured query + chain-of-thought + response samples that teach models to make better decisions autonomously in agentic multi-turn scenarios.
- **CLAUDE.md reminders** (short-term): Actionable rules written to the user's configuration, providing immediate experience-based guidance in subsequent sessions.

### 1.3 Design Principles

1. **Never degrade user experience.** All reflection work runs in isolated subagents. The user's main workflow context is sacred — zero pollution, zero blocking.
2. **Users are not always right.** User corrections may reflect personal preference rather than objective improvement. The system must distinguish genuine improvements from style preferences.
3. **Generalize carefully.** Every insight has a correct level of abstraction. Too specific is useless; too broad is harmful. Default to the most specific formulation.
4. **Train for autonomy.** SFT data should teach models to reason independently — user hints are internalized into self-directed reasoning, not preserved as instructions to follow.
5. **Progressive deployment.** Skill-only → CLI tools → Central server. Each phase is independently valuable.

---

## 2. Architecture

### 2.1 System Overview

```
Phase 1: Skill + Local Storage
┌─────────────────── Claude Code Session ───────────────────┐
│                                                           │
│  User interacts with model normally                       │
│       │                                                   │
│       ▼ (model detects learning signal via skill match)   │
│  ┌──────────────────────────────────────────┐             │
│  │  Self-tune Skill                        │             │
│  │  → Spawns background subagent            │             │
│  │  → Main workflow continues unblocked     │             │
│  └──────────────────────────────────────────┘             │
│       │                                                   │
│       ▼ (subagent, isolated context)                      │
│  ┌──────────────────────────────────────────┐             │
│  │  Reflection Subagent                     │             │
│  │  - Analyze episode                       │             │
│  │  - Generate Insight (dual version)       │             │
│  │  - Build SFT samples                     │             │
│  │  - Generate Reminder candidates          │             │
│  │  - Write to ~/.self-tune/data/          │             │
│  └──────────────────────────────────────────┘             │
└───────────────────────────────────────────────────────────┘

Phase 2: + CLI Tool
  self-tune-cli: batch validation, quality scoring,
  multi-format export (SFT/DPO), data management

Phase 3: + Central Server
  Data aggregation, strong-model re-evaluation,
  cross-user deduplication, desensitization, dataset export
```

### 2.2 Component Responsibilities

| Component | Phase | Responsibility |
|-----------|-------|----------------|
| Self-tune Skill | 1 | Trigger detection, subagent dispatch, reminder approval |
| Reflection Subagent | 1 | Episode analysis, insight extraction, SFT/reminder generation |
| Local Storage | 1 | Structured file-based persistence at `~/.self-tune/` |
| CLI Tool | 2 | Batch operations, quality scoring, export, upload |
| Central Server | 3 | Aggregation, strong-model judging, dataset production |

---

## 3. Core Concepts

### 3.1 Concept Model

```
Trace 1:N Episode
Episode 1:1 Insight
Insight 1:N SFT Sample  (concrete + abstract versions)
Insight 1:0..1 Reminder
Insight 0..N:0..N Correction
```

**Trace** — A complete interaction session record. Contains metadata about the task, model, outcome, and a compressed conversation snapshot.

**Episode** — A segment within a Trace representing a "cognitive turning point" — where the model failed, got stuck, was corrected, or changed strategy.

**Insight** — The distilled learning from an Episode. Always produced in dual versions:
- `concrete_version`: Preserves specific context (file names, error messages, framework details)
- `abstract_version`: Generalized pattern applicable beyond the specific project

**SFT Sample** — A training data point with three components:
- `query`: Reconstructed "accident scene" — the context a model faces at a decision point
- `cot`: An improved chain-of-thought, better than what actually happened
- `response`: The ideal action/output

**Reminder** — An actionable rule suitable for writing into CLAUDE.md, providing immediate guidance.

**Correction** — A record that invalidates, supersedes, or amends a previous Insight when it is later found to be wrong.

### 3.2 Insight Classification (insight_type)

| Type | Description | Primary Output | Example |
|------|-------------|----------------|---------|
| `skill_gap` | Model lacks a specific capability | SFT | Didn't know to use RS256 in microservices |
| `knowledge_gap` | Model lacks specific knowledge | SFT | Unaware of API's undocumented behavior |
| `reasoning_error` | Model's reasoning chain was flawed | SFT | Drew wrong conclusion from error message |
| `exploration_inefficiency` | Model's exploration path was wasteful | SFT | Read 10 files when Grep would locate in 1 |
| `tool_orchestration` | Model chose wrong tools or sequence | SFT | Used Read to guess paths instead of Glob |
| `backtrack_failure` | Model failed to abandon wrong direction | SFT | 5 rounds on config when issue was in Dockerfile |
| `preference_probe` | User correction reflects preference, not error | SFT (as inquiry pattern) | Should ask user's preference, not assume |
| `env_specific` | Environment-specific issue | Reminder only | Proxy connectivity, local toolchain quirks |

### 3.3 Dual-Output Flywheel

```
Experience Extraction Pipeline
    ├→ Long-term: SFT Data → Training → Improve model base capabilities
    │                                    (benefits all users)
    └→ Short-term: Reminder → Write to CLAUDE.md → Immediate UX improvement
                                                   (benefits current user)
                                    │
                                    ▼
                   User retain/delete behavior on Reminders
                   = quality validation signal for SFT data
                                    │
                                    └→ feeds back into quality scoring
```

---

## 4. Trigger Mechanism

### 4.1 Skill Description (Auto-Matching)

The skill uses Claude Code's native skill-matching mechanism. The model evaluates the skill's description against the current context on each turn, identical to how `brainstorming` or `systematic-debugging` skills are automatically invoked.

```yaml
---
name: self-tune
description: >
  Use when the agent just received a user correction,
  when the agent is about to retry an approach for the
  third time, or when the agent realizes a previous
  solution was wrong. Do not use when the task is
  proceeding smoothly without notable friction.
---
```

Note: Description contains ONLY trigger conditions, no workflow summary (per Anthropic skill best practices).

### 4.2 Trigger Modes

**Sidecar Mode (during task execution):**
Model detects a turning point mid-task → spawns a background subagent with a context snapshot → continues main workflow without blocking.

**Retrospective Mode (after task completion):**
Task finishes → model judges the process had notable learning moments → spawns a background subagent for full-process review.

**Manual Mode (user-initiated):**
User invokes `/self-tune` directly. Preserved but not relied upon.

### 4.3 Trigger Criteria

**DO trigger when:**
- The model retried an approach 3+ times before succeeding
- The user explicitly corrected the model's direction
- The model changed strategy after realizing its approach was wrong
- The user provided a key hint that unblocked progress
- The model discovers a previous solution was actually incorrect

**DO NOT trigger when:**
- The task proceeded smoothly without notable friction
- The only "issue" was gathering routine requirements
- During an active `systematic-debugging` skill session (wait until it concludes)
- Inside a subagent (only trigger from the main conversation)
- Already in an self-tune reflection cycle
- Uncertain — under-triggering is better than over-triggering

### 4.4 Cost Assessment Gate

Before dispatching a subagent, the skill instructs the model to quickly assess:
- Is this interaction truly novel? (not a repeat of a known pattern)
- Is the lesson generalizable? (not a one-off project-specific detail)
- Would the extracted experience have training value?

If any answer is NO, skip invocation.

---

## 5. Context Isolation

### 5.1 Core Constraint

The main conversation context is inviolable. Self-tune's total footprint in the main context must be < 100 tokens per trigger:
- Trigger judgment: internal model decision, zero output
- Spawn subagent: one tool call (~50 tokens)
- Result notification: one sentence (~30 tokens)

### 5.2 Subagent Receives a Curated Context Package

```
Passed to subagent:
  1. Task description (one sentence)
  2. Episode summary:
     - What the model did (the error/inefficiency)
     - What the user said (if applicable — correction/hint)
     - What the correct approach turned out to be
  3. Project context (language, framework, architecture)
  4. Instruction: execute self-tune reflection workflow

NOT passed:
  ✗ Full conversation history
  ✗ Unrelated code file contents
  ✗ Previous task discussions
```

### 5.3 Context Budget by Scenario

| Scenario | Execution | Budget | Content |
|----------|-----------|--------|---------|
| Sidecar reflection | Background subagent | ~50K tokens | Single episode analysis |
| Retrospective review | Background subagent | ~100K tokens | Multi-episode + global review |
| Historical correction | Background subagent | ~30K tokens | Targeted correction |
| Batch aggregation | Offline CLI + strong model | Unlimited | Cross-user, cross-time |

---

## 6. SFT Data Design

### 6.1 SFT Data Types

**Type 1: User Prompt Internalization**
- Source: User corrected the model's direction
- Query cut point: Before user intervention (at T_actual)
- CoT transformation: User's wisdom → model's autonomous reasoning
- Key principle: User hints are the source of learning signal but must NOT appear in the training query. The goal is for the model to reach the same conclusion independently.

**Type 2: Exploration Path Compression**
- Source: Model took 10 rounds to find what could be found in 3
- Query cut point: At T_optimal (earliest moment correct judgment was possible)
- CoT transformation: Wasteful exploration → optimal path
- Key mechanism: Optimal Decision Point Detection — backtrack from T_actual to find the earliest tool result that contained the key signal.

**Type 3: Error Correction**
- Source: A previously accepted solution was later found to be wrong
- Query cut point: At the moment of contradiction discovery
- CoT transformation: Old understanding → corrected understanding
- Note: The correction itself generates a new Insight and potentially invalidates the original.

**Type 4: Preference → Inquiry Transformation**
- Source: User corrected based on personal preference, not objective improvement
- CoT transformation: Making assumptions → proactively asking
- Example: Instead of learning "always use quicksort", learn "when multiple valid sorting approaches exist, present options and ask user preference."

**Type 5: Backtrack Decision**
- Source: Model persisted in a wrong direction too long before switching
- Query cut point: The moment when continuing was no longer rational (e.g., 3rd consecutive failure in same direction)
- CoT transformation: Tunnel vision → strategic reassessment

**Type 6: Tool Orchestration Optimization**
- Source: Model used inefficient tool choices or sequences
- Query cut point: Before the inefficient tool call
- CoT transformation: Inefficient tool sequence → optimal tool selection
- Examples: Read-guessing paths vs Glob; serial searches vs parallel; Bash for grep vs Grep tool.

### 6.2 Query Design Principles

**Reflect real agentic distribution:**
Real Claude Code sessions are dominated by assistant ↔ tool interactions, not user ↔ assistant dialogue. A typical task: user says 2 sentences, model + tools interact 10+ rounds. Query must reflect this.

```
Role distribution in query:
  user:      Task description + key corrections (typically 1-3 turns)
  assistant: Intent expressions, reasoning fragments (brief, each turn)
  tool:      Calls and results (core content, intelligently trimmed)
```

**Tool result trimming strategy:**
- Read: Keep only decision-relevant code snippets, annotate line numbers
- Grep: Keep match results, remove irrelevant lines
- Bash: Keep error output and key result lines
- Edit: Keep diff summary
- Annotate: `[trimmed: original N lines, kept M lines]`

**Target length:** 1000-3000 tokens for query portion.

**Validation test:** Cover the CoT and look only at the query — could a strong model independently derive the CoT's conclusions from the information present? If not, the query is missing key signals or the CoT's reasoning jumps too far.

### 6.3 CoT Quality Requirements

**Required patterns (enforce in subagent prompt):**

| Pattern | Description | Example |
|---------|-------------|---------|
| Evidence-chained reasoning | Every conclusion anchored to specific tool output | "Grep returned X at line 42, which indicates Y" |
| Decision tree externalization | List options, weigh tradeoffs, choose | "Three approaches: A (risk...), B (risk...), C (best because...)" |
| Expect-observe-revise | Explicit prediction-mismatch-correction | "I expected string[], but TypeScript says Promise<string[]>, so..." |

**Forbidden anti-patterns (reject in quality gate):**

| Anti-pattern | Detection heuristic | Why harmful |
|--------------|---------------------|-------------|
| Post-hoc rationalization | Specific line numbers/variable names appear without prior tool lookup | Teaches "fake reasoning" |
| Content-free hedging | "Let me carefully analyze..." with no actual analysis | Wastes tokens, teaches verbosity |
| Over-explaining basics | "package.json is a Node.js config file..." | Dilutes valuable reasoning with noise |

### 6.4 DPO Data (Free Byproduct)

Every Type 2 (path compression) and Type 5 (backtrack) sample naturally produces a DPO pair:

```
prompt:   shared query context
chosen:   optimized trajectory (from SFT sample)
rejected: original inefficient trajectory (from Trace)
```

No additional collection needed — just an alternative export format.

---

## 7. Quality Assurance

### 7.1 Adversarial Reflection

For every Insight, the subagent generates two opposing attributions:

```
Attribution A: "The user's correction is objectively better because..."
Attribution B: "The original approach is also valid because..."
```

Each gets a confidence score (0-1). Only when A significantly exceeds B (e.g., >0.7 vs <0.3) is the insight marked as high-confidence. Otherwise it enters a "pending validation" queue.

This directly addresses the constraint that **users are not always right**.

### 7.2 Generalization Ladder

Every Insight must produce three levels of formulation:

```
L1 (most specific): "In Next.js 14 App Router, Server Components cannot use useState"
L2 (moderate):      "React Server Components cannot use client-side hooks"
L3 (most abstract): "Server-rendered components have API usage restrictions"
```

Rules:
- SFT data defaults to L1
- Upgrade to L2 only after cross-user validation
- L3 is almost never used directly for training (only for search indexing)
- If the model cannot generate a reasonable counter-example for the generalization, it may be over-generalizing

### 7.3 CoT Anti-Pattern Filtering

Automated checks applied by the subagent before writing data:

1. **Post-hoc rationalization check:** Does the CoT reference specific identifiers that weren't present in any tool output within the query? → Reject.
2. **Content-free hedging check:** Does the CoT contain > 50 tokens before the first substantive analytical statement? → Flag for revision.
3. **Evidence anchoring check:** Does every major conclusion in the CoT reference a specific tool result from the query? → Required.

### 7.4 Independent Value Assessment

Each Insight is evaluated independently of the task's overall outcome:

```jsonc
{
  "independent_value": true,
  "value_rationale": "The knowledge about RS256 vs HS256 in microservices
                      is valid regardless of whether the overall auth task succeeded",
  "task_outcome": "failed"  // task failed, but this insight still has value
}
```

---

## 8. Data Schema

### 8.1 Storage Structure

```
~/.self-tune/                    # Global, cross-project
├── config.yaml                   # User configuration
├── data/
│   ├── traces/                   # Raw trajectory snapshots
│   │   └── {trace-id}.json
│   ├── insights/                 # Extracted insights
│   │   └── {insight-id}.json
│   ├── samples/                  # SFT training samples
│   │   └── {sample-id}.json
│   ├── reminders/                # Reminder records (with lifecycle metadata)
│   │   └── {reminder-id}.json
│   └── corrections/              # Correction records
│       └── {correction-id}.json
├── index.json                    # Local data index for fast queries
└── upload-log.json               # Upload history
```

Located at `~/.self-tune/` (not project directory) because:
- Insights are cross-project knowledge
- Avoids polluting git repositories
- One instance per developer for company-wide deployment

### 8.2 ID Format

`{type}-{YYYYMMDD}-{random6}` — Human-readable, time-sortable, dedup-safe.

Examples: `trace-20260410-a1b2c3`, `ins-20260410-d4e5f6`, `sft-20260410-g7h8i9`

### 8.3 Trace Schema

```jsonc
{
  "id": "trace-20260410-a1b2c3",
  "created_at": "2026-04-10T14:30:00Z",
  "source": "claude-code",           // claude-code | cursor | copilot | ...
  "model": "claude-sonnet-4-6",
  "trigger": "auto",                 // auto | manual | retrospective
  "task_description": "Implement JWT auth middleware for microservice",
  "task_outcome": "success",          // success | partial | failed
  "project_context": {
    "language": "typescript",
    "framework": "express",
    "repo": "internal/auth-service"
  },
  "episodes": ["ep-20260410-x1y2z3"],
  "conversation_snapshot": {
    "segments": [
      {
        "role": "assistant",
        "summary": "Attempted express-jwt with wrong algorithm parameter",
        "content_hash": "sha256:..."
      },
      {
        "role": "tool",
        "name": "Bash",
        "summary": "npm test → 'algorithm HS256 not allowed'",
        "is_key_signal": true
      },
      {
        "role": "user",
        "summary": "Pointed out RS256 is needed for microservices",
        "is_correction": true
      }
    ]
  }
}
```

### 8.4 Insight Schema

```jsonc
{
  "id": "ins-20260410-d4e5f6",
  "trace_id": "trace-20260410-a1b2c3",
  "created_at": "2026-04-10T14:32:00Z",
  "insight_type": "knowledge_gap",
  "status": "active",                 // active | invalidated | superseded | merged

  "root_cause": {
    "concrete": "Did not know microservice JWT should use asymmetric algorithm (RS256)",
    "abstract": "When choosing crypto algorithms, failed to consider deployment architecture security constraints"
  },

  "user_correction": {
    "type": "genuine_improvement",    // genuine_improvement | preference | environmental
    "description": "User pointed out microservices should not share symmetric keys"
  },

  "adversarial_reflection": {
    "attribution_a": { "argument": "RS256 is objectively better for multi-service architectures...", "confidence": 0.88 },
    "attribution_b": { "argument": "HS256 could work if API gateway centralizes verification...", "confidence": 0.35 },
    "verdict": "high_confidence"      // high_confidence | moderate | contested
  },

  "generalization_ladder": {
    "L1": "In Express microservice JWT auth, use RS256 not HS256 when multiple services verify tokens",
    "L2": "Microservice architectures require asymmetric JWT algorithms to avoid shared secret distribution",
    "L3": "Deployment architecture constrains cryptographic algorithm choice",
    "selected_level": "L1"
  },

  "efficiency_metrics": {            // present for exploration_inefficiency / tool_orchestration / backtrack_failure
    "actual_rounds": 10,
    "optimal_rounds": 3,
    "wasted_rounds": 7,
    "t_optimal": 2,
    "missed_signals": [
      { "round": 2, "tool": "Read", "signal": "line 42: algorithm: 'HS256'", "why_missed": "Focused on function structure, did not cross-validate algorithm choice against architecture" }
    ]
  },

  "independent_value": true,
  "value_rationale": "RS256 vs HS256 knowledge is valid regardless of task outcome",

  "quality": {
    "local_score": 0.82,
    "server_score": null
  }
}
```

### 8.5 SFT Sample Schema

```jsonc
{
  "id": "sft-20260410-g7h8i9",
  "insight_id": "ins-20260410-d4e5f6",
  "created_at": "2026-04-10T14:33:00Z",
  "version": "concrete",             // concrete | abstract
  "sft_type": "exploration_compression",
  // user_prompt_internalization | exploration_compression
  // error_correction | preference_to_inquiry
  // backtrack_decision | tool_orchestration

  "query": {
    "system_context": "You are a coding assistant helping implement Express.js microservice JWT auth middleware.",
    "conversation_history": [
      {"role": "user", "content": "Help me fix auth failure — Service B cannot verify tokens"},
      {"role": "assistant", "content": "Let me check the auth middleware."},
      {"role": "tool", "name": "Read", "input": "src/auth/middleware.ts",
       "output": "// JWT middleware [trimmed: 200 lines, kept 15]\n...line 42: algorithm: 'HS256'...\n...line 58: secret: process.env.JWT_SECRET..."},
      {"role": "assistant", "content": "I see the middleware config. Let me check how Service B verifies."},
      {"role": "tool", "name": "Grep", "input": "JWT_SECRET",
       "output": "src/config.ts:12: JWT_SECRET=process.env.JWT_SECRET\nsrc/service-b/auth.ts:5: const secret = process.env.JWT_SECRET"}
    ],
    "decision_point": "Read and Grep results are in. Model has seen HS256 on line 42 and shared secret pattern. What should the model think and do next?"
  },

  "cot": "Analyzing the tool results:\n1. middleware.ts line 42 uses HS256 (symmetric algorithm)\n2. Both services read JWT_SECRET from env — they share the same secret\n3. This is a microservice architecture where Service B independently verifies tokens\n4. Key reasoning: shared symmetric secrets across services is a security risk — if any service is compromised, all token verification is compromised\n5. The 'algorithm not allowed' error likely means Service B is configured to reject HS256\n6. Root fix: migrate to RS256 (asymmetric) — auth service holds private key for signing, other services use public key for verification\n7. Before implementing, check Service B's algorithm whitelist to confirm this hypothesis",

  "response": "The issue is architectural. HS256 requires all services to share a secret, which is a security risk in microservices. Service B likely rejects HS256 by policy. Let me check its algorithm config and then migrate to RS256...",

  "quality": {
    "local_score": 0.82,
    "server_score": null,
    "evidence_anchored": true,
    "no_post_hoc_rationalization": true,
    "no_content_free_hedging": true
  },

  "dpo_rejected_available": true      // indicates original inefficient trajectory exists for DPO pairing
}
```

### 8.6 Reminder Schema

```jsonc
{
  "id": "rem-20260410-j0k1l2",
  "insight_id": "ins-20260410-d4e5f6",
  "created_at": "2026-04-10T14:33:00Z",
  "status": "pending_approval",       // pending_approval | active | invalidated | expired

  "rule": "When configuring JWT, first confirm deployment architecture. Microservices require asymmetric algorithms (RS256); monoliths can use symmetric (HS256).",

  "claude_md_text": "## [Self-tune] JWT Algorithm Selection\nWhen implementing JWT auth, first ask or confirm the deployment architecture. Use RS256 (asymmetric) for microservices, HS256 (symmetric) is acceptable for monoliths.",

  "lifecycle": {
    "validation_count": 0,
    "contradiction_count": 0,
    "last_validated": null,
    "confidence": 0.82,
    "written_to_claude_md": false,
    "user_approved": false
  },

  "scope": "global"                   // global | project | personal
}
```

### 8.7 Correction Schema

```jsonc
{
  "id": "cor-20260412-m3n4o5",
  "created_at": "2026-04-12T10:00:00Z",
  "target_type": "insight",            // insight | sample | reminder
  "target_id": "ins-20260410-d4e5f6",
  "action": "supersede",               // invalidate | supersede | amend

  "reason": "Discovered the project uses API Gateway for centralized token verification, so HS256 is viable in this specific architecture",

  "new_insight_id": "ins-20260412-p6q7r8",

  "lesson": {
    "abstract": "JWT algorithm choice depends not just on architecture pattern (monolith vs microservice) but also on verification topology (who verifies tokens)",
    "generates_new_sample": true
  }
}
```

---

## 9. Skill Implementation

### 9.1 File Structure

```
self-tune/
├── skills/
│   └── self-tune/
│       ├── SKILL.md                  # Main skill definition
│       ├── sidecar-prompt.md         # Sidecar subagent prompt template
│       ├── retrospective-prompt.md   # Retrospective subagent prompt template
│       ├── correction-prompt.md      # Correction subagent prompt template
│       └── output-schema.md          # Output format definitions
├── cli/                              # Phase 2
├── server/                           # Phase 3
├── install.sh                        # One-command installer
└── README.md
```

### 9.2 SKILL.md Structure

```markdown
---
name: self-tune
description: >
  Use when the agent just received a user correction,
  when the agent is about to retry an approach for the
  third time, or when the agent realizes a previous
  solution was wrong. Do not use when the task is
  proceeding smoothly without notable friction.
---

# Self-tune: Experience Distillation

## Trigger Criteria
[Specific conditions — see Section 4.3]

## When NOT to Invoke
[Exclusion conditions — see Section 4.3]

## Cost Assessment Gate
[Quick pre-dispatch check — see Section 4.4]

## Execution Protocol

### Step 1: Identify Trigger Type
- Sidecar (mid-task turning point detected)
- Retrospective (task just completed with notable friction)
- Correction (discovered previous insight was wrong)

### Step 2: Build Context Package
[Curate minimal context for subagent — see Section 5.2]

### Step 3: Dispatch Subagent
Use Agent tool with run_in_background=true.
Load appropriate prompt template (sidecar/retrospective/correction).

### Step 4: Handle Result
When subagent completes:
- If Reminder candidates generated: briefly notify user, request approval
- Otherwise: silent or one-line summary ("Extracted 2 insights")
- NEVER expand details unless user asks

## Interaction with Other Skills
- Wait for systematic-debugging to conclude before triggering
- Only trigger from main conversation, never from within a subagent
- Do not trigger during an active self-tune cycle
```

### 9.3 Subagent Prompt Template (sidecar-prompt.md)

Core instructions for the reflection subagent:

```markdown
# Self-tune Sidecar Reflection Agent

You are a background agent performing experience extraction.
Your output is written to files only. Keep your work silent.

## Input Context
{task_description}
{episode_summary}
{project_context}

## Workflow

### 1. Episode Analysis
- What went wrong and why?
- Classify insight_type
- Assess user correction type (genuine_improvement / preference / environmental)
- If preference: reframe as inquiry pattern, NOT a fixed answer

Use the following common failure mode checklist to aid classification:
- **Tunnel vision** (backtrack_failure): Persisting in one direction despite repeated failures — e.g., 5 rounds modifying config when the issue is in Dockerfile
- **Surface-level fix** (reasoning_error): Patching symptoms instead of root cause — e.g., adding null checks instead of tracing why the value is null
- **Shotgun modification** (reasoning_error): Changing code without understanding blast radius — e.g., renaming a function but missing dynamic references
- **Convention blindness** (skill_gap): Ignoring codebase conventions — e.g., creating camelCase files in a kebab-case project, reimplementing existing utilities
- **Tool misuse** (tool_orchestration): Using wrong tools for the task — e.g., guessing file paths with Read instead of using Glob, using Bash for grep instead of Grep tool
- **Over-exploration** (exploration_inefficiency): Collecting information well past the point of sufficiency — e.g., reading 10 files when the answer was in the first one

### 2. Adversarial Reflection
Generate two opposing attributions with confidence scores.
Only proceed with high-confidence insights.

### 3. Optimal Decision Point Detection
- Find T_actual (when correct judgment was actually made)
- Backtrack to find T_optimal (earliest possible correct judgment)
- Identify missed signals between T_optimal and T_actual

### 4. Generalization Ladder
Generate L1/L2/L3 formulations. Default to L1.

### 5. SFT Sample Construction

#### Query Design
- Reflect real agentic distribution: assistant ↔ tool interactions dominate
- Preserve valuable long context (1000-3000 tokens)
- Include prior failed attempts (key training signal)
- Trim tool results intelligently (keep decision-relevant portions)
- Cut query at T_optimal (for Type 2) or T_actual (for Type 1)

#### Prompt Internalization (for Type 1)
User hints are the learning source but must NOT appear in query.
Transform user wisdom into autonomous model reasoning in the CoT.

#### CoT Requirements
- Every conclusion MUST anchor to specific tool output (evidence-chained)
- Externalize decision trees when multiple approaches exist
- Use expect-observe-revise pattern when predictions fail
- FORBIDDEN: post-hoc rationalization, content-free hedging, over-explaining basics

#### Response
The ideal action given the improved CoT reasoning.

### 6. Reminder Generation (if applicable)
For env_specific or high-frequency issues, generate CLAUDE.md-compatible rule.
Write to ~/.self-tune/data/reminders/ (pending_approval status).

### 7. Contradiction Check
Read ~/.self-tune/data/index.json first.
Only load specific insight files if potential conflict detected.
If contradiction found: generate Correction record.

### 8. Persist All Outputs
Write to ~/.self-tune/data/ following schema definitions.
Update index.json.
```

---

## 10. Reminder Lifecycle

### 10.1 Generation and Approval

```
Subagent generates → writes to reminders/ as pending_approval
    → Main conversation notifies user (one sentence)
    → User approves or rejects
    → If approved: write to CLAUDE.md under "## Self-tune Reminders"
    → If rejected: mark as rejected, do not persist
```

### 10.2 Ongoing Validation

Each active Reminder tracks:
- `validation_count`: Times a subsequent interaction confirmed its value
- `contradiction_count`: Times a subsequent interaction contradicted it
- `confidence`: Dynamically adjusted based on validation/contradiction ratio

### 10.3 Cleanup

- Reminders with 0 validations after 30 days → suggest removal
- Reminders with contradiction_count > validation_count → proactively suggest correction
- Maximum 20 active reminders per CLAUDE.md section (prevent bloat)

---

## 11. CLI Tool (Phase 2)

### 11.1 Commands

```
self-tune stats                   # Local data statistics
self-tune list [--type] [--status]   # Browse data
self-tune show <id>               # View single record
self-tune export                  # Export data
  --format sft|dpo|jsonl           # Output format
  --filter "score>0.7"             # Quality filter
self-tune upload                  # Upload to central server
  --dry-run                        # Preview upload content
self-tune validate                # Batch quality validation
self-tune remind --sync           # Sync pending reminders
self-tune remind --prune          # Clean expired/low-confidence reminders
self-tune gc                      # Clean up old data
```

### 11.2 Technology

Python CLI with `click` + `rich`. Package installable via `pip install self-tune`.

### 11.3 Quality Scoring Engine

Offline batch validation applying:
- Adversarial reflection score check
- Generalization level risk assessment
- CoT anti-pattern detection (rule-based)
- Cross-entry consistency check (contradiction detection within dataset)
- Composite quality score (0.0-1.0)

---

## 12. Central Server (Phase 3)

### 12.1 Technology

FastAPI + PostgreSQL + MinIO (file storage) + Celery + Redis (async pipeline) + React (dashboard).

### 12.2 Ingest API

```
POST /api/v1/upload     # Receive data from self-tune-cli
POST /api/v1/feedback   # Receive reminder retain/delete signals
```

### 12.3 Analysis Pipeline

```
Stage 1: Deduplication and normalization
Stage 2: Strong model re-evaluation (Opus/GPT-4o)
  - Independent assessment of each Insight
  - Verify generalization reasonableness
  - Verify CoT is genuinely better than original trajectory
  - Output server_score
  - Future: cross-model voting (multiple models independently evaluate,
    majority agreement increases confidence, disagreement flags for review)
Stage 3: Cross-user aggregation
  - Similar insight clustering
  - Conflict detection and classification
  - Cross-user validation counting
  - User credibility scoring (based on correction consistency,
    cross-user corroboration rate, and correction survival rate —
    used as sampling weight, not as user gatekeeping)
Stage 4: Desensitization
  - Remove internal API addresses, key fragments, internal domains
  - Replace project-specific paths and naming
  - Preserve code logic structure
Stage 5: Dataset construction
  - Quality-filtered selection
  - Domain-balanced sampling
  - Curriculum learning ordering: arrange training data by difficulty
    (preference→inquiry first, then prompt internalization,
    then path compression/tool orchestration, then backtrack/anticipation)
  - Export: SFT format + DPO format
  - Data card (distribution stats, quality metrics, domain coverage)
```

### 12.4 Quality Dashboard

- Data volume and growth trends
- Quality score distribution
- insight_type distribution
- Tech stack / language coverage heatmap
- Cross-user conflict rate
- Per-record detail view with query + CoT + response comparison

---

## 13. Installation and Distribution

### 13.1 Phase 1 Installation (Skill only)

```bash
git clone git@internal:ai/self-tune.git
cd self-tune && ./install.sh
```

`install.sh` performs:
1. Create `~/.self-tune/data/` directory structure
2. Symlink skill to `~/.claude/skills/self-tune`
3. Generate default `config.yaml`
4. Print success message

### 13.2 Phase 2 Installation (+ CLI)

```bash
pip install self-tune     # or: pip install -e . for development
```

Auto-completes Skill installation + CLI tool setup.

### 13.3 Configuration

```yaml
# ~/.self-tune/config.yaml
version: 1

server:
  url: null                     # Central server URL (Phase 3)
  api_key: null
  auto_upload: false

trigger:
  min_retry_count: 3            # Minimum retries before considering "notable friction"
  auto_remind: true             # Auto-generate Reminder candidates

reminder:
  target: claude_md
  claude_md_section: "## Self-tune Reminders"
  max_active_reminders: 20

retention:
  max_local_samples: 1000
  auto_cleanup_days: 90
```

---

## 14. Phased Delivery

### Phase 1 (v1): Skill + Local Storage
- Self-tune Skill with auto-trigger via description matching
- Subagent-based reflection (sidecar + retrospective + correction)
- All 6 SFT data types
- Dual output: SFT data + CLAUDE.md reminders
- Adversarial reflection + generalization ladder + CoT quality controls
- Local file-based storage at `~/.self-tune/`
- Data accumulation period (collect, don't train yet)

### Phase 2: + CLI Tool
- `self-tune-cli` for batch management
- Quality scoring engine
- Multi-format export (SFT / DPO / JSONL)
- Successful trajectory reinforcement (expert trajectory detection)
- Generational isolation tagging
- Offline data analysis (conflict rate, validation pass rate)

### Phase 3: + Central Server
- Multi-user data aggregation and deduplication
- Strong model re-evaluation
- Cross-user clustering and conflict resolution
- Desensitization pipeline
- Quality dashboard
- Production SFT dataset export
