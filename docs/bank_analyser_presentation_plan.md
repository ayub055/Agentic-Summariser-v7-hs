# Plan — Kotak Bank Analyser Presentation

> **Hand-off document for the next Claude agent.**
> This plan captures the full conversation, decisions, and current state of a `.pptx` presentation built for the Kotak Agentic Reader project. The next agent will work on a related project that contains only the **Bank_Analyser** component — adapt context accordingly where the scope differs.

---

## 1. Project Background

**Kotak Agentic Reader** is a LangChain-based agentic system for hindsighting credit decisions on offers, **first payment defaults (FPDs)**, and **30+ DPD cases**. Goal: identify what went wrong and what to rectify.

### Three failure modes the system diagnoses
1. **Execution gaps** — a policy or sub-component did not fire correctly.
2. **Policy issues** — too harsh, or safe to relax based on observed cohort behaviour.
3. **Income estimation** — under- or over-stated; alternate signals were missed.

### Current operational reality
- 10–20 cases per day handled **manually** by analysts (data pull, aggregation, judgment).
- Slow, inconsistent across analysts, hard to audit.
- This project's ultimate goal: streamline the loop with the agent we built.

### What's already shipped (status as of this conversation)
- Customer + Bureau + Combined **HTML / PDF / Excel** reports.
- **Transaction tagging in-built** for Kotak banking narrations (43-category retrieval-augmented model wired in as a tool).
- Deterministic engine: feature vectors, key findings, scorecard, checklist.
- Agentic base already in place: intent parser (Mistral · JSON), planner, tool registry, audit log — designed to evolve into a full ReAct loop.
- Currently focused on HTML report + Excel creation. Has the skeleton for ReAct-type agent.

### Architecture in one breath
5-stage pipeline: **Intent Parser → Query Planner → Tool Executor → Insight Extractor → Explainer / Narrator.** All LLM inference is local Ollama (no PII egress). Numbers are deterministic; LLM only narrates and plans tool calls.

---

## 2. Presentation Goal & Audience

Build a `.pptx` for a **mixed audience: technical reviewers + C-suite**.
Split: **70% technically rigorous, 30% C-suite framing.**
Slot length: **20–30 minutes** → final size landed at **13 slides**.

### Tone rules (user-stated)
- Professional, no unnecessary text.
- Technical slides must be technically deep with **clear motivation** (a "why this choice" angle).
- Each technical slide should carry an **architecture image** (generic on the main slide, zoomed variants on deep-dives).
- Architecture diagrams must share a visual language across slides.
- Stay **directional** on quantified impact (no hard TAT numbers available yet).
- Frame as **shipped** (HTML/Excel done) — but make ReAct the aspirational story.

---

## 3. Style Constraints

**Primary visual reference (use this):**
`Kotak_Agentic_Reader_Presentation.pptx` — sits at the root of `/Users/ayyoob/Desktop/Projects/langchain_agentic_v7_hs/`. This is the deck produced by the conversation that generated this plan; it already embodies every styling decision documented below, plus the slide-2 60/40 split, the gold-highlighted Transaction Tagger tool, the slide-7 "Why Agentic?" framing, and the cover-card layout. **Open this file first and mirror it slide-for-slide where the scope overlaps.**

**Upstream style anchor (for fallback / cross-check):**
`Transaction_Tagger_Presentation.pptx` (Kotak AI-team standard) — same folder. Use this only to verify chrome details (slide-number position, footer-bar height, divider weight) if `Kotak_Agentic_Reader_Presentation.pptx` is ambiguous.

Do not deviate from these styles.

### Extracted palette
| Token | Hex | Use |
|---|---|---|
| NAVY   | `#1B3A6B` | Primary text / borders / panels |
| BLUE   | `#275BAD` | Secondary accent |
| GOLD   | `#B8860B` | Highlight accent (Transaction Tagger, agentic emphasis) |
| TINT   | `#E8EDF7` | Pale panel fill |
| BORDER | `#CCD3DD` | Dividers, card borders |
| TEXT   | `#556578` | Body copy |
| SUBTLE | `#99A8BB` | Captions, footer text |

