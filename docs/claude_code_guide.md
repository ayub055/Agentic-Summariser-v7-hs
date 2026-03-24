# Claude Code Guide for This Project

> How to use Claude Code efficiently with the Kotak Agentic Reader codebase.

---

## 1. What's Been Set Up

### Directory Structure

```
.claude/
├── settings.json              # Shared project settings (permissions)
├── settings.local.json        # Your local overrides (gitignored)
├── rules/                     # Path-specific rules (auto-loaded)
│   ├── python.md              # Python file conventions
│   ├── templates.md           # HTML template conventions
│   └── config.md              # Config file conventions
└── skills/                    # Custom slash commands
    ├── generate-report/       # /generate-report <customer_id>
    ├── add-checklist-item/    # /add-checklist-item <description>
    ├── add-event-detector/    # /add-event-detector <type> <desc>
    ├── add-keyword-rule/      # /add-keyword-rule <group-name>
    └── research-codebase/     # /research-codebase <topic>

CLAUDE.md                      # Root project instructions (loaded every session)
```

### What Each File Does

| File | Purpose | When Loaded |
|------|---------|-------------|
| `CLAUDE.md` | Project overview, architecture, conventions | Every session start |
| `.claude/rules/python.md` | Python-specific rules | When editing `*.py` files |
| `.claude/rules/templates.md` | Template rules (all themes) | When editing `templates/*.html` |
| `.claude/rules/config.md` | Config conventions | When editing `config/*` |
| `.claude/settings.json` | Pre-approved bash commands | Every session |

---

## 2. How to Maintain the .claude Directory

### settings.json — Permissions

This file pre-approves commands so Claude doesn't ask permission every time:

```json
{
  "permissions": {
    "allow": [
      "Bash(/Users/ayyoob/anaconda3/bin/python *)",  // Run python
      "Bash(ls *)",                                     // List files
      "Bash(grep *)"                                    // Search
    ],
    "deny": [
      "Bash(rm -rf *)",                                 // Never allow
      "Edit(.env*)"                                     // Protect secrets
    ]
  }
}
```

**To add new permissions:** Edit `.claude/settings.json` directly, or tell Claude `/update-config allow npm run test`.

### settings.local.json — Personal Overrides

For machine-specific settings that shouldn't be shared:
```json
{
  "env": {
    "OLLAMA_HOST": "http://localhost:11434"
  }
}
```

### rules/ — Path-Specific Instructions

Rules auto-load when Claude works with matching files. Each rule file has frontmatter:

```markdown
---
paths:
  - "tools/**/*.py"
---

# Tools Rules
- All tools return Dict[str, Any]
- Never call LLM from tools — tools are deterministic
```

**When to add a new rule:** When you find yourself repeating the same instruction for a specific area of the codebase.

### CLAUDE.md — Keep It Focused

The root `CLAUDE.md` should be:
- Under 200 lines (longer = worse adherence)
- Focused on what Claude MUST know for any task
- NOT a full documentation dump — use `@imports` for detail

**Update it when:**
- Architecture changes (new directory, new pipeline stage)
- Key conventions change (new centralised config file)
- You discover Claude keeps making the same mistake

---

## 3. Available Skills (Slash Commands)

### `/generate-report <customer_id> [theme]`
Generates a combined report and tells you where the HTML is.
```
/generate-report 698167220
/generate-report 698167220 emerald
```

### `/add-checklist-item <description>`
Guided workflow to add a new boolean item to the Quick Assessment Checklist.
```
/add-checklist-item "Check if customer has SIP investments"
```

### `/add-event-detector <event-type> <description>`
Guided workflow to add a new transaction event detector — either keyword-based or custom.
```
/add-event-detector cash_withdrawal "Detect large ATM withdrawals"
```

### `/add-keyword-rule <group>`
Add keywords to the centralised keyword config.
```
/add-keyword-rule "LENDER_FRAGMENTS — add new NBFC names"
```

### `/research-codebase <topic>`
Deep research a topic and output findings to `docs/`.
```
/research-codebase "how bureau FOIR is computed end-to-end"
```

---

## 4. Ideas for More Custom Skills

### High Value — Build These Next

| Skill | What It Does | Why Useful |
|-------|-------------|------------|
| `/batch-run <crn-list>` | Run batch report generation for multiple CRNs | Saves typing the batch_reports.py CLI args |
| `/add-bureau-finding` | Add a new deterministic key finding rule | 40+ rules in key_findings.py, common extension point |
| `/add-scorecard-signal` | Add a new RAG signal to the scorecard | Scorecard is the most visible output |
| `/compare-reports <crn1> <crn2>` | Side-by-side comparison of two customer reports | Useful for QA/validation |
| `/validate-output <crn>` | Check a generated report for hallucination signals | Run post-generation validation (amounts exist in input, etc.) |
| `/debug-events <crn>` | Show all detected events with debug info | Helpful when tuning event detector thresholds |

