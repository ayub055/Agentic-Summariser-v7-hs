"""Generate all 5 architecture PNGs used by build_deck.py.

Output dir: /tmp/ppt_assets/
Palette matches Transaction_Tagger_Presentation.pptx / Kotak_Agentic_Reader_Presentation.pptx.
"""
import os
import matplotlib.pyplot as plt
import matplotlib.patches as mp
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

NAVY   = "#1B3A6B"
BLUE   = "#275BAD"
GOLD   = "#B8860B"
TINT   = "#E8EDF7"
BORDER = "#CCD3DD"
TEXT   = "#556578"

OUTDIR = "/tmp/ppt_assets"
os.makedirs(OUTDIR, exist_ok=True)


# ---------- helpers ----------
def make_fig(w=14, h=6.5):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis('off')
    return fig, ax


def box(ax, x, y, w, h, label, fill=TINT, edge=NAVY, text_color=NAVY,
        fontsize=10, bold=True, sub=None):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.8",
        linewidth=1.2, facecolor=fill, edgecolor=edge))
    weight = 'bold' if bold else 'normal'
    if sub:
        ax.text(x+w/2, y+h*0.62, label, ha='center', va='center',
                color=text_color, fontsize=fontsize, fontweight=weight)
        ax.text(x+w/2, y+h*0.30, sub, ha='center', va='center',
                color=text_color, fontsize=fontsize-2, style='italic')
    else:
        ax.text(x+w/2, y+h/2, label, ha='center', va='center',
                color=text_color, fontsize=fontsize, fontweight=weight)


def arrow(ax, x1, y1, x2, y2, color=NAVY, style='-|>'):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style,
        mutation_scale=14, linewidth=1.5, color=color))


def band(ax, y, h, label, fill=NAVY, text_color="white", fontsize=10):
    ax.add_patch(mp.Rectangle((0, y), 100, h, facecolor=fill, edgecolor='none'))
    ax.text(1, y+h/2, label, color=text_color, fontsize=fontsize,
            fontweight='bold', va='center')


