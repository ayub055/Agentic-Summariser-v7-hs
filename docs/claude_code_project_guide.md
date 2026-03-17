# Claude Code CLI — Project Development Guide

> **Scope:** Complete reference for using Claude Code CLI to build, maintain, and scale real-world projects
> **Context:** All examples reference this project — a LangChain-based Transaction Intelligence System with Ollama LLMs, 28 intent types, PDF report generation, and bureau data analysis
> **Audience:** Developers who want to extract maximum value from Claude Code as a development partner

---

## Table of Contents

1. [Core Functionalities](#1-core-functionalities)
2. [Project-Specific Examples & Use Cases](#2-project-specific-examples--use-cases)
3. [Context Window Optimization](#3-context-window-optimization)
4. [Repeatable Task Patterns](#4-repeatable-task-patterns)
5. [Multi-Subagent Patterns](#5-multi-subagent-patterns)
6. [CLAUDE.md & Memory System](#6-claudemd--memory-system)
7. [Hooks System — Workflow Automation](#7-hooks-system--workflow-automation)
8. [MCP Server Integration](#8-mcp-server-integration)
9. [Permission Modes & Security](#9-permission-modes--security)
10. [Skills System — Reusable Workflows](#10-skills-system--reusable-workflows)
11. [Session Management & Worktrees](#11-session-management--worktrees)
12. [CLI Flags & Scripting](#12-cli-flags--scripting)
13. [IDE Integration](#13-ide-integration)
14. [Cost Management](#14-cost-management)
15. [Advanced Patterns & Pro Tips](#15-advanced-patterns--pro-tips)

---

## 1. Core Functionalities

Everything you can do with Claude Code CLI when working on a project.

### 1.1 Interactive Session

```bash
# Start fresh session in project root
cd ~/Desktop/Projects/langchain_agentic_v7_hs
claude

# Start with initial prompt
claude "Explain the pipeline architecture in this project"

# Named session (for later resume)
claude -n "hallucination-fixes"
```

### 1.2 File Operations

| Operation | How | Example |
|-----------|-----|---------|
| **Read files** | `@file` reference or ask | `@config/prompts.py explain the BUREAU_REVIEW_PROMPT` |
| **Edit files** | Describe the change | `"Fix the CC utilization bug in report_summary_chain.py line 685"` |
| **Create files** | Ask to create | `"Create a new output_validator.py in utils/"` |
| **Search files** | Describe what you need | `"Find all files that use SUMMARY_MODEL"` |
| **Rename/move** | Ask to refactor | `"Rename get_total_income to calculate_total_income across the project"` |

### 1.3 Code Understanding

```
# Architecture exploration
"Trace the full execution flow when a user asks 'show spending for customer 100384958'"

# Dependency analysis
"What modules import from config/thresholds.py and how do they use the constants?"

# Pattern identification
"Find all places where LLM output is used without validation"
```

### 1.4 Code Generation & Modification

```
# Bug fix with context
"The bureau summary hallucinates CC utilization when no credit card exists.
 The bug is in _build_bureau_data_summary() — 0.0 passes the 'is not None' check.
 Fix it to check for actual CC presence."

# Feature addition
"Add a post-generation validator that checks summaries against source data
 before returning them. Use the pattern from docs/hallucination_fix_plan.md Section C."

# Refactoring
"Refactor the QueryPlanner to support both deterministic and LLM-based planning
 as described in docs/agentic_architecture_plan.md"
```

### 1.5 Testing & Debugging

```
# Run tests
"Run the test suite and fix any failures"

# Debug specific issue
"The event detector flags 'GOSIPURA RENT' as a SIP investment.
 Debug why and fix the keyword matching in tools/event_detector.py"

# Generate tests
"Write unit tests for the normalize_category function in pipeline/core/planner.py"
```

### 1.6 Git Operations

```
# Commit with context
/commit

# Create PR
"Create a PR for the hallucination fixes on the current branch"

# Review changes
"Review all uncommitted changes and summarize what they do"
```

### 1.7 Documentation

```
# Generate docs from code
"Document the complete data flow for bureau report generation"

# Update existing docs
"Update TECHNICAL_OVERVIEW.md to reflect the new hybrid planner"
```

### 1.8 Web Research

```
# Check library docs
"What's the latest API for ChatOllama streaming in LangChain?"

# Find solutions
"How does DeepSeek-R1 handle structured output? Check their docs."
```

### 1.9 Bash Commands

```
# Direct bash execution
! pip install langchain-ollama
! python main.py
! ollama list

# Or prefix with description
"Run the batch report generator for customer 698167220"
```

### 1.10 Slash Commands Reference

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `/compact` | Compress conversation context | When hitting context limits mid-task |
| `/clear` | Fresh conversation | Starting a new unrelated task |
| `/resume` | Resume previous session | Continuing yesterday's work |
| `/cost` | View token usage | Budget monitoring |
| `/context` | Check context usage | Before starting a large task |
| `/init` | Generate CLAUDE.md | First time setting up a project |
| `/model` | Switch model | Switching between Opus/Sonnet/Haiku |
| `/effort` | Set reasoning depth | Quick tasks (low) vs complex refactors (high) |
| `/memory` | Browse loaded context | Debugging why Claude misses project rules |
| `/doctor` | Diagnose issues | When something isn't working right |
| `/vim` | Toggle vim mode | If you prefer vim keybindings |
| `/add-dir` | Add working directory | When you need access to a sibling project |
| `!command` | Run bash directly | Quick terminal commands |
| `@file` | Reference file | Pointing Claude to specific code |

---

## 2. Project-Specific Examples & Use Cases

### 2.1 Architecture Exploration

**Understanding the pipeline flow:**
```
"Trace what happens when a user submits 'show bureau report for customer 100384958'.
 Start from app.py → orchestrator → intent parser → planner → executor → report builder.
 Show me the exact function calls and data transformations at each step."
```

**Finding cross-cutting concerns:**
```
"Find every place in the codebase where an LLM is called.
 For each call, tell me: which model is used, what prompt template,
 whether the output is validated, and whether there's error handling."
```

**Dependency mapping:**
```
"Create a dependency graph showing which modules import from which.
 Focus on the pipeline/ directory. Identify circular dependencies if any."
```

### 2.2 Bug Fixing

**Hallucination bug (real example from this project):**
```
"In pipeline/reports/report_summary_chain.py, the _build_bureau_data_summary()
 method at line 685 checks 'if cc_utilization is not None' but cc_utilization
 can be 0.0 (float) when there's no credit card, because the feature extractor
 defaults to 0.0 instead of None.

 Fix this by:
 1. Checking the has_cc flag from tradeline features instead
 2. Only including CC utilization in the prompt when has_cc is True
 3. Adding an explicit 'NO CREDIT CARD DATA' marker when has_cc is False"
```

**Event detector false positives (real example):**
```
"The keyword rules in tools/event_detector.py match substrings without
 word boundaries. 'SIP' matches 'GOSIPURA', 'LIC' matches 'LICENCE'.

 Fix all 6 keyword rules in KEYWORD_RULES (line 69-137) to:
 1. Add \\b word boundaries to all patterns
 2. Add negative keyword lists to exclude known false positives
 3. The self-transfer detector matches 'SELF PAY RENT' — add exclusion patterns"
```

### 2.3 Feature Implementation

**Adding output validation (from hallucination plan):**
```
"Implement the OutputValidator class described in docs/hallucination_fix_plan.md
 Section C. It should:

 1. Live in utils/output_validator.py
 2. Take the LLM summary text and the source data dict
 3. Check that no numbers appear in the summary that aren't in the source data
 4. Check that no product types are mentioned that aren't in the data
 5. Flag any sentences that mention 'credit card' when has_cc is False
 6. Return a ValidationResult with pass/fail and list of violations

 Wire it into report_summary_chain.py after each generate_*_review() call."
```

**Adding hybrid agentic planning (from architecture plan):**
```
"Implement Phase 1 of docs/agentic_architecture_plan.md:

 1. Create the ToolDescription dataclass in a new schemas/tool_description.py
 2. Build the TOOL_REGISTRY dict in config/tool_registry.py from existing tools
 3. Add the should_use_agentic_planning() decision gate in pipeline/core/planner.py
 4. Keep all existing deterministic behavior unchanged — the agentic path should
    only activate for UNKNOWN intents initially"
```

### 2.4 Prompt Engineering

**Rewriting prompts to reduce hallucination:**
```
"Rewrite the CUSTOMER_REVIEW_PROMPT in config/prompts.py following the
 anti-hallucination principles in docs/hallucination_fix_plan.md:

 1. Remove all example values (e.g., '₹72,000', 'primary score 35/100')
 2. Replace 'EXAMPLE' markers with 'TEMPLATE' markers using {placeholders}
 3. Add explicit instruction: 'ONLY mention products and metrics that appear
    in the DATA section below. If a data field is marked ABSENT, do not
    mention it at all.'
 4. Add structural constraint: 'Output EXACTLY 2 paragraphs. No bullet points.'
 5. Keep the prompt under 500 tokens total."
```

### 2.5 Batch Operations

**Generating reports for multiple customers:**
```
"Run batch_reports.py for customers [100384958, 698167220, 445566778].
 After each run, check the generated HTML report for:
 - CC utilization mentioned when no CC exists
 - Any numbers not present in the source data
 - Prompt example text appearing in the output
 Report findings for each customer."
```

**Refactoring across files:**
```
"Rename SUMMARY_MODEL to REPORT_MODEL across the entire codebase.
 This should update: config/settings.py, any imports, and all references
 in pipeline/reports/ files. Don't change PARSER_MODEL or EXPLAINER_MODEL."
```

### 2.6 Code Review

```
"Review all changes in the current git diff. For each modified file:
 1. Check for potential bugs or regressions
 2. Verify error handling is adequate
 3. Check that no sensitive data (API keys, customer data) is exposed
 4. Verify the changes align with the existing code style"
```

### 2.7 Data Analysis

```
"Read data/dpd_data.csv and data/transactions.csv.
 Tell me:
 - How many unique customers are in each dataset?
 - How many customers appear in both?
 - What's the date range of transaction data?
 - What are all unique transaction categories?"
```

---

## 3. Context Window Optimization

The context window is your most valuable resource. Every token loaded reduces space for Claude's reasoning. Here's how to manage it.

### 3.1 Understanding Context Budget

```
Total context: ~200K tokens

Permanent overhead (loaded every turn):
├── System prompt:        ~2-5K tokens
├── CLAUDE.md files:      ~1-3K tokens (keep under 200 lines)
├── Auto memory:          ~0.5-1K tokens (first 200 lines of MEMORY.md)
├── MCP tool definitions: ~0.5-2K per server
└── Skill descriptions:   ~2% of context

Available for conversation: ~180-190K tokens
```

### 3.2 The CLAUDE.md Budget Rule

**Problem:** A 500-line CLAUDE.md is loaded on every single turn. Over a 50-turn conversation, that's 25K+ tokens wasted on repeated context.

**Solution: Layer your instructions.**

```
CLAUDE.md (keep under 200 lines)
├── Project name, tech stack, critical commands
├── @imports for detail files
└── Link to .claude/rules/ for path-specific rules

.claude/rules/
├── testing.md        → loaded only when touching test files
├── reports.md        → loaded only when touching pipeline/reports/
├── prompts.md        → loaded only when editing config/prompts.py
└── security.md       → loaded only when touching auth/secrets
```

**For this project, an optimal CLAUDE.md:**

```markdown
# Transaction Intelligence System

Python + LangChain + Ollama (local LLMs). Financial analysis pipeline.
No cloud API keys — all inference runs locally via Ollama.

## Tech Stack
- Python 3.11, LangChain, Jinja2 templates
- Ollama models: mistral (parser), llama3.2 (explainer), deepseek-r1:14b (summary)
- Data: CSV files in data/ (transactions.csv, dpd_data.csv)

## Key Commands
```bash
python main.py                    # Interactive CLI
python app.py                     # Streamlit UI
python batch_reports.py           # Batch report generation
ollama list                       # Check loaded models
```

## Architecture
5-stage pipeline: IntentParser → QueryPlanner → ToolExecutor → InsightExtractor → Explainer
Reports: Customer (banking), Bureau (credit), Combined (both)
All risk scoring is deterministic Python — LLM only narrates.

## Critical Rules
- NEVER use cloud LLM APIs — Ollama only
- All thresholds in config/thresholds.py — do not hardcode
- strip_think() required for all DeepSeek-R1 output
- Report prompts must not contain example values (hallucination risk)

## Active Plans
@docs/hallucination_fix_plan.md
@docs/agentic_architecture_plan.md
@docs/model_selection_guide.md
```

### 3.3 Conversation Hygiene Techniques

#### Use `/compact` Proactively
```
# Don't wait for auto-compaction at 95%
# Compact after completing a logical phase of work

Phase 1: Explored codebase, found bugs → /compact
Phase 2: Fixed 3 bugs → /compact
Phase 3: Wrote tests → /compact
```

#### Use `/clear` Between Unrelated Tasks
```
# Task 1: Fix hallucination bugs
claude -n "hallucination-fixes"
# ... work ...
# Done. Session saved.

# Task 2: Add new API endpoint (unrelated)
claude -n "api-endpoint"  # Fresh context, no old baggage
```

#### Use `@file` Instead of Pasting Code
```
# BAD — wastes context with pasted code
"Here's my prompts.py file: [500 lines of code]. Fix the bureau prompt."

# GOOD — Claude reads only what's needed
"Fix the BUREAU_REVIEW_PROMPT in @config/prompts.py to remove example values"
```

#### Use Subagents for Exploration
```
# BAD — reading 10 files fills up main context
"Read all files in pipeline/reports/ and summarize each one"

# GOOD — subagent explores, returns only the summary
# Claude automatically uses Explore subagent for this
"What does each file in pipeline/reports/ do? Give me a one-line summary of each."
```

### 3.4 Context-Efficient Prompting

#### Be Specific, Not Exploratory
```
# BAD — forces Claude to read many files to understand
"Make the system better"

# GOOD — Claude knows exactly what to read and change
"In pipeline/reports/report_summary_chain.py, the _build_bureau_data_summary()
 method includes CC utilization even when has_cc is False. Fix lines 683-689
 to check has_cc before including utilization data."
```

#### Reference Documentation You've Already Created
```
# BAD — re-explaining everything
"I want to fix hallucinations. The system has these problems: [re-explains everything]"

# GOOD — reference existing docs
"Implement Phase 1 of @docs/hallucination_fix_plan.md — the prompt-level fixes A1-A5"
```

#### Batch Related Changes
```
# BAD — 5 separate prompts for related changes
"Fix the keyword rules" → "Now fix the self-transfer detector" → "Now fix round trips"

# GOOD — one prompt for related changes
"Fix all event detector issues described in @docs/hallucination_fix_plan.md Section D:
 D1 through D7. Apply all fixes to tools/event_detector.py."
```

### 3.5 Model Selection for Context Efficiency

```bash
# Quick exploration — use Haiku (cheaper, keeps less context)
claude --model haiku "List all Python files that import from config/"

# Implementation — use Sonnet (balanced)
claude --model sonnet "Implement the OutputValidator class"

# Complex architectural reasoning — use Opus
claude --model opus "Design the hybrid agentic planning system"
```

### 3.6 Effort Level Management

```bash
# Simple tasks — low effort (less reasoning tokens consumed)
claude --effort low "Add a docstring to the QueryPlanner class"

# Standard development — medium (default)
claude --effort medium "Fix the CC utilization bug"

# Complex multi-file refactoring — high effort
claude --effort high "Implement the full hybrid planner from the architecture plan"
```

---

## 4. Repeatable Task Patterns

### 4.1 The `/loop` Command — Scheduled Repetition

```bash
# Monitor test results every 5 minutes during refactoring
/loop 5m "Run python -m pytest tests/ and report any failures"

# Watch for model availability
/loop 30s "Run 'ollama list' and tell me when deepseek-r1:14b appears"

# Continuous integration check
/loop 10m "Check if the batch report generator produces valid output for customer 698167220"
```

### 4.2 Custom Skills for Repeatable Workflows

Create `.claude/skills/validate-reports/SKILL.md`:

```markdown
---
name: validate-reports
description: Validate generated reports for hallucination artifacts
argument-hint: [customer_id]
user-invocable: true
allowed-tools: Read, Grep, Bash
---

Validate the most recently generated report for customer $ARGUMENTS[0].

Steps:
1. Find the report HTML in reports/ directory for this customer
2. Check for these hallucination patterns:
   - CC utilization mentioned when customer has no credit cards
   - Exact phrases from prompt templates appearing in output
   - Numbers not present in the source data
   - Product types mentioned that aren't in the data
3. Report: PASS or FAIL with specific violations found

Output format:
- Customer: [id]
- Report type: [banking/bureau/combined]
- Status: PASS/FAIL
- Violations: [list]
```

**Usage:**
```bash
/validate-reports 698167220
/validate-reports 100384958
```

### 4.3 Hooks for Automatic Quality Checks

`.claude/settings.json`:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python -c \"import ast; ast.parse(open('$FILE').read())\" 2>&1 || echo 'Syntax error detected'",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

This automatically validates Python syntax after every file edit.

### 4.4 Session Resume for Ongoing Work

```bash
# Day 1: Start hallucination fixes
claude -n "hallucination-phase1"
# ... implement fixes A1-A3 ...
# End of day. Exit.

# Day 2: Continue where you left off
claude -r "hallucination-phase1"
# Claude has full context of what was done yesterday
"Continue with fixes A4 and A5 from the hallucination plan"

# Day 3: Resume again
claude -r "hallucination-phase1"
"Now implement Section B — the data pipeline fixes"
```

### 4.5 Batch Operations with `/batch`

```bash
# Apply the same change across multiple files
/batch "In every Python file under pipeline/, add proper error handling
 to all ChatOllama calls — wrap in try/except with graceful fallback"

# Standardize imports
/batch "In all files under tools/, change 'from config.settings import *'
 to explicit named imports"

# Add type hints
/batch "Add type hints to all public methods in pipeline/core/"
```

### 4.6 Print Mode for Scripted Checks

```bash
# Run as part of a shell script or CI pipeline
claude -p "Check config/prompts.py for any hardcoded example values
 like specific rupee amounts or scores. Return JSON with findings." \
 --output-format json

# Chain multiple checks
claude -p "Does tools/event_detector.py use word boundaries in all regex patterns?" \
 --max-turns 3

# Budget-limited validation
claude -p --max-budget-usd 0.50 "Review the last 5 commits for security issues"
```

### 4.7 Git Pre-commit Validation

`.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Check for hallucination-prone patterns in prompts
PROMPT_FILES=$(git diff --cached --name-only | grep "prompts.py")
if [ -n "$PROMPT_FILES" ]; then
  claude -p "Check if config/prompts.py contains any hardcoded example values
   (like specific rupee amounts ₹xx,xxx or specific scores xx/100).
   Return 'PASS' if clean, or 'FAIL: [details]' if problems found." \
   --max-turns 2 --max-budget-usd 0.10
fi
```

---

## 5. Multi-Subagent Patterns

Subagents are isolated Claude instances with their own context, tools, and models. They are the key to scaling complex work without blowing up your main context.

### 5.1 When to Use Subagents

| Scenario | Why Subagent | Example |
|----------|-------------|---------|
| **Heavy file reading** | Keeps main context clean | "Analyze all 15 files in pipeline/" |
| **Parallel research** | Multiple investigations at once | "Check 3 different approaches" |
| **Isolated testing** | Test output doesn't pollute context | "Run full test suite" |
| **Specialized analysis** | Different model/tools needed | "Security audit with read-only access" |
| **Long-running operations** | Main session stays responsive | "Generate and validate all reports" |

### 5.2 Built-in Subagent Types

#### Explore Agent (Fast, Read-Only)
```
# Claude automatically uses this for codebase exploration
"Find all files that handle bureau data processing"

# You can be explicit about thoroughness
"Do a very thorough search for every place where CC utilization is calculated or used"
```

**Best for:**
- Finding files, classes, functions
- Understanding code structure
- Tracing data flow
- Quick answers about the codebase

#### Plan Agent (Read-Only, Architectural)
```
# Used in plan mode
"Design the implementation approach for the hybrid agentic planner"

# Explores codebase and produces implementation plan
# Cannot edit files — safe for exploration
```

**Best for:**
- Implementation planning
- Architecture design
- Trade-off analysis

#### General-Purpose Agent (Full Access)
```
# Used for complex multi-step tasks
"Implement all 7 event detector fixes from Section D of the hallucination plan"

# Can read, write, edit, run bash
# Independent context from main session
```

**Best for:**
- Multi-file implementations
- Complex refactoring
- Tasks that generate lots of output

### 5.3 Custom Subagent Definitions

Create `.claude/agents/report-validator.md`:

```markdown
---
name: report-validator
description: Validates generated HTML reports against source data for hallucination artifacts. Use after generating any report.
tools: Read, Grep, Glob, Bash
disallowedTools: Write, Edit
model: sonnet
maxTurns: 20
---

You are a report validation specialist. Your job is to verify that
generated HTML reports contain ONLY information present in the source data.

When invoked with a customer ID:

1. Read the source data:
   - data/transactions.csv for banking data
   - data/dpd_data.csv for bureau data

2. Read the generated report HTML from reports/

3. Cross-reference every claim in the report:
   - Every number must trace back to source data
   - Every product mention must exist in the data
   - CC utilization should ONLY appear if customer has credit cards
   - No prompt template text should appear in output

4. Output a structured validation report:
   - PASS/FAIL status
   - List of specific violations with line references
   - Confidence score (0-100)
```

Create `.claude/agents/prompt-auditor.md`:

```markdown
---
name: prompt-auditor
description: Audits LLM prompts for hallucination risk factors. Use when modifying prompts.
tools: Read, Grep, Glob
disallowedTools: Write, Edit, Bash
model: haiku
maxTurns: 10
---

You audit LLM prompt templates for patterns that cause hallucination.

Check for:
1. Hardcoded example values (specific numbers, names, scores)
2. Ambiguous instructions ("provide insights", "be comprehensive")
3. Missing absence instructions (what to do when data is missing)
4. Structural ambiguity (paragraph count, format not specified)
5. Prompt injection vulnerabilities (user data in prompt without sanitization)

Rate each prompt: LOW / MEDIUM / HIGH / CRITICAL risk.
Provide specific fix recommendations for each finding.
```

### 5.4 Parallel Subagent Execution

Claude can spawn multiple subagents simultaneously for independent tasks:

```
"I need three things done in parallel:
 1. Audit all prompts in config/prompts.py for hallucination risk
 2. Find all event detector false positive patterns in tools/event_detector.py
 3. Map every LLM call in the codebase and check if output is validated"
```

Claude will launch 3 Explore agents simultaneously, each investigating independently.

### 5.5 Worktree-Isolated Subagents

For subagents that need to make code changes without affecting your working tree:

```markdown
---
name: experimental-refactor
description: Try experimental refactoring approaches in isolation
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
isolation: worktree
maxTurns: 30
---

You work in an isolated git worktree. Make experimental changes freely.
If the changes work, they can be merged. If not, the worktree is discarded.
```

### 5.6 Background Subagents

```
# Run long tasks in background while you continue working
"In the background, generate reports for all customers in the test set
 and validate each one. Notify me when done."
```

Claude will run the agent in the background and notify you on completion. You can continue working on other things.

### 5.7 Chained Subagent Pattern

```
"First, use an explore agent to find all hallucination-prone code paths.
 Then, use a general-purpose agent to fix each one.
 Finally, use the report-validator agent to verify the fixes work."
```

### 5.8 Agent Teams (Advanced)

For large projects, you can configure teams of agents that coordinate:

```bash
# CLI definition of multiple agents
claude --agents '{
  "researcher": {
    "description": "Research codebase patterns",
    "tools": ["Read", "Grep", "Glob"],
    "model": "haiku"
  },
  "implementer": {
    "description": "Implement changes",
    "tools": ["Read", "Edit", "Write", "Bash"],
    "model": "sonnet"
  },
  "reviewer": {
    "description": "Review code changes",
    "tools": ["Read", "Grep", "Bash"],
    "model": "sonnet"
  }
}'
```

---

## 6. CLAUDE.md & Memory System

### 6.1 CLAUDE.md File Hierarchy

```
Precedence (highest to lowest):

1. Managed Policy    /Library/Application Support/ClaudeCode/CLAUDE.md  (org-wide)
2. Project           ./CLAUDE.md or ./.claude/CLAUDE.md                 (git-shared)
3. User              ~/.claude/CLAUDE.md                                (personal)
```

### 6.2 Optimal CLAUDE.md for This Project

```markdown
# Transaction Intelligence System (LangChain Agentic v7)

## Stack
Python 3.11 | LangChain | Ollama (local LLMs) | Jinja2 | Streamlit

## Models
- Parser: mistral (7B) — JSON intent extraction
- Explainer: llama3.2 (3B) — streaming chat
- Summary: deepseek-r1:14b — report generation (strip_think() required)

## Commands
```bash
python main.py                          # CLI interface
python app.py                           # Streamlit UI
python batch_reports.py                 # Batch reports
python -m pytest tests/                 # Run tests
ollama list                             # Check models
```

## Architecture
5-stage pipeline: Parse → Plan → Execute → Insights → Explain
All risk scoring is deterministic Python. LLMs only narrate.
28 intent types in schemas/intent.py → mapped in config/intents.py

## Rules
- No cloud LLM APIs — Ollama only, all local
- Thresholds in config/thresholds.py only — never hardcode
- All DeepSeek output must pass through strip_think()
- Report prompts must NOT contain example values (causes hallucination)
- Test with: 698167220 (has bureau+banking), 100384958 (bureau only)

## Active Plans
@docs/hallucination_fix_plan.md
@docs/agentic_architecture_plan.md
```

### 6.3 Path-Specific Rules with .claude/rules/

`.claude/rules/reports.md`:
```markdown
---
paths:
  - "pipeline/reports/**"
  - "config/prompts.py"
  - "templates/**"
---

# Report Generation Rules

- Every LLM summary must be validated against source data before use
- Prompts must not contain hardcoded example values
- Always check has_cc/has_pl flags before mentioning products
- Combined reports feed LLM output into LLM — double-validate
- Use strip_think() for all DeepSeek-R1 output
- Report HTML must be self-contained (inline CSS, no external deps)
```

`.claude/rules/event-detection.md`:
```markdown
---
paths:
  - "tools/event_detector.py"
---

# Event Detection Rules

- All regex patterns MUST use \b word boundaries
- Every keyword rule needs negative exclusion patterns
- Self-transfer threshold: 40% is too low, use 60%
- Round-trip name matching: require 8+ chars, not 6
- All thresholds come from config/thresholds.py
```

### 6.4 Auto Memory System

Claude automatically maintains memories across sessions in:
```
~/.claude/projects/<project-hash>/memory/
├── MEMORY.md          # Index (first 200 lines loaded each session)
├── debugging.md       # Debug solutions discovered
├── patterns.md        # Code patterns identified
└── decisions.md       # Architectural decisions made
```

**Trigger memory saves:**
```
"Remember: always use deepseek-r1:14b for summary model, never llama3.2"
"Remember: customer 698167220 is the best test case — has both banking and bureau data"
"Remember: the CC utilization bug was in _build_bureau_data_summary() lines 683-689"
```

**Query memories:**
```
"What do you remember about the hallucination fixes we discussed?"
/memory  # Browse all memory files
```

### 6.5 Importing External Context

In CLAUDE.md or any rules file:
```markdown
# Import project docs
@docs/hallucination_fix_plan.md
@docs/agentic_architecture_plan.md
@docs/model_selection_guide.md

# Import README
@README.md

# Import config for reference
@config/settings.py
```

**Limitation:** Max 5 import hops. Keep imported files concise.

---

## 7. Hooks System — Workflow Automation

Hooks let you run code automatically in response to Claude's actions.

### 7.1 Hook Event Lifecycle

```
User types prompt
  └→ UserPromptSubmit hook fires
      └→ Claude processes, decides to edit a file
          └→ PreToolUse (Edit) hook fires
              └→ Tool executes
                  └→ PostToolUse (Edit) hook fires
                      └→ Claude finishes response
                          └→ Stop hook fires
```

### 7.2 Practical Hook Examples for This Project

#### Auto-lint Python files after edit

`.claude/settings.json`:
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "FILE=$(echo $CLAUDE_TOOL_INPUT | python3 -c \"import sys,json; print(json.load(sys.stdin).get('file_path',''))\") && [ -n \"$FILE\" ] && [ \"${FILE##*.}\" = 'py' ] && python3 -m py_compile \"$FILE\" 2>&1 || true",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

#### Block edits to critical config files

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "FILE=$(echo $CLAUDE_TOOL_INPUT | python3 -c \"import sys,json; print(json.load(sys.stdin).get('file_path',''))\") && [[ \"$FILE\" == *'.env'* || \"$FILE\" == *'credentials'* ]] && { echo 'BLOCKED: Cannot modify secrets files' >&2; exit 2; } || exit 0"
          }
        ]
      }
    ]
  }
}
```

#### Desktop notification when Claude finishes

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "osascript -e 'display notification \"Claude Code finished its task\" with title \"Claude Code\"'"
          }
        ]
      }
    ]
  }
}
```

#### Auto-validate after report generation

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "CMD=$(echo $CLAUDE_TOOL_INPUT | python3 -c \"import sys,json; print(json.load(sys.stdin).get('command',''))\") && [[ \"$CMD\" == *'batch_reports'* ]] && echo 'REMINDER: Validate generated reports for hallucination artifacts' || true"
          }
        ]
      }
    ]
  }
}
```

#### Inject context after compaction

```json
{
  "hooks": {
    "PostCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo 'CONTEXT REMINDER: Working on hallucination fixes. Current phase: prompt rewrites in config/prompts.py. Test customer: 698167220.'"
          }
        ]
      }
    ]
  }
}
```

### 7.3 Hook Exit Codes

| Exit Code | Behavior |
|-----------|----------|
| `0` | Allow — continue normally |
| `2` | Block — prevent the tool from executing |
| Other | Log warning to stderr, continue |

### 7.4 Prompt-Based Hooks (LLM Validation)

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Review the changes just made. Did they introduce any hardcoded example values in prompt templates? Respond with {\"ok\": true} if clean or {\"ok\": false, \"reason\": \"details\"} if problems found.",
            "model": "haiku"
          }
        ]
      }
    ]
  }
}
```

