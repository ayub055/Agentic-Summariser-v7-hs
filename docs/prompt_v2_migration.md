# Prompt v2 Migration — Product Terminology Rules

## Problem

The LLM prompts (`BUREAU_REVIEW_PROMPT`, `COMBINED_EXECUTIVE_PROMPT`) had no rules distinguishing between:
- **CC Utilization** — credit card outstanding as % of credit limit (revolving credit)
- **PL Outstanding** — personal loan balance remaining as % of sanctioned amount (repayment progress)

Without explicit terminology rules, the LLM could narrate PL outstanding as "PL utilization", which is semantically wrong — Personal Loans are term loans with no revolving credit facility. The word "utilization" only applies to Credit Cards.

## What Changed in v2

New file: `config/prompts_v2_bureau.py` containing two prompt variants:

| Prompt | Variable Name |
|---|---|
| Bureau Review | `BUREAU_REVIEW_PROMPT_V2` |
| Combined Executive Summary | `COMBINED_EXECUTIVE_PROMPT_V2` |

### Additions over v1

1. **PRODUCT TERMINOLOGY RULES block** — added to both prompts, explicitly states:
   - "Utilization" = CC only (revolving credit)
   - "Outstanding %" = PL and all term loans (repayment progress)
   - Never conflate the two metrics
2. **Portfolio Overview paragraph** — now instructs LLM to narrate PL outstanding as repayment progress
3. **Behavioral Insights paragraph** — examples updated to show correct CC vs PL phrasing

### What was NOT changed
- No Python logic changes needed — the data labels fed to the LLM already say "PL Outstanding" (in `report_summary_chain.py`)
- No template changes — HTML templates already use "PL Outstanding %"
- No threshold changes — `config/thresholds.py` constants are unchanged

---

## Migration Steps

### Step 1 — Update the import in `pipeline/reports/report_summary_chain.py`

Open `pipeline/reports/report_summary_chain.py` (line 27-28). Change:

```python
# Before
from config.prompts import (
    ...
    BUREAU_REVIEW_PROMPT,
    COMBINED_EXECUTIVE_PROMPT,
    ...
)

# After
from config.prompts_v2_bureau import (
    BUREAU_REVIEW_PROMPT_V2 as BUREAU_REVIEW_PROMPT,
    COMBINED_EXECUTIVE_PROMPT_V2 as COMBINED_EXECUTIVE_PROMPT,
)
```

Using `as` aliases means no other code in the file needs to change — the variable names used at line 954 and line 1006 remain `BUREAU_REVIEW_PROMPT` and `COMBINED_EXECUTIVE_PROMPT`.

### Step 2 — Regenerate a test report

```bash
/Users/ayyoob/anaconda3/bin/python -c "
from tools.combined_report import generate_combined_report_pdf
generate_combined_report_pdf(698167220)
"
```

### Step 3 — Verify the generated narrative

Check the generated HTML for correct terminology:

```bash
# Should find "outstanding" near PL references, never "utilization"
grep -i "PL.*util\|personal.*util" reports/combined_report_html_version/combined_698167220_report.html

# Should find CC utilization correctly used
grep -i "CC.*util\|credit card.*util" reports/combined_report_html_version/combined_698167220_report.html
```

Expected: first grep returns no matches (PL never called utilization). Second grep returns matches with correct CC utilization phrasing.

### Step 4 — (Optional) Retire v1 prompts

Once v2 is validated across multiple customers, you can move the original prompts in `config/prompts.py` to commented-out blocks (like the existing commented variants at lines 228-320) and import v2 as the primary.

---

## Rollback

To revert, simply change the import back to:

```python
from config.prompts import (
    BUREAU_REVIEW_PROMPT,
    COMBINED_EXECUTIVE_PROMPT,
)
```

No other files are affected.

---

## Files Reference

| File | Role |
|---|---|
| `config/prompts_v2_bureau.py` | New v2 prompt variants (this change) |
| `config/prompts.py` | Original v1 prompts (unchanged, kept as fallback) |
| `pipeline/reports/report_summary_chain.py:27` | Import location to swap |
| `pipeline/reports/report_summary_chain.py:954` | Bureau prompt usage |
| `pipeline/reports/report_summary_chain.py:1006` | Combined prompt usage |
