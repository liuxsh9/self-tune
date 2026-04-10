# Echo-smith Output Schema

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

## Insight JSON Structure

```json
{
  "id": "ins-YYYYMMDD-XXXXXX",
  "trace_id": "trace-YYYYMMDD-XXXXXX",
  "created_at": "ISO8601",
  "insight_type": "skill_gap|knowledge_gap|reasoning_error|exploration_inefficiency|tool_orchestration|backtrack_failure|preference_probe|env_specific",
  "status": "active",
  "root_cause": {
    "concrete": "Specific description of what went wrong",
    "abstract": "Generalized pattern"
  },
  "user_correction": {
    "type": "genuine_improvement|preference|environmental",
    "description": "What the user said/did"
  },
  "adversarial_reflection": {
    "attribution_a": {"argument": "Why the correction is better...", "confidence": 0.0-1.0},
    "attribution_b": {"argument": "Why original was also valid...", "confidence": 0.0-1.0},
    "verdict": "high_confidence|moderate|contested"
  },
  "generalization_ladder": {
    "L1": "Most specific formulation",
    "L2": "Moderate generalization",
    "L3": "Most abstract formulation",
    "selected_level": "L1"
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
  "quality": {"local_score": 0.0-1.0, "server_score": null}
}
```

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
    "local_score": 0.0-1.0,
    "server_score": null,
    "evidence_anchored": true,
    "no_post_hoc_rationalization": true,
    "no_content_free_hedging": true
  },
  "dpo_rejected_available": false
}
```

## Reminder JSON Structure

```json
{
  "id": "rem-YYYYMMDD-XXXXXX",
  "insight_id": "ins-YYYYMMDD-XXXXXX",
  "created_at": "ISO8601",
  "status": "pending_approval",
  "rule": "Plain-text rule description",
  "claude_md_text": "Markdown-formatted text for CLAUDE.md",
  "lifecycle": {
    "validation_count": 0,
    "contradiction_count": 0,
    "last_validated": null,
    "confidence": 0.0-1.0,
    "written_to_claude_md": false,
    "user_approved": false
  },
  "scope": "global|project|personal"
}
```