---

## 8. MCP Server Integration

MCP (Model Context Protocol) extends Claude with external tool access.

### 8.1 Adding MCP Servers

```bash
# GitHub integration
claude mcp add --transport http github https://api.github.com/mcp

# Filesystem server (for additional directories)
claude mcp add --transport stdio files -- npx -y @anthropic/mcp-filesystem ~/data

# Database access
claude mcp add --transport stdio postgres -- npx -y @anthropic/mcp-postgres \
  --connection-string "postgresql://localhost:5432/analytics"

# From JSON config
claude mcp add-json ollama '{"type":"http","url":"http://localhost:11434/mcp"}'
```

### 8.2 Project-Level MCP Config

`.mcp.json` (committed to git, shared with team):
```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.github.com/mcp"
    },
    "project-data": {
      "type": "stdio",
      "command": "python",
      "args": ["mcp_server.py"],
      "env": {
        "DATA_DIR": "${PROJECT_ROOT}/data"
      }
    }
  }
}
```

### 8.3 MCP for This Project — Practical Uses

```bash
# GitHub: Track issues and PRs
claude mcp add --transport http github https://api.github.com/mcp
# Then: "Create an issue for the CC utilization hallucination bug"
# Then: "List open PRs and their review status"

# Slack: Notify team about deployments
claude mcp add --transport http slack https://mcp.slack.com
# Then: "Post to #deployments: 'Hallucination fix v1 deployed to staging'"
```