# ============ 1) Generic system architecture ============
def diagram_generic():
    fig, ax = make_fig(14, 7)
    band(ax, 93, 6, "  KOTAK AGENTIC READER — END-TO-END ARCHITECTURE", fill=NAVY, fontsize=11)

    ax.text(7, 88, "DATA SOURCES", color=GOLD, fontsize=9, fontweight='bold', ha='center')
    box(ax, 1, 75, 12, 8, "Banking\nTransactions",  sub="rgs.csv",       fontsize=9)
    box(ax, 1, 64, 12, 8, "Bureau / DPD\nTradelines", sub="dpd_data.csv", fontsize=9)
    box(ax, 1, 53, 12, 8, "Pre-computed\nTL Features", sub="tl_features.csv", fontsize=9)

    ax.text(50, 88, "5-STAGE AGENTIC PIPELINE", color=GOLD, fontsize=9, fontweight='bold', ha='center')
    stages = [
        ("Intent\nParser",     "Mistral · JSON",     18),
        ("Query\nPlanner",     "Deterministic",      33),
        ("Tool\nExecutor",     "Agent invokes",      48),
        ("Insight\nExtractor", "llama3.2",           63),
        ("Explainer /\nNarrator", "llama3.2 · stream", 78),
    ]
    for label, sub, x in stages:
        box(ax, x, 70, 13, 13, label, sub=sub, fill=TINT, edge=BLUE, fontsize=9)
    for i in range(4):
        arrow(ax, stages[i][2]+13, 76.5, stages[i+1][2], 76.5, color=BLUE)

    ax.text(50, 60,
            "DETERMINISTIC TOOL LAYER  —  every tool below is invoked by the agent (Tool Executor)",
            color=GOLD, fontsize=9, fontweight='bold', ha='center')

    tools = [
        ("Analytics\n(15 fns)",       "white", BORDER, TEXT,    False),
        ("Bureau\nFeatures",          "white", BORDER, TEXT,    False),
        ("Transaction\nTagger",        GOLD,    GOLD,   "white", True),   # HIGHLIGHTED
        ("Key Findings\n(40+ rules)", "white", BORDER, TEXT,    False),
        ("Category\nResolver",        "white", BORDER, TEXT,    False),
        ("Report\nBuilders",          "white", BORDER, TEXT,    False),
    ]
    slot_w = 11; gap = 1.2
    total = len(tools)*slot_w + (len(tools)-1)*gap
    x0 = (100 - total) / 2
    for i, (t, fill, edge, tc, bold) in enumerate(tools):
        xi = x0 + i*(slot_w + gap)
        box(ax, xi, 47, slot_w, 9, t, fill=fill, edge=edge, fontsize=8, text_color=tc, bold=bold)
        if t.startswith("Transaction"):
            ax.text(xi+slot_w/2, 45.5, "upstream model · now an agent tool",
                    color=GOLD, fontsize=7, style='italic', ha='center')

    ax.text(50, 40, "CONFIGURATION (Single source of truth)",
            color=GOLD, fontsize=9, fontweight='bold', ha='center')
    cfg = ["thresholds.py", "prompts.py", "categories.yaml", "intents.py", "loan_type.py"]
    for i, t in enumerate(cfg):
        box(ax, 18 + i*14, 28, 12, 7, t, fill=NAVY, edge=NAVY, text_color="white", fontsize=8)

    ax.text(93, 88, "OUTPUTS", color=GOLD, fontsize=9, fontweight='bold', ha='center')
    box(ax, 87, 75, 12, 8, "HTML\nReport",   fill=GOLD, edge=GOLD, text_color="white", fontsize=9)
    box(ax, 87, 64, 12, 8, "Excel\nWorkbook", fill=GOLD, edge=GOLD, text_color="white", fontsize=9)
    box(ax, 87, 53, 12, 8, "PDF\nReport",    fill=GOLD, edge=GOLD, text_color="white", fontsize=9)

    arrow(ax, 13, 79, 18, 76.5, color=NAVY)
    arrow(ax, 13, 68, 18, 76,   color=NAVY)
    arrow(ax, 13, 57, 18, 75,   color=NAVY)
    arrow(ax, 91, 76.5, 87, 79, color=GOLD)
    arrow(ax, 91, 76.5, 87, 68, color=GOLD)
    arrow(ax, 91, 76.5, 87, 57, color=GOLD)
    arrow(ax, 54.5, 70, 50, 56, color=GOLD)
    arrow(ax, 48, 35, 48, 47,   color=BORDER)

    band(ax, 0, 8,
         "  Local Ollama inference  ·  Zero PII egress  ·  Deterministic numbers  ·  LLM narrates only",
         fill=TINT, text_color=NAVY, fontsize=10)

    plt.tight_layout()
    plt.savefig(f"{OUTDIR}/arch_generic.png", dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()


# ============ 2) Determinism > Intelligence ============
def diagram_determinism():
    fig, ax = make_fig(14, 6.5)
    band(ax, 93, 6, "  DETERMINISM > INTELLIGENCE — WHERE LLMs DO AND DON'T TOUCH DATA",
         fill=NAVY, fontsize=11)

    box(ax, 3, 60, 16, 18, "Raw Data\n(transactions,\nbureau, features)",
        fill=TINT, edge=NAVY, fontsize=10)

    box(ax, 28, 70, 44, 18, "DETERMINISTIC ENGINE\nAgent tool-call results · pure Python",
        fill=GOLD, edge=GOLD, text_color="white", fontsize=11)
    ax.text(50, 64,
            "Feature vectors · Risk thresholds · Key findings · Scorecard · Checklist",
            ha='center', fontsize=9, color=TEXT, style='italic')
    ax.text(50, 61,
            "each tool above is executed per the agent's plan — no number is invented by the LLM",
            ha='center', fontsize=8.5, color=NAVY, style='italic', fontweight='bold')

    box(ax, 28, 30, 44, 18, "LLM LAYER (Ollama, local)\nMistral · llama3.2",
        fill=BLUE, edge=BLUE, text_color="white", fontsize=11)
    ax.text(50, 24, "Intent JSON · Plan · Narration · Persona — NEVER numbers",
            ha='center', fontsize=9, color=TEXT, style='italic')

    box(ax, 80, 60, 17, 28, "Audit-grade\nReport",
        fill=NAVY, edge=NAVY, text_color="white", fontsize=11)

    arrow(ax, 19, 70, 28, 79, color=NAVY)
    arrow(ax, 19, 68, 28, 39, color=NAVY)
    arrow(ax, 72, 79, 80, 78, color=GOLD)
    arrow(ax, 72, 39, 80, 70, color=BLUE)
    arrow(ax, 50, 48, 50, 70, color=GOLD,   style='-|>')
    ax.text(53, 55, "Agent plan\n→ tool calls",
            color=NAVY, fontsize=8, style='italic', fontweight='bold')
    arrow(ax, 46, 70, 46, 48, color=BORDER, style='->')
    ax.text(40, 57, "Pre-computed\nsummary only",
            color=TEXT, fontsize=8, style='italic', ha='right')

    band(ax, 0, 8,
         "  Why: regulatory auditability  ·  reproducibility  ·  no LLM hallucination of numbers  ·  every threshold in config/thresholds.py",
         fill=TINT, text_color=NAVY, fontsize=10)

    plt.tight_layout()
    plt.savefig(f"{OUTDIR}/arch_determinism.png", dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()


# ============ 3) Bureau features + Key Findings ============
def diagram_features():
    fig, ax = make_fig(14, 6.5)
    band(ax, 93, 6, "  BUREAU FEATURE EXTRACTION → KEY-FINDINGS ENGINE",
         fill=NAVY, fontsize=11)

    box(ax, 2,  70, 14, 14, "dpd_data.csv\n+ tl_features.csv",
        fill=TINT, edge=NAVY, fontsize=9)
    box(ax, 19, 70, 16, 14, "LoanType\nNormalization\n(100+ raw → 13)",
        fill="white", edge=BORDER, fontsize=9, text_color=TEXT)
    box(ax, 38, 70, 16, 14, "Per-LoanType\nFeature Vectors\n(DPD, util, vintage)",
        fill="white", edge=BORDER, fontsize=9, text_color=TEXT)
    box(ax, 57, 70, 16, 14, "Aggregator →\nExecutive\nSummary Inputs",
        fill="white", edge=BORDER, fontsize=9, text_color=TEXT)

    arrow(ax, 16, 77, 19, 77)
    arrow(ax, 35, 77, 38, 77)
    arrow(ax, 54, 77, 57, 77)

    box(ax, 76, 70, 22, 14,
        "KEY-FINDINGS ENGINE\n40+ threshold rules\nZero LLM",
        fill=GOLD, edge=GOLD, text_color="white", fontsize=10)
    arrow(ax, 73, 77, 76, 77, color=GOLD)

    findings = [
        ("Portfolio\nfindings",      "delinquency, exposure"),
        ("Loan-type\nfindings",      "CC util, PL balance"),
        ("Tradeline\nfindings",      "enquiry velocity"),
        ("Composite\nrisk findings", "multi-signal"),
    ]
    for i, (lbl, sub) in enumerate(findings):
        box(ax, 3 + i*24, 38, 22, 16, lbl, sub=sub, fill=TINT, edge=NAVY, fontsize=10)
        arrow(ax, 14 + i*24, 70, 14 + i*24, 54, color=NAVY)

    box(ax, 30, 14, 40, 14,
        "Severity-tagged Findings\nhigh_risk · moderate · concern · positive · neutral",
        fill=NAVY, edge=NAVY, text_color="white", fontsize=10)
    for i in range(4):
        arrow(ax, 14 + i*24, 38, 50, 28, color=BORDER)

    band(ax, 0, 8,
         "  Single source of truth: config/thresholds.py  ·  Same constants used by engine AND LLM narration prompt",
         fill=TINT, text_color=NAVY, fontsize=10)

    plt.tight_layout()
    plt.savefig(f"{OUTDIR}/arch_features.png", dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()


# ============ 4) Report generation & rendering ============
def diagram_rendering():
    fig, ax = make_fig(14, 6.5)
    band(ax, 93, 6, "  REPORT GENERATION & MULTI-FORMAT RENDERING",
         fill=NAVY, fontsize=11)

    ax.text(50, 88, "BUILDERS  (deterministic)",
            color=GOLD, fontsize=9, fontweight='bold', ha='center')
    box(ax, 4,  72, 22, 13, "Customer Report\nBuilder",
        sub="banking sections",          fill=TINT, edge=NAVY, fontsize=10)
    box(ax, 30, 72, 22, 13, "Bureau Report\nBuilder",
        sub="features + findings",       fill=TINT, edge=NAVY, fontsize=10)
    box(ax, 56, 72, 22, 13, "Combined Report\nBuilder",
        sub="merges both + LLM exec summary", fill=TINT, edge=NAVY, fontsize=10)
    box(ax, 82, 72, 14, 13, "Cache\n(per CRN)",
        fill="white", edge=BORDER, fontsize=9, text_color=TEXT, bold=False)

    ax.text(50, 64, "NARRATION  (llama3.2 · fail-soft)",
            color=GOLD, fontsize=9, fontweight='bold', ha='center')
    box(ax, 15, 48, 30, 12, "Section summary chains\n(LCEL · LangChain)",
        fill=BLUE, edge=BLUE, text_color="white", fontsize=10)
    box(ax, 55, 48, 30, 12, "Executive summary\n(Combined report)",
        fill=BLUE, edge=BLUE, text_color="white", fontsize=10)
    for x in [15, 41, 67]:
        arrow(ax, x+11, 72, 30, 60, color=BORDER)

    ax.text(50, 40, "RENDERING LAYER",
            color=GOLD, fontsize=9, fontweight='bold', ha='center')
    box(ax, 4,  22, 28, 14, "Jinja2 templates\n(5 themes)",
        fill="white", edge=BORDER, fontsize=10, text_color=TEXT, bold=False)
    box(ax, 36, 22, 28, 14, "fpdf2 renderer\n(ReportPDF base)",
        fill="white", edge=BORDER, fontsize=10, text_color=TEXT, bold=False)
    box(ax, 68, 22, 28, 14, "Excel exporter\n(openpyxl)",
        fill="white", edge=BORDER, fontsize=10, text_color=TEXT, bold=False)

    arrow(ax, 30, 48, 18, 36, color=BLUE); arrow(ax, 30, 48, 50, 36, color=BLUE); arrow(ax, 30, 48, 82, 36, color=BLUE)
    arrow(ax, 70, 48, 18, 36, color=BLUE); arrow(ax, 70, 48, 50, 36, color=BLUE); arrow(ax, 70, 48, 82, 36, color=BLUE)

    box(ax, 4,  4, 28, 12, "HTML  (Chart.js)", fill=GOLD, edge=GOLD, text_color="white", fontsize=11)
    box(ax, 36, 4, 28, 12, "PDF",               fill=GOLD, edge=GOLD, text_color="white", fontsize=11)
    box(ax, 68, 4, 28, 12, "XLSX",              fill=GOLD, edge=GOLD, text_color="white", fontsize=11)
    arrow(ax, 18, 22, 18, 16, color=GOLD)
    arrow(ax, 50, 22, 50, 16, color=GOLD)
    arrow(ax, 82, 22, 82, 16, color=GOLD)

    plt.tight_layout()
    plt.savefig(f"{OUTDIR}/arch_rendering.png", dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()


# ============ 5) Agentic foundation (today vs ReAct) ============
def diagram_agentic():
    fig, ax = make_fig(14, 6.5)
    band(ax, 93, 6, "  AGENTIC FOUNDATION — TODAY'S SKELETON, TOMORROW'S REACT AGENT",
         fill=NAVY, fontsize=11)

    ax.text(50, 88, "TODAY  (deterministic intent routing)",
            color=GOLD, fontsize=10, fontweight='bold', ha='center')
    box(ax, 3,  68, 18, 14, "User Query",   fill=TINT, edge=NAVY, fontsize=10)
    box(ax, 25, 68, 18, 14, "Intent Parser\n(LLM · JSON)",
        fill=BLUE, edge=BLUE, text_color="white", fontsize=10)
    box(ax, 47, 68, 18, 14, "Planner\n(static map)",
        fill="white", edge=BORDER, fontsize=10, text_color=TEXT, bold=False)
    box(ax, 69, 68, 18, 14, "Tool Registry\n(20+ tools)",
        fill="white", edge=BORDER, fontsize=10, text_color=TEXT, bold=False)
    for x in [21, 43, 65]:
        arrow(ax, x, 75, x+4, 75, color=NAVY)

    ax.text(50, 56, "TOMORROW  (full ReAct loop)",
            color=GOLD, fontsize=10, fontweight='bold', ha='center')
    box(ax, 8,  28, 18, 14, "LLM Reasoner\n(Thought)",
        fill=BLUE, edge=BLUE, text_color="white", fontsize=10)
    box(ax, 33, 28, 18, 14, "Action\nSelector",
        fill=GOLD, edge=GOLD, text_color="white", fontsize=10)
    box(ax, 58, 28, 18, 14, "Tool\nInvocation",
        fill="white", edge=BORDER, fontsize=10, text_color=TEXT, bold=False)
    box(ax, 83, 28, 14, 14, "Observation",
        fill=TINT, edge=NAVY, fontsize=10)

    arrow(ax, 26, 35, 33, 35, color=NAVY)
    arrow(ax, 51, 35, 58, 35, color=GOLD)
    arrow(ax, 76, 35, 83, 35, color=NAVY)
    arrow(ax, 90, 28, 17, 20, color=GOLD, style='->')
    arrow(ax, 17, 20, 17, 28, color=GOLD, style='-|>')
    ax.text(50, 17, "↻  Reflect & Re-plan until answer is grounded",
            ha='center', fontsize=9, color=TEXT, style='italic', fontweight='bold')

    band(ax, 0, 8,
         "  Already built: parser · planner · tool registry · audit log.  Gap: replace static INTENT_TOOL_MAP with dynamic LLM-driven selection.",
         fill=TINT, text_color=NAVY, fontsize=10)

    plt.tight_layout()
    plt.savefig(f"{OUTDIR}/arch_agentic.png", dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()


if __name__ == "__main__":
    diagram_generic()
    diagram_determinism()
    diagram_features()
    diagram_rendering()
    diagram_agentic()
    print(f"✓ All 5 diagrams generated in {OUTDIR}/")