### Layout standard for every content slide
- Thin navy strip on left edge (full height) + thin navy strip on top edge (full width).
- Slide number top-right (`NN / 13`, 10 pt, TEXT colour, right-aligned).
- Title: 24 pt **bold NAVY**, left-aligned.
- Hairline BORDER divider under the title.
- Subtitle: 12 pt TEXT under the divider.
- Footer bar: full-width TINT band with a 1 px BORDER top edge, 8 pt TEXT inside.
- Slide dimensions: **16:9 widescreen**, exact EMU: `12188952 × 6858000` (13.33″ × 7.5″).
- Font: **Calibri** throughout.

### Cover slide pattern (slide 1)
- Left dark NAVY panel covering ~35% width.
- Giant 2-letter mark inside (the Transaction Tagger uses `AI`; this deck uses `RG` — adapt for Bank_Analyser, e.g. `BA`).
- Right side: kicker → main title → gold divider → subtitle → 4 stat cards → byline.

---

## 4. Final Slide Structure (13 slides)

| # | Slide | Notes |
|---|---|---|
| 1 | Title / cover | Kotak palette, 4 stat cards (cases/day, failure modes, local LLM, formats shipped) |
| 2 | Context, problem & what we shipped | **60/40 split.** Left 60%: stacked rows "Where we are today" (top) + "What we shipped" (bottom). Right 40%: "Three failure modes we diagnose" — full height. The "shipped" panel explicitly mentions Transaction Tagger as in-built. |
| 3 | Generic system architecture | Full-width architecture PNG. Tool layer header reads "every tool below is invoked by the agent (Tool Executor)". Transaction Tagger sits in the middle of the tool row **highlighted in gold** with italic caption "upstream model · now an agent tool". |
| 4 | Determinism > Intelligence | Bigger arch PNG (9.1M EMU wide) on left + concise gold-accented "MOTIVATION" panel on right with 5 short bullets. Engine box now reads "Agent tool-call results · pure Python"; arrow from LLM up to engine labelled "Agent plan → tool calls". |
| 5 | Bureau Feature Extraction & Key-Findings Engine | Full-width zoomed arch PNG. Severity ladder noted in footer. |
| 6 | Transaction Tagger (upstream) | Big NAVY/GOLD card with mini-stats (43 categories · 35K records · 10M txns/mo · <15 ms). **Hyperlinked** to `Transaction_Tagger_Presentation.pptx` (relative path). Call-to-action below the card. |
| 7 | Why this pipeline needs an agent — Report Orchestration | Bigger arch PNG (9.1M EMU) on left + concise gold "WHY AGENTIC?" panel on right with 5 short bullets + scaling tagline ("More agents. More data sources. More decisions per case. The agent scales linearly — manual review does not."). Title reframed to argue the case rather than describe. |
| 8 | Agentic Foundation — Toward a ReAct Agent | Full-width arch PNG. Today (deterministic intent routing) on top half, Tomorrow (full ReAct loop with reflection) on bottom half. Honest framing: parser + planner + tool registry + audit log already built; gap is dynamic tool selection. |
| 9 | Sample Output — Combined Report (HTML) | Placeholder card with "[Insert annotated Combined Report screenshot]" — user will supply image with yellow highlights later. Sample CRN referenced: `698167220`. |
| 10 | Sample Output — Excel / Checklist / Scorecard | Two side-by-side placeholders. |
| 11 | Impact — Directional | **4 stacked rows** (matches roadmap card style): THROUGHPUT, CONSISTENCY, AUDITABILITY, SCALABILITY. Each row = TINT panel + coloured left accent stripe + kicker + headline + one-line body. |
| 12 | Roadmap | 4 phases stacked: (1) Now, (2) ReAct loop, (3) Offer validation, (4) Active learning. Each row has a numbered badge. |
| 13 | Risks, Guardrails & Ask | 2-column TINT panels: left = guardrails (local Ollama, fail-soft, audit log, deterministic, single-source thresholds), right = risks & ask (concurrency, cache TTL, pilot ask, infra ask, decision ask). |

---

## 5. Architecture Diagrams (PNG assets)