### 8.4 MCP Resources as Context

```
# Reference GitHub issues directly
"Analyze @github:issue://42 and implement the fix"

# Reference database schemas
"Show me the schema at @postgres:schema://transactions and suggest indexes"
```

### 8.5 Managing MCP Servers

```bash
claude mcp list              # Show all configured servers
claude mcp get github        # Details for specific server
claude mcp remove github     # Remove server
/mcp                         # In-session management and auth
```

---

## 9. Permission Modes & Security

### 9.1 Permission Modes

| Mode | Behavior | Best For |
|------|----------|----------|
| `default` | Prompts for each tool use | Normal development |
| `plan` | Read-only, no edits allowed | Architecture exploration |
| `acceptEdits` | Auto-accepts file edits, prompts for bash | Active coding sessions |
| `dontAsk` | Auto-denies unless pre-approved | Strict safety requirements |
| `bypassPermissions` | Skips all checks | Isolated containers/VMs only |

### 9.2 Permission Rules for This Project

`.claude/settings.json`:
```json
{
  "permissions": {
    "defaultMode": "default",
    "allow": [
      "Read",
      "Glob",
      "Grep",
      "Edit(pipeline/**)",
      "Edit(config/**)",
      "Edit(tools/**)",
      "Edit(utils/**)",
      "Edit(schemas/**)",
      "Bash(python main.py*)",
      "Bash(python -m pytest*)",
      "Bash(python batch_reports.py*)",
      "Bash(ollama *)",
      "Bash(pip install *)",
      "Bash(git status)",
      "Bash(git diff*)",
      "Bash(git log*)",
      "Bash(git add *)",
      "Bash(git commit *)"
    ],
    "deny": [
      "Edit(.env*)",
      "Edit(data/*.csv)",
      "Bash(git push*)",
      "Bash(rm -rf*)",
      "Bash(pip uninstall*)"
    ]
  }
}
```