### Medium Value — Nice to Have

| Skill | What It Does |
|-------|-------------|
| `/add-category` | Add a new category to categories.yaml with aliases and keywords |
| `/add-intent` | Add a new intent type to the query pipeline (intents.py + tool mapping) |
| `/explain-pipeline <stage>` | Explain how a specific pipeline stage works with live code refs |
| `/profile-report <crn>` | Time each stage of report generation to find bottlenecks |
| `/update-prompt <prompt-name>` | Guided editing of LLM prompts with before/after diff |
| `/add-template-section` | Add a new section to the HTML template across all themes |

### Hooks You Could Add

```json
// In .claude/settings.json:
{
  "hooks": {
    // Auto-format after edits
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "echo 'File changed: check templates sync'"
      }]
    }],
    // Notify when Claude finishes
    "Notification": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "osascript -e 'display notification \"Claude is done\" with title \"Claude Code\"'"
      }]
    }]
  }
}
```

---

## 5. Tips for Working Efficiently with Claude

### Be Specific About Scope
Instead of: "Fix the reports"
Say: "Fix the checklist in combined_report.html — the FOIR item should show amber when between 40-65%"

### Use Skills for Repetitive Tasks
If you do something more than twice, create a skill for it. Skills are just markdown files — create them manually or ask Claude to create one.

### Let Claude Use Plan Mode for Big Changes
For anything touching 3+ files, let Claude plan first:
- "Plan how to add X" → Claude creates a plan for your approval
- "Implement the plan" → Claude executes

### Reference the Codebase Research Doc
The `docs/codebase_research_plan.md` has prioritised bugs, hallucination fixes, and optimisations. Reference it:
- "Implement V6 from the research doc"
- "Fix the remaining medium bugs from codebase_research_plan.md"

### Parallel Work
When asking for multiple independent changes, tell Claude to run agents in parallel:
- "Fix B7, B8, and B9 from the research doc — run in parallel"

### Memory
Claude automatically remembers things across sessions. You can also:
- "Remember that the theme default is 'original' not 'emerald'"
- "Forget the thing about conda envs"
- Check memory: "What do you remember about this project?"

---

## 6. Project-Specific Workflows

### Adding a New Feature to the Report

1. `/add-event-detector` or `/add-keyword-rule` — if it needs new detection
2. `/add-checklist-item` — if it should appear in the checklist
3. Edit `_build_data_summary()` in `report_summary_chain.py` — if it should feed the LLM
4. `/generate-report 698167220` — verify it works

### Debugging Why Something Doesn't Appear in the Report

1. Check if data exists: `from data.loader import get_transactions_df; df = get_transactions_df(); print(df[df['cust_id'] == 698167220])`
2. Check if detection works: `from tools.event_detector import detect_events; print(detect_events(698167220))`
3. Check if it reaches the template: Look at `render_combined_report_html()` in `combined_report_renderer.py`
4. Check the right template: Default theme is `"original"` → `combined_report_original.html`

### Changing Thresholds

1. Edit `config/thresholds.py` — all thresholds are here
2. No code changes needed — all consumers import from this file
3. Re-generate report to see the effect

---

## 7. File Quick Reference

| When You Want To... | Edit This File |
|---------------------|----------------|
| Add narration keywords | `config/keywords.py` |
| Change detection thresholds | `config/thresholds.py` |
| Change LLM prompts | `config/prompts.py` |
| Add category taxonomy | `config/categories.yaml` |
| Add event detection logic | `tools/event_detector.py` |
| Add checklist items | `pipeline/renderers/combined_report_renderer.py` → `compute_checklist()` |
| Add scorecard signals | `tools/scorecard.py` → `compute_scorecard()` |
| Add bureau key findings | `pipeline/reports/key_findings.py` |
| Change report HTML layout | `templates/combined_report_original.html` (+ other themes) |
| Change what data feeds LLM | `pipeline/reports/report_summary_chain.py` → `_build_data_summary()` |
| Add Excel columns | `tools/excel_exporter.py` → `build_excel_row()` |
| Add a new tool | `tools/` + wire in `config/intents.py` |
| Add query intent | `schemas/intent.py` + `config/intents.py` |
