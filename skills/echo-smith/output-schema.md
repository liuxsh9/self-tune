# Echo-smith Output Schema

> This schema is generated from `cli/echo_smith/models.py`. If in doubt, models.py is the source of truth.

All outputs are JSON files written to `~/.echo-smith/data/`.

## File Locations

- Traces: `~/.echo-smith/data/traces/{trace-id}.json`
- Insights: `~/.echo-smith/data/insights/{insight-id}.json`
- SFT Samples: `~/.echo-smith/data/samples/{sft-id}.json`
- Reminders: `~/.echo-smith/data/reminders/{rem-id}.json`
- Corrections: `~/.echo-smith/data/corrections/{cor-id}.json`

## ID Format

`{type_prefix}-{YYYYMMDD}-{random_6_hex}`

Prefixes: `trace`, `ins`, `sft`, `rem`, `cor`

Example: `ins-20260410-a3f2c1`

## Enum Reference

| Enum | Values |
|------|--------|
| `InsightType` | `skill_gap` `knowledge_gap` `reasoning_error` `exploration_inefficiency` `tool_orchestration` `backtrack_failure` `preference_probe` `env_specific` |
| `InsightStatus` | `active` `superseded` `archived` |
| `SFTType` | `user_prompt_internalization` `exploration_compression` `error_correction` `preference_to_inquiry` `backtrack_decision` `tool_orchestration` |
| `CorrectionType` | `genuine_improvement` `stylistic_preference` `factual_error` |
| `CorrectionAction` | `supersede` `amend` `retract` |
| `ReminderStatus` | `pending_approval` `approved` `active` `expired` `rejected` |
| `ReminderScope` | `global` `project` `language` |
| `TriggerMode` | `auto` `manual` `scheduled` `sidecar` `retrospective` `user_correction` |
| `TaskOutcome` | `success` `success_after_correction` `partial` `failure` `abandoned` |
| `GeneralizationLevel` | `L1` `L2` `L3` |
| `AdversarialVerdict` | `high_confidence` `moderate` `contested` |

## Trace JSON Structure

```json
{
  "id": "trace-YYYYMMDD-XXXXXX",
  "created_at": "ISO8601",
  "source": "claude-code",
  "model": "claude-sonnet-4-5",
  "trigger": "auto|manual|scheduled|sidecar|retrospective|user_correction",
  "task_description": "Description of the task",
  "task_outcome": "success|success_after_correction|partial|failure|abandoned",
  "project_context": {
    "language": "python",
    "framework": "fastapi",
    "repo": "my-repo"
  },
  "episodes": ["ins-YYYYMMDD-XXXXXX"],
  "conversation_snapshot": {
    "segments": [
      {
        "role": "user|assistant|tool",
        "summary": "Brief summary of this turn",
        "name": "tool_name",
        "is_key_signal": true,
        "is_correction": false
      }
    ]
  }
}
```

## Insight JSON Structure

```json
{
  "id": "ins-YYYYMMDD-XXXXXX",
  "trace_id": "trace-YYYYMMDD-XXXXXX",
  "created_at": "ISO8601",
  "insight_type": "skill_gap|knowledge_gap|reasoning_error|exploration_inefficiency|tool_orchestration|backtrack_failure|preference_probe|env_specific",
  "status": "active|superseded|archived",
  "root_cause": {
    "concrete": "Specific description of what went wrong",
    "abstract": "Generalized pattern"
  },
  "user_correction": {
    "type": "genuine_improvement|stylistic_preference|factual_error",
    "description": "What the user said/did"
  },
  "adversarial_reflection": {
    "attribution_a": {"argument": "Why the correction is better...", "confidence": 0.85},
    "attribution_b": {"argument": "Why original was also valid...", "confidence": 0.3},
    "verdict": "high_confidence|moderate|contested"
  },
  "generalization_ladder": {
    "L1": "Most specific formulation",
    "L2": "Moderate generalization",
    "L3": "Most abstract formulation",
    "selected_level": "L1|L2|L3"
  },
  "efficiency_metrics": {
    "actual_rounds": 10,
    "optimal_rounds": 3,
    "wasted_rounds": 7,
    "t_optimal": 2,
    "missed_signals": [{"round": 2, "tool": "Read", "signal": "...", "why_missed": "..."}]
  },
  "independent_value": true,
  "value_rationale": "Why this insight is valuable regardless of task outcome",
  "quality": {"local_score": 0.85, "server_score": null}
}
```

`user_correction` and `efficiency_metrics` are optional (null when absent).

## SFT Sample JSON Structure

```json
{
  "id": "sft-YYYYMMDD-XXXXXX",
  "insight_id": "ins-YYYYMMDD-XXXXXX",
  "created_at": "ISO8601",
  "version": "concrete|abstract",
  "sft_type": "user_prompt_internalization|exploration_compression|error_correction|preference_to_inquiry|backtrack_decision|tool_orchestration",
  "query": {
    "system_context": "System prompt for the scenario",
    "conversation_history": [
      {"role": "user|assistant|tool", "content": "...", "name": "tool_name", "input": "...", "output": "..."}
    ],
    "decision_point": "Description of what the model faces at this moment"
  },
  "cot": "Improved chain-of-thought reasoning",
  "response": "Ideal action/output",
  "quality": {
    "local_score": 0.9,
    "server_score": null,
    "evidence_anchored": true,
    "no_post_hoc_rationalization": true,
    "no_content_free_hedging": true
  },
  "dpo_rejected_available": false,
  "dpo_rejected": null
}
```

When `dpo_rejected_available` is `true`, `dpo_rejected` is populated:

```json
"dpo_rejected_available": true,
"dpo_rejected": {
  "response": "The suboptimal response that was rejected",
  "failure_mode": "Description of why this response is worse"
}
```

## Reminder JSON Structure

```json
{
  "id": "rem-YYYYMMDD-XXXXXX",
  "insight_id": "ins-YYYYMMDD-XXXXXX",
  "created_at": "ISO8601",
  "status": "pending_approval|approved|active|expired|rejected",
  "rule": "Plain-text rule description",
  "claude_md_text": "Markdown-formatted text for CLAUDE.md",
  "lifecycle": {
    "validation_count": 0,
    "contradiction_count": 0,
    "last_validated": null,
    "confidence": 0.7,
    "written_to_claude_md": false,
    "user_approved": false
  },
  "scope": "global|project|language"
}
```

## Correction JSON Structure

```json
{
  "id": "cor-YYYYMMDD-XXXXXX",
  "created_at": "ISO8601",
  "target_type": "insight|sft|reminder",
  "target_id": "ins-YYYYMMDD-XXXXXX",
  "action": "supersede|amend|retract",
  "reason": "Why this correction is being made",
  "new_insight_id": "ins-YYYYMMDD-XXXXXX",
  "lesson": {
    "abstract": "Generalized lesson learned from this correction",
    "generates_new_sample": false
  }
}
```

`new_insight_id` and `lesson` are optional (null when absent).