### 9.3 Path-Based Permission Patterns

```json
{
  "allow": [
    "Read(./*.json)",         "# Relative to cwd",
    "Edit(/src/**/*.ts)",     "# Relative to project root",
    "Read(~/shared/*)",       "# Relative to home",
    "Read(//etc/hosts)"       "# Absolute path"
  ]
}
```

### 9.4 Switching Modes Mid-Session

```
# Keyboard shortcut
Shift+Tab → Cycle through permission modes

# Or use plan mode for exploration
claude --permission-mode plan "Explore the report generation architecture"
```

---

## 10. Skills System — Reusable Workflows

Skills are parameterized prompt templates that you can invoke with `/skill-name`.

### 10.1 Creating Project-Specific Skills

`.claude/skills/validate-report/SKILL.md`:
```markdown
---
name: validate-report
description: Validate a generated report for hallucination artifacts
argument-hint: [customer_id] [report_type]
user-invocable: true
allowed-tools: Read, Grep, Glob, Bash
model: sonnet
---

Validate the $0 report for customer $1.

## Steps
1. Read the source data for customer $1:
   - data/transactions.csv (filter by cust_id = $1)
   - data/dpd_data.csv (filter by crn = $1)

2. Read the generated report:
   - reports/${0}_${1}_report.html

3. Cross-reference every factual claim:
   - Numbers must match source data exactly
   - Product mentions must exist in data
   - CC utilization only if has_cc is true
   - No prompt template text in output

4. Output validation result as structured report.
```