All built with matplotlib using the Kotak palette. Output dir: `/tmp/ppt_assets/`.

| File | Used on slide | Visual story |
|---|---|---|
| `arch_generic.png`     | 3 | Data sources → 5-stage pipeline → 6-tool layer (Transaction Tagger highlighted gold) → config → outputs |
| `arch_determinism.png` | 4 | Raw data flows to BOTH the deterministic engine (gold) AND the LLM layer (blue); LLM plans, engine executes, summary feeds back to LLM for narration |
| `arch_features.png`    | 5 | dpd_data + tl_features → loan-type normalization → feature vectors → aggregator → Key-Findings Engine → 4 finding categories → severity-tagged output |
| `arch_rendering.png`   | 7 | 3 builders → narration chains → rendering layer (Jinja2 / fpdf2 / openpyxl) → HTML / PDF / XLSX |
| `arch_agentic.png`     | 8 | Today (linear: query → parser → planner → tools) vs Tomorrow (ReAct loop: reasoner → action → tool → observation → reflect) |

If the Bank_Analyser project's scope is narrower (banking only, no bureau), drop `arch_features.png` and adjust `arch_generic.png` to remove bureau data sources.

---

## 6. Build Toolchain & Conventions

- **Python**: `/Users/ayyoob/anaconda3/bin/python` (has `python-pptx`, `matplotlib`, `pandas`, `langchain`). Do **not** use `.venv`.
- **Build script lives at** `/tmp/build_deck.py` (single self-contained file). Rebuild with `python /tmp/build_deck.py`.
- **Output**: `Kotak_Agentic_Reader_Presentation.pptx` saved at project root.
- All sizes in EMU (`from pptx.util import Emu`).
- Helper functions in the build script: `add_rect`, `add_text`, `add_chrome` (renders the standard top/left strip + title + divider + subtitle + footer bar — call once per content slide).

### Slide-1 stat-card recipe (reusable pattern)
- TINT-filled rounded rect with BORDER outline, height 749808 EMU, width 1645920 EMU.
- 45720 EMU NAVY left edge strip.
- Stat number: 20 pt NAVY bold.
- Stat label: 8 pt TEXT below the number.

---

## 7. Slide-Wise Changes Already Made (history)

The deck went through these revisions during the conversation. Do not re-litigate unless the user reopens a slide.

| Slide | Final state |
|---|---|
| 2 | Originally 3 columns. Changed to **60/40 split** with stacked rows on the left and "Three failure modes" full-height on the right. **"Transaction tagging in-built for Kotak banking narrations"** added as a bullet under "What we shipped". |
| 3 | Added **Transaction Tagger as a 6th tool** in the deterministic tool layer, **highlighted gold**. Tool-layer header changed to make agent-invocation explicit. |
| 4 | Diagram enlarged to 9.1M EMU. Right panel reduced to **5 concise noun-phrase bullets** ("Auditable line-by-line", etc.). Engine box now reads "Agent tool-call results · pure Python"; arrow from LLM labelled "Agent plan → tool calls"; LLM layer caption includes "Plan" as one of its allowed outputs. |
| 7 | Title reframed from descriptive to argumentative ("Why this pipeline needs an agent — Report Orchestration"). Diagram enlarged to 9.1M EMU. Right "WHY AGENTIC?" panel reduced to 5 short bullets + a closing scaling tagline. Footer tees up slide 8. |
| 11 | Originally 4 cards in a row. Changed to **4 stacked rows** (same panel design as the roadmap slide). |

---

## 8. Pending / Open Items

1. **Slides 9 & 10 screenshots** — user will supply annotated HTML/Excel screenshots with **yellow highlights** marking analyst review points. Placeholders are in place.
2. **Slide 13 "Ask"** — current copy is generic ("pilot ask · infra ask · decision ask"). User may want to tailor to their actual ask before sending the deck up.
3. **Hyperlink path on slide 6** — currently a relative path (`Transaction_Tagger_Presentation.pptx`). Both `.pptx` files must sit in the same folder when opened.
4. **Hard TAT numbers** — directional today. If real numbers come in, slide 11 should be updated.

