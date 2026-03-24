# Project: Kotak Agentic Reader v7 HS

LangChain-based agentic system for natural language querying over banking transactions and bureau/CIBIL tradeline data. Generates PDF/HTML/Excel reports for credit decisioning.

## Key Principle
**Determinism > Intelligence** — All numbers are computed deterministically. LLMs (local Ollama) are used ONLY for narration/summary. Never trust LLM-generated numbers.

## Python Environment
- **Use:** `/Users/ayyoob/anaconda3/bin/python` (has pandas, langchain, etc.)
- Do NOT use `.venv`, `venv`, or conda envs — they lack dependencies.

## Entry Points
- **CLI:** `python main.py` (interactive query pipeline)
- **Web UI:** `streamlit run app.py` (Kotak-branded interface)
- **Batch:** `python batch_reports.py --crns 698167220 --output reports/batch_output.xlsx`
- **Report generation:** `from tools.combined_report import generate_combined_report_pdf`

## Architecture (5-Stage Pipeline)
```
Query → IntentParser (LLM) → QueryPlanner → ToolExecutor → Insights → Explainer (LLM)
```

## Key Directories
| Directory | Purpose |
|-----------|---------|
| `config/` | Settings, prompts, thresholds, keywords, categories |
| `schemas/` | Pydantic models (CustomerReport, BureauReport, ParsedIntent) |
| `pipeline/core/` | 5-stage orchestrator (parser, planner, executor, explainer) |
| `pipeline/reports/` | Report generation (orchestrator, builder, summary chains) |
| `pipeline/renderers/` | PDF/HTML rendering (Jinja2 templates) |
| `pipeline/extractors/` | Bureau feature extraction from CSV |
| `tools/` | Deterministic analytics (15+ tools) |
| `features/` | Feature vector dataclasses |
| `templates/` | Jinja2 HTML templates (multiple themes) |
| `data/` | Data loader + CSV files |
| `reports/` | Generated output (PDF, HTML, Excel) |

## Data Sources
- `data/rgs.csv` — Banking transactions (TSV)
- `dpd_data.csv` — Bureau DPD tradeline data (TSV, 99 columns)
- `tl_features.csv` — Pre-computed tradeline features (TSV)
- `rg_sal_strings.csv` / `rg_income_strings.csv` — Salary/income algorithm outputs

## LLM Models (Ollama, local only)
- **mistral** — Intent parsing (JSON forced, temp=0)
- **llama3.2** — Explainer, summaries (temp=0, seed=42)
- No cloud API calls.

## Report Generation Flow
```
generate_combined_report_pdf(customer_id)
  → generate_customer_report_pdf() [banking]
  → generate_bureau_report_pdf()   [bureau]
  → generate_combined_executive_summary() [LLM]
  → render_combined_report() [PDF + HTML + Excel]
```

## Centralised Configuration
- **Keywords:** `config/keywords.py` — All narration-matching keywords (salary, EMI, self-transfer, event rules, lender names)
- **Thresholds:** `config/thresholds.py` — All numeric thresholds
- **Prompts:** `config/prompts.py` — All LLM prompt templates
- **Categories:** `config/categories.yaml` — 40+ category taxonomy with aliases

## Testing
- No formal test suite. Test via:
  - `python main.py` (interactive)
  - `from tools.combined_report import generate_combined_report_pdf; generate_combined_report_pdf(698167220)`
  - Test customer: `698167220` (21 transactions in rgs.csv)

## Common Patterns
- Module-level caching: `get_transactions_df()` caches DataFrame globally
- Fail-soft: All LLM/tool calls wrapped in try/except with logger.warning
- Events auto-flow to LLM: `detect_events()` → `format_events_for_prompt()` → LLM prompt
- Scorecard: `compute_scorecard()` — pure deterministic, no LLM
- Checklist: `compute_checklist()` — boolean flags derived from report data

@instructions.md
@TECHNICAL_OVERVIEW.md