**Usage:**
```
/validate-report customer 698167220
/validate-report bureau 100384958
/validate-report combined 698167220
```

### 10.2 Audit Skill

`.claude/skills/audit-prompts/SKILL.md`:
```markdown
---
name: audit-prompts
description: Audit all LLM prompts for hallucination risk
user-invocable: true
allowed-tools: Read, Grep
model: haiku
---

Audit all prompt templates in config/prompts.py for hallucination risk factors.

Check each prompt for:
1. Hardcoded example values (₹ amounts, scores, percentages)
2. Ambiguous instructions ("provide insights", "be comprehensive")
3. Missing absence handling (what to do when data fields are empty)
4. Structural ambiguity (no paragraph count, format unspecified)
5. Data injection risk (user data without sanitization)

Rate each prompt: LOW / MEDIUM / HIGH / CRITICAL

Output a table:
| Prompt Name | Risk Level | Issues Found | Fix Priority |
```

**Usage:**
```
/audit-prompts
```

### 10.3 Built-in Skills

| Skill | Usage | What It Does |
|-------|-------|-------------|
| `/simplify` | `/simplify focus on the planner` | Reviews code for quality issues, suggests simplifications |
| `/batch` | `/batch add type hints to all tools/` | Parallel refactoring across multiple files |
| `/loop` | `/loop 5m run tests` | Repeat a task on schedule |
| `/commit` | `/commit` | Smart git commit with message generation |