---

## 9. Adapting for the Bank_Analyser Project (instructions for the next agent)

The next agent is working on a project that contains **only the Bank_Analyser** component — not the bureau / combined / agentic stack.

### Scope differences to assume
- **Banking only.** No bureau tradeline data (`dpd_data.csv`), no bureau feature extraction, no key-findings engine for bureau.
- The analyser likely focuses on transactional intelligence: categorization, salary detection, EMI/rent/bills detection, scorecard for banking only.
- **No combined report.** Outputs are banking-only HTML / Excel / PDF.

### What to drop from this plan when reusing
- Slide 5 (Bureau Feature Extraction) — repurpose for the banking equivalent (e.g., "Banking Feature Extraction & Scorecard Engine") or drop.
- Slide 8 (Agentic foundation) — keep if Bank_Analyser also has an agentic skeleton; drop or simplify otherwise.
- Bureau data source from `arch_generic.png` — remove the bureau and tl_features boxes.

### What to keep
- The **style**, palette, chrome layout, and slide-1 cover pattern (modify the 2-letter mark from `RG` → `BA`).
- The slide-2 60/40 layout pattern.
- The slide-7 "Why agentic?" framing (highlight orchestration value).
- Slide 6 (Transaction Tagger card with hyperlink) — Bank_Analyser also depends on tagged transactions, so this slide is still relevant.
- Slide 11 (4 stacked impact rows), slide 12 (roadmap), slide 13 (guardrails + ask).

### Recommended slide count for Bank_Analyser
**10–11 slides** instead of 13 (drop bureau-specific slides; merge if possible).

### Verification checklist before handing the deck back to the user
- [ ] Style matches `Transaction_Tagger_Presentation.pptx` (chrome, palette, fonts).
- [ ] All architecture diagrams use the same palette and box-style language.
- [ ] No slide has dense paragraphs — bullets are concise noun-phrases on technical deep-dives.
- [ ] Each technical slide carries an architecture image with motivation copy beside it.
- [ ] Transaction Tagger hyperlink on its dedicated slide.
- [ ] Slide-1 cover has the 2-letter mark adapted to the new project.
- [ ] User has been asked to supply real screenshots with yellow highlights for output samples.
- [ ] Build script is self-contained and rebuildable with one command.

---

## 10. Key Conversational Decisions (for context)

These were debated and resolved during the conversation. Do not re-open unless the user reopens.

- **Output format**: `.pptx` (not Marp / markdown).
- **Audience split**: technical slides must be rigorous; C-suite slides can stay directional.
- **Sample CRN**: `698167220` (already has reports generated in `reports/` of the source project).
- **Honesty framing for ReAct**: lead with ReAct ambition; be explicit that today's intent-parser + planner + tool-registry are the *skeleton*, and the gap is dynamic LLM-driven tool selection.
- **Determinism is the project's spine** — every slide must respect "LLM never invents numbers".
- **Local Ollama only** — no cloud LLM mentions anywhere.
- **One slide per concept**, never split a single argument across two slides.

---

## 11. **Mandatory First Step for the Next Agent — Discover, Then Revise**

Do **not** start building slides from this plan as-is. This plan was written for a different project (Kotak Agentic Reader). Before any slide work, perform codebase discovery on the Bank_Analyser project and revise both this document and the slide content to match what actually exists.

### 11a. Discovery checklist (do this first)

**Before touching the codebase, open `Kotak_Agentic_Reader_Presentation.pptx` and walk through all 13 slides.** It is the canonical reference for chrome, palette, layout patterns, diagram style, and tone. Treat it as your slide-template library — copy the shapes you need into the new deck rather than re-deriving them from scratch. Also inspect it programmatically (`python-pptx`) to extract exact EMU coordinates, colors, and font sizes if the build script is not directly reusable.

Then ground every claim before it ends up on a slide:

