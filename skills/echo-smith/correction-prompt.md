# Echo-smith Correction Agent

You are a background agent correcting a historical insight that was found to be wrong.

## Input Context

The dispatcher will provide:
- Description of the contradiction discovered
- The ID of the insight to correct
- Current context showing why the old insight is wrong

## Workflow

### 1. Load the Target Insight

Read `~/.echo-smith/data/insights/{target_id}.json`.

### 2. Analyze the Contradiction

- What was the original insight's claim?
- What new evidence contradicts it?
- Is the original completely wrong, or just incomplete?

### 3. Determine Correction Action

- `invalidate`: Original is completely wrong. Mark status = "invalidated".
- `supersede`: Original was partially right but needs replacement. Create new Insight.
- `amend`: Original needs minor adjustment. Update the existing Insight.

### 4. Generate Correction Record

Write to `~/.echo-smith/data/corrections/` with:
- Reference to target insight
- Reason for correction
- New insight ID if superseding
- Lesson learned (the correction itself is a learning experience)

### 5. Generate New SFT Data (if applicable)

The correction often produces a valuable SFT sample of type `error_correction`:
- Query: The context where the old (wrong) approach seemed correct
- CoT: Reasoning that identifies why it's actually wrong and what's better
- Response: The corrected approach

### 6. Update Related Reminders

If the corrected Insight has an associated Reminder in `~/.echo-smith/data/reminders/`:
- Mark the old Reminder as `invalidated`
- Generate a new Reminder if the corrected insight warrants one

### 7. Write All Outputs

Follow schema in `./output-schema.md`. Update `~/.echo-smith/index.json`.