### 10.4 Skill Context Modes

```yaml
# Fork mode — runs in subagent (doesn't affect main context)
context: fork
agent: Explore  # Uses Explore subagent

# Inline mode — runs in main conversation
context: inline  # Default
```

---

## 11. Session Management & Worktrees

### 11.1 Session Workflow

```bash
# Start named session for a feature
claude -n "fix-hallucinations"

# Work throughout the day...
# Exit when done for the day

# Next day: resume exactly where you left off
claude -r "fix-hallucinations"

# Or use interactive picker
claude --resume
# ↑/↓ to navigate, P to preview, Enter to select

# Continue most recent session
claude -c
```

### 11.2 Session Picker Features

| Key | Action |
|-----|--------|
| `↑ / ↓` | Navigate sessions |
| `Enter` | Resume selected session |
| `P` | Preview session contents |
| `R` | Rename session |
| `/` | Search/filter sessions |
| `A` | Toggle scope (current dir / all projects) |
| `B` | Filter by git branch |
| `Esc` | Exit picker |

### 11.3 Worktrees for Parallel Development

```bash
# Create isolated worktree for experimental changes
claude -w experiment-new-planner

# Claude creates:
# .claude/worktrees/experiment-new-planner/
# Branch: worktree-experiment-new-planner

# Make changes freely — won't affect main working tree
"Try implementing the agentic planner with a completely different approach"

# If changes are good: merge
git merge worktree-experiment-new-planner

# If changes are bad: discard
git worktree remove .claude/worktrees/experiment-new-planner
```

### 11.4 Parallel Sessions in Multiple Terminals

```bash
# Terminal 1: Work on hallucination fixes
claude -n "hallucination-fixes" -w hallucination

# Terminal 2: Work on agentic architecture (simultaneously!)
claude -n "agentic-planner" -w agentic

# Terminal 3: Run validation
claude -n "validation" --permission-mode plan
```

### 11.5 Resume from PR

```bash
# Pick up work from a specific PR
claude --from-pr 42
claude --from-pr https://github.com/owner/repo/pull/42

# Claude reads the PR context and continues from there
```

---

## 12. CLI Flags & Scripting

### 12.1 Non-Interactive (Print) Mode

```bash
# One-shot query, output only
claude -p "How many intent types are defined in schemas/intent.py?"

# With structured output
claude -p --output-format json "List all Python files in pipeline/core/"

# With JSON schema validation
claude -p --json-schema '{
  "type": "object",
  "properties": {
    "files": {"type": "array", "items": {"type": "string"}},
    "count": {"type": "integer"}
  }
}' "List all tool files in tools/ directory"

# Streaming JSON (for real-time processing)
claude -p --output-format stream-json "Analyze the orchestrator module"
```

### 12.2 Budget & Turn Limits

```bash
# Limit spending
claude -p --max-budget-usd 1.00 "Full code review of pipeline/"

# Limit turns (prevent infinite loops)
claude -p --max-turns 5 "Fix the import error in main.py"

# Combined
claude -p --max-budget-usd 0.50 --max-turns 3 "Quick syntax check on config/"
```

### 12.3 System Prompt Customization

```bash
# Replace system prompt entirely
claude --system-prompt "You are a Python security auditor. Only check for vulnerabilities."

# Append to system prompt
claude --append-system-prompt "Always suggest test cases for any code changes."

# From file
claude --append-system-prompt-file ./review-guidelines.txt
```