1. **Map the directory** — `ls`, then read `README.md`, `CLAUDE.md`, `instructions.md`, or equivalent. Identify entry points (CLI, web UI, batch script).
2. **Identify data sources** — what CSVs / databases does Bank_Analyser actually read? Columns? Cardinality? Any bureau data, or banking-only?
3. **List the tools / features** — grep for tool registrations, feature extractors, analytics functions. Build a real inventory; do not assume the 20+ tools from the parent project exist here.
4. **Find the LLM layer** — is there one? Ollama? Cloud? What models? What prompts? Any agentic skeleton (intent parser, planner, executor)?
5. **Find the output layer** — HTML? Excel? PDF? Templates? Renderers? Themes?
6. **Find existing reports / sample CRNs** — what's a known-good customer ID for screenshots?
7. **Find the visual / branding assets** — logo, existing PPTX in the repo (use as style anchor if newer than `Transaction_Tagger_Presentation.pptx`).
8. **Verify the "three failure modes" framing** still applies. If Bank_Analyser has a narrower scope (e.g., only categorization, only income estimation), revise the problem statement.

### 11b. Update this plan after discovery

Edit this `plan.md` in place before touching the deck:

- Rewrite §1 (Project Background) with what Bank_Analyser actually does — not what the parent project does.
- Rewrite §4 (Slide Structure) to reflect the real scope. Drop slides that don't apply; add slides for capabilities unique to Bank_Analyser.
- Update §5 (Diagrams) — list which diagrams need to be regenerated vs reused. Specify exactly what each new diagram should show, based on the real architecture.
- Update §7 (Change History) — strike-through entries that no longer apply; add a "Bank_Analyser revisions" subsection for new decisions.
- Update §9 (Adaptation instructions) — replace assumptions with verified facts.
- Add a §12 below this section titled "**Bank_Analyser Codebase Facts**" — a short evidence ledger of what the discovery turned up (file paths, line numbers, function names). Slide claims must cite this ledger.

### 11c. Update slide content (after the plan is current)

For every slide:

- **Start from `Kotak_Agentic_Reader_Presentation.pptx` as the template**, not from a blank deck. Fork its build script (`/tmp/build_deck.py` in the parent project, or rebuild from the deck via `python-pptx` introspection) and edit slide-by-slide. The chrome helpers (`add_chrome`, `add_rect`, `add_text`, `panel`, stat-card pattern) are already correct — keep them.
- **Verify every concrete claim against the codebase.** If the slide says "20+ tools", grep for tool registrations and put the actual count. If it says "5 themes", check the templates directory.
- **Regenerate architecture diagrams** to reflect the real architecture. Do not reuse `arch_*.png` files from the parent project blindly — they will mislead. Keep the same matplotlib palette and box-style language seen in the reference deck so the new diagrams look like siblings, not strangers.
- **Replace the cover mark** (`RG`) with the appropriate 2-letter mark for Bank_Analyser (e.g., `BA`).
- **Update sample CRN** on output-walkthrough slides to a customer ID that actually exists in Bank_Analyser's data.
- **Re-derive the stat-card numbers** on the cover slide from the real project (cases/day, failure modes covered, output formats, etc.) — but keep the 4-card slot layout, EMU dimensions, and NAVY-stripe accent identical to the reference deck.
- **Re-verify the Transaction Tagger dependency** — does Bank_Analyser actually depend on it? If not, drop slide 6. If yes, keep the hyperlink slide but verify the path.
- **Side-by-side check before saving:** open the new deck next to `Kotak_Agentic_Reader_Presentation.pptx` and confirm chrome, palette, type sizes, and panel proportions match. Any visual drift = bug.

### 11d. Confirm with the user before generating the .pptx

Before running the build script:

- Present the **revised plan** (or a diff against this document) to the user for sign-off.
- Surface every assumption the discovery could not resolve as an explicit question.
- Only after the user confirms the plan should you call `python-pptx` to produce the deck.

### 11e. Do not skip discovery to "save time"

A plausible-looking deck built from stale assumptions is worse than no deck — it goes in front of C-suite and gets caught. Discovery is the cheapest part of this work; getting it wrong is the most expensive.

---

*End of plan. The next agent should read this end-to-end, perform §11 discovery, update §1, §4, §5, §7, §9, and add §12, then confirm with the user before building the deck.*