### 12.4 Shell Script Integration

```bash
#!/bin/bash
# automated_review.sh — Run after each PR

PR_NUMBER=$1
BRANCH=$(git branch --show-current)

# Step 1: Review code changes
REVIEW=$(claude -p --max-budget-usd 1.00 --output-format json \
  "Review all changes on branch $BRANCH compared to main.
   Return JSON: {\"issues\": [...], \"severity\": \"low|medium|high\", \"approved\": bool}")

# Step 2: Check for hallucination patterns
HALLUCINATION_CHECK=$(claude -p --max-budget-usd 0.50 \
  "Check if any prompt templates in config/prompts.py contain hardcoded example values.")

# Step 3: Post results
echo "Review: $REVIEW"
echo "Hallucination check: $HALLUCINATION_CHECK"
```

### 12.5 Piping Input

```bash
# Pipe file content
cat config/prompts.py | claude -p "Audit this for hallucination risk"

# Pipe command output
python batch_reports.py 2>&1 | claude -p "Analyze these errors and suggest fixes"

# Pipe git diff
git diff | claude -p "Review these changes for bugs"
```

### 12.6 Multiple Working Directories

```bash
# Add sibling projects for cross-reference
claude --add-dir ../shared-config ../common-utils

# Or use /add-dir in session
/add-dir ../data-pipeline
```

---

## 13. IDE Integration

### 13.1 VS Code Extension

**Features available in VS Code:**
- Sidebar panel with prompt input
- `@file` and `@folder` references from file tree
- Terminal output inclusion
- Git integration (commits, PRs from IDE)
- Background task monitoring
- Clickable file references in output (e.g., `config/prompts.py:162`)

**Key shortcuts:**
- `Cmd+Shift+P` → "Claude Code: Start New Session"
- `Cmd+Shift+P` → "Claude Code: Resume Session"
- Select code → Right-click → "Ask Claude about this"

### 13.2 File References in VS Code

When Claude outputs file references, they become clickable links:
```
The bug is in [report_summary_chain.py:685](pipeline/reports/report_summary_chain.py#L685)
```

Click to jump directly to the line in your editor.

### 13.3 Image & Screenshot Support

```
# Paste screenshot directly
Ctrl+V / Cmd+V (when an image is in clipboard)

# Reference image file
@reports/screenshot.png "What's wrong with this report layout?"
```

---

## 14. Cost Management

### 14.1 Understanding Costs

```
Cost factors (highest to lowest impact):
1. Model choice:  Opus >> Sonnet >> Haiku
2. Context size:  Larger CLAUDE.md = more tokens per turn
3. Thinking:      Extended thinking adds overhead
4. Tool calls:    Each tool invocation costs input+output tokens
5. MCP servers:   Tool definitions loaded every turn
```

### 14.2 Cost Optimization Strategies

| Strategy | Savings | How |
|----------|---------|-----|
| Use Haiku for exploration | ~10x vs Opus | `claude --model haiku "Find all uses of..."` |
| Lower effort for simple tasks | ~2-3x | `claude --effort low "Add a comment to..."` |
| Keep CLAUDE.md concise | ~5-10% per session | Under 200 lines, use @imports |
| Use subagents for research | Variable | Keeps main context lean |
| Compact proactively | Prevents reprocessing | `/compact` after each phase |
| Use print mode for scripts | No session overhead | `claude -p "quick check"` |
| Set budget limits | Hard cap | `--max-budget-usd 2.00` |
| Disable unused MCP servers | ~0.5-2K tokens/turn saved | Remove servers you don't use |

### 14.3 Monitoring Usage

```bash
# In-session cost check
/cost

# Context usage
/context

# Verbose mode (shows token counts)
claude --verbose
```

---

## 15. Advanced Patterns & Pro Tips

### 15.1 The Phased Development Pattern

For large features, structure work in phases with context boundaries:

```bash
# Phase 1: Research & Plan (read-only, cheap)
claude --permission-mode plan --model sonnet -n "feature-plan"
"Analyze the codebase and create an implementation plan for [feature]"
# Exit after plan is created

# Phase 2: Core Implementation (full access)
claude --model sonnet -n "feature-impl"
"Implement the plan from @docs/feature_plan.md — Phase 1 only"
# /compact after each sub-phase

# Phase 3: Testing (bash-heavy)
claude --model haiku -n "feature-tests"
"Run the test suite, fix failures, verify the feature works"

# Phase 4: Review (read-only)
claude --permission-mode plan --model sonnet -n "feature-review"
"Review all changes on this branch for bugs, security issues, and style"
```

### 15.2 The Documentation-Driven Pattern

Write a plan doc first, then reference it in all implementation sessions:

```
# Session 1: Create the plan
"Create a detailed implementation plan for fixing hallucinations.
 Save it to docs/hallucination_fix_plan.md"

# Session 2: Implement (reference the plan)
"Implement Section A of @docs/hallucination_fix_plan.md"

# Session 3: Continue (same plan, fresh context)
"Implement Section B of @docs/hallucination_fix_plan.md"
```

This is exactly what we've been doing in this project — the three docs serve as persistent context that survives session boundaries.

### 15.3 The Exploratory Coding Pattern

Use worktrees to try different approaches safely:

```bash
# Approach A: LangChain-based planner
claude -w approach-a -n "langchain-planner"
"Implement the agentic planner using LangChain's AgentExecutor"

# Approach B: Custom planner (parallel terminal)
claude -w approach-b -n "custom-planner"
"Implement the agentic planner with a custom planning loop"

# Compare results, merge the winner
git diff worktree-approach-a..worktree-approach-b
```

### 15.4 Rewind & Checkpoint Recovery

```
# Made a mistake? Rewind to before it happened
Esc+Esc → Opens checkpoint picker
         → Select the point before the mistake
         → "Restore" to undo all changes since then

# Or "Summarize" to keep current state but inject earlier context
```

### 15.5 External Editor Integration

```
# Write a complex prompt in your editor, then submit
Ctrl+G → Opens prompt in $EDITOR (vim, code, etc.)
       → Write your detailed multi-line prompt
       → Save and close → prompt is submitted
```

### 15.6 Bash Mode for Quick Commands

```
# Prefix with ! for instant bash execution
! git status
! python -c "from data.loader import get_transactions_df; print(len(get_transactions_df()))"
! ollama list
! wc -l config/prompts.py

# Output is added to conversation context for Claude to reference
```

### 15.7 The PR-Driven Workflow

```bash
# Create branch and work
git checkout -b fix/hallucination-cc-util
claude -n "cc-util-fix"
"Fix the CC utilization hallucination bug described in @docs/hallucination_fix_plan.md B2"

# Commit and push
/commit
! git push -u origin fix/hallucination-cc-util

# Create PR with Claude
"Create a PR for this branch. Title: 'Fix CC utilization hallucination in bureau summaries'
 Description should reference the hallucination fix plan."

# Later: Resume from PR to address review comments
claude --from-pr 42
"Address the review comments on this PR"
```

### 15.8 Environment Variables for Customization

```bash
# Set in your shell profile (~/.zshrc or ~/.bashrc)

# Default effort level
export CLAUDE_CODE_EFFORT_LEVEL=medium

# Disable auto-memory if you prefer manual control
export CLAUDE_CODE_DISABLE_AUTO_MEMORY=0

# Custom compaction threshold
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=90  # Compact earlier

# Enable prompt suggestions
export CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=true

# MCP timeout (for slow servers)
export MCP_TIMEOUT=15000
```

### 15.9 The `/init` Bootstrap

When setting up Claude Code for a new project:

```bash
cd your-project
claude
/init

# Claude analyzes your codebase and generates an initial CLAUDE.md with:
# - Project description
# - Tech stack detection
# - Key file identification
# - Build/test commands
# - Architecture overview
```

### 15.10 Keyboard Shortcuts Quick Reference

| Shortcut | Action |
|----------|--------|
| `Ctrl+C` | Cancel current operation |
| `Ctrl+D` | Exit Claude Code |
| `Ctrl+G` | Open prompt in external editor |
| `Ctrl+L` | Clear screen |
| `Ctrl+B` | Background current task |
| `Ctrl+T` | Toggle task list |
| `Shift+Tab` | Cycle permission modes |
| `Option+P` / `Alt+P` | Switch model |
| `Option+T` / `Alt+T` | Toggle extended thinking |
| `Esc+Esc` | Rewind / checkpoint picker |
| `!` | Bash mode (direct command execution) |
| `@` | File/folder reference |
| `?` | Show all shortcuts |

### 15.11 Debug Mode

```bash
# Full debug output
claude --debug

# Filter debug categories
claude --debug "api,mcp"

# Exclude noisy categories
claude --debug "!statsig,!file"

# Session diagnostics
/doctor

# Debug current session issues
/debug "high memory usage"
/debug "MCP server not connecting"
```

### 15.12 Remote Sessions

```bash
# Start a remote session (accessible from claude.ai)
claude --remote "Working on hallucination fixes"

# Connect to remote session from another machine
claude --teleport

# Remote control (interactive)
claude --remote-control "Transaction Intelligence System"
```

### 15.13 Multi-Project Workflows

```bash
# Add sibling project directories
claude --add-dir ../data-pipeline ../shared-schemas

# Or mid-session
/add-dir ../common-utils

# Now Claude can read/search across all three directories
"Find how the transaction schema is defined in @../shared-schemas/"
```

### 15.14 The Managed Policy Pattern (Teams/Enterprise)

For organizations standardizing Claude Code usage:

```json
// /Library/Application Support/ClaudeCode/settings.json (macOS)
{
  "permissions": {
    "defaultMode": "default",
    "deny": [
      "Bash(git push --force*)",
      "Edit(.env*)",
      "Bash(rm -rf*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/usr/local/bin/claude-policy-check.sh"
          }
        ]
      }
    ]
  }
}
```

This enforces organization-wide policies that individual developers cannot override.

---

## Appendix A: Quick Command Cheat Sheet

```bash
# === Session Management ===
claude                              # New session
claude -n "name"                    # Named session
claude -c                           # Continue last session
claude -r "name"                    # Resume by name
claude --resume                     # Interactive picker

# === Model & Performance ===
claude --model opus|sonnet|haiku    # Select model
claude --effort low|medium|high     # Reasoning depth

# === Permissions ===
claude --permission-mode plan       # Read-only exploration
claude --permission-mode acceptEdits # Auto-accept edits

# === Scripting ===
claude -p "query"                   # Print mode (non-interactive)
claude -p --output-format json      # JSON output
claude -p --max-budget-usd 1.00    # Budget limit
claude -p --max-turns 5            # Turn limit

# === Worktrees ===
claude -w feature-name              # Isolated worktree

# === MCP ===
claude mcp list                     # List servers
claude mcp add --transport http name url  # Add server

# === In-Session ===
/compact                            # Compress context
/clear                              # Fresh start
/cost                               # Check spending
/context                            # Check context usage
/memory                             # Browse memories
/init                               # Generate CLAUDE.md
@file.py                            # Reference file
! bash command                      # Run bash
```

## Appendix B: File Structure for Claude Code Configuration

```
project-root/
├── CLAUDE.md                           # Main project instructions (< 200 lines)
├── .mcp.json                           # MCP server configs (git-shared)
├── .claude/
│   ├── CLAUDE.md                       # Alternative location for project instructions
│   ├── settings.json                   # Project settings (git-shared)
│   ├── settings.local.json             # Local overrides (gitignored)
│   ├── rules/
│   │   ├── reports.md                  # Rules for pipeline/reports/**
│   │   ├── event-detection.md          # Rules for tools/event_detector.py
│   │   ├── prompts.md                  # Rules for config/prompts.py
│   │   └── security.md                 # Security rules (all paths)
│   ├── agents/
│   │   ├── report-validator.md         # Custom validation agent
│   │   ├── prompt-auditor.md           # Prompt audit agent
│   │   └── security-reviewer.md        # Security review agent
│   ├── skills/
│   │   ├── validate-report/
│   │   │   └── SKILL.md               # Report validation skill
│   │   ├── audit-prompts/
│   │   │   └── SKILL.md               # Prompt audit skill
│   │   └── generate-test-data/
│   │       └── SKILL.md               # Test data generation skill
│   └── worktrees/                      # Auto-created worktree directories
│       ├── experiment-a/
│       └── experiment-b/
│
├── ~/.claude/                          # User-level (all projects)
│   ├── CLAUDE.md                       # Personal global instructions
│   ├── settings.json                   # Personal settings
│   ├── keybindings.json                # Custom key bindings
│   ├── rules/
│   │   └── preferences.md             # Personal coding preferences
│   ├── agents/
│   │   └── my-helper.md               # Personal custom agent
│   ├── skills/
│   │   └── my-workflow/
│   │       └── SKILL.md               # Personal skill
│   └── projects/
│       └── <project-hash>/
│           └── memory/
│               ├── MEMORY.md           # Auto-memory index
│               ├── debugging.md        # Debug notes
│               └── patterns.md         # Discovered patterns
```

---

*Guide authored for the Transaction Intelligence System (LangChain Agentic v7 HS) — March 2026*

*Built with practical experience from developing: hallucination fix plans, agentic architecture designs, model selection guides, and multi-module Python pipeline systems using Claude Code CLI.*
