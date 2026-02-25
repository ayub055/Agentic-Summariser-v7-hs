"""
Kotak Agentic Reader - Streamlit UI for Transaction Intelligence System

A professional interface for natural language queries about bank transactions
with streaming LLM responses and PDF report generation.
"""

import streamlit as st
import base64
import html
from pathlib import Path

# =============================================================================
# BACKEND INTEGRATION IMPORTS
# =============================================================================
# These imports connect to the LangChain-based agentic pipeline
from pipeline import (
    TransactionPipeline, IntentParser, QueryPlanner, ToolExecutor, ResponseExplainer,
    generate_customer_report_pdf, get_transaction_insights_if_needed,
)
from tools.bureau import generate_bureau_report_pdf
from tools.combined_report import generate_combined_report_pdf
from schemas.intent import IntentType, ParsedIntent
from utils.helpers import mask_customer_id


# =============================================================================
# CONSTANTS
# =============================================================================
LOGO_PATH = Path(__file__).parent / "Kotak_Mahindra_Group_logo.svg.png"

# Kotak Brand Colors
KOTAK_RED = "#ED1C24"
KOTAK_DARK = "#1A1A1A"
KOTAK_GRAY = "#2D2D2D"

# =============================================================================
# PIPELINE STAGE DEFINITIONS
# =============================================================================
PIPELINE_STAGES = [
    {"id": "parse", "label": "Parsing intent"},
    {"id": "plan", "label": "Creating execution plan"},
    {"id": "execute", "label": "Executing tools"},
    {"id": "insights", "label": "Extracting insights"},
    {"id": "generate", "label": "Generating response"},
]

# Intents that benefit from transaction insights
INSIGHT_INTENTS = {
    IntentType.LENDER_PROFILE,
    IntentType.CUSTOMER_REPORT,
    IntentType.FINANCIAL_OVERVIEW,
}


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================
st.set_page_config(
    page_title="Kotak Agentic Reader",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =============================================================================
# CUSTOM STYLING
# =============================================================================
def apply_custom_css():
    """Apply Kotak brand styling with professional, clean design."""
    st.markdown(f"""
        <style>
        /* Hide Streamlit branding and processing bar */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}
        .stStatusWidget {{display: none;}}
        .stSpinner {{display: none;}}
        [data-testid="stStatusWidget"] {{display: none;}}
        [data-testid="stHeader"] {{display: none;}}
        [data-testid="stToolbar"] {{display: none;}}
        .stDeployButton {{display: none;}}

        /* Reduce top padding */
        .block-container {{
            padding-top: 1rem !important;
        }}

        /* Global styling */
        .stApp {{
            background: linear-gradient(180deg, #0f0f0f 0%, #1a1a1a 100%);
        }}

        /* Custom Header Bar */
        .kotak-header {{
            background: linear-gradient(90deg, {KOTAK_DARK} 0%, {KOTAK_GRAY} 100%);
            padding: 0.6rem 1.5rem;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
            border-bottom: 3px solid {KOTAK_RED};
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        }}

        .header-left {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .header-logo {{
            height: 36px;
            width: auto;
        }}

        .header-title {{
            font-size: 1.75rem;
            font-weight: 700;
            color: #ffffff;
            margin: 0;
            letter-spacing: 0.5px;
        }}

        .header-subtitle {{
            font-size: 0.7rem;
            color: #888888;
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .header-right {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        /* Report status badge */
        .report-badge {{
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            color: white;
            padding: 0.4rem 1rem;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .report-badge::before {{
            content: "\\2713";
        }}

        /* Message styling - User message with light blue */
        .user-message {{
            padding: 0.75rem 1rem;
            margin: 0.5rem 0;
            font-size: 0.95rem;
            line-height: 1.5;
            color: #e0e0e0;
            border-left: 3px solid #64b5f6;
            background: rgba(100, 181, 246, 0.08);
            border-radius: 0 8px 8px 0;
        }}

        .user-message strong {{
            color: #90caf9;
            font-weight: 600;
        }}

        .assistant-message {{
            padding: 0.75rem 1rem;
            margin: 0.5rem 0;
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Courier New', monospace;
            font-size: 0.85rem;
            line-height: 1.7;
            white-space: pre-wrap;
            color: #c0c0c0;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .system-message {{
            padding: 0.75rem 1rem;
            margin: 0.5rem 0;
            color: #ff6b6b;
            font-style: italic;
            background: rgba(255, 107, 107, 0.1);
            border-radius: 8px;
            border-left: 3px solid #ff6b6b;
        }}

        /* Stage indicator styling */
        .stage-container {{
            padding: 1rem;
            margin: 0.5rem 0;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }}

        .stage-item {{
            display: flex;
            align-items: center;
            padding: 0.4rem 0;
            color: #555555;
            font-size: 0.85rem;
            transition: all 0.3s ease;
        }}

        .stage-item.active {{
            color: {KOTAK_RED};
            font-weight: 500;
        }}

        .stage-item.completed {{
            color: #28a745;
        }}

        .stage-icon {{
            width: 24px;
            margin-right: 0.75rem;
            text-align: center;
            font-size: 0.9rem;
        }}

        .stage-info {{
            margin-top: 0.75rem;
            padding-top: 0.75rem;
            font-size: 0.8rem;
            color: #666666;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }}

        /* Thinking indicator */
        .thinking-indicator {{
            padding: 0.75rem 1rem;
            margin: 0.5rem 0;
            color: #64b5f6;
            font-style: italic;
            background: rgba(100, 181, 246, 0.05);
            border-radius: 8px;
            border-left: 3px solid #64b5f6;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}

        .thinking-dots {{
            animation: pulse 1.5s ease-in-out infinite;
        }}

        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}

        .spinning {{
            display: inline-block;
            animation: spin 1s linear infinite;
        }}

        /* Download button styling */
        .stDownloadButton > button {{
            background: linear-gradient(135deg, {KOTAK_RED} 0%, #c41922 100%) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 0.5rem 1.5rem !important;
            font-weight: 500 !important;
            transition: all 0.3s ease !important;
        }}

        .stDownloadButton > button:hover {{
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 12px rgba(237, 28, 36, 0.4) !important;
        }}

        /* Divider styling */
        hr {{
            border: none;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            margin: 1rem 0;
        }}
        </style>
    """, unsafe_allow_html=True)


# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================
def init_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "report_ready" not in st.session_state:
        st.session_state.report_ready = False

    if "report_path" not in st.session_state:
        st.session_state.report_path = None

    if "report_customer" not in st.session_state:
        st.session_state.report_customer = None

    if "processing" not in st.session_state:
        st.session_state.processing = False

    # ==========================================================================
    # BACKEND INTEGRATION: Initialize pipeline and parser (cached)
    # ==========================================================================
    if "pipeline" not in st.session_state:
        st.session_state.pipeline = None

    if "parser" not in st.session_state:
        st.session_state.parser = None


def get_pipeline() -> TransactionPipeline:
    """Get or create the transaction pipeline instance."""
    # ==========================================================================
    # BACKEND INTEGRATION: Pipeline initialization with streaming delay
    # ==========================================================================
    if st.session_state.pipeline is None:
        st.session_state.pipeline = TransactionPipeline(
            verbose=False,  # Disable console logging for UI
            stream_delay=0.025  # Natural typing effect
        )
    return st.session_state.pipeline


def get_parser() -> IntentParser:
    """Get or create the intent parser instance."""
    # ==========================================================================
    # BACKEND INTEGRATION: Parser for intent detection
    # ==========================================================================
    if st.session_state.parser is None:
        st.session_state.parser = IntentParser()
    return st.session_state.parser


# =============================================================================
# UI COMPONENTS
# =============================================================================
def get_logo_base64():
    """Get the Kotak logo as base64 string."""
    if LOGO_PATH.exists():
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


def render_header():
    """Render the branded header with logo and report status."""
    logo_b64 = get_logo_base64()

    # Build logo HTML
    logo_html = ""
    if logo_b64:
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" class="header-logo" alt="Kotak">'

    # Build report status HTML
    report_html = ""
    if st.session_state.report_ready:
        report_html = '<span class="report-badge">Report Ready</span>'

    # Render custom header (single line to avoid whitespace issues)
    header_html = (
        '<div class="kotak-header">'
        '<div class="header-left">'
        f'{logo_html}'
        '<div>'
        '<p class="header-title">Agentic Reader</p>'
        '<p class="header-subtitle">Transaction Intelligence</p>'
        '</div>'
        '</div>'
        '<div class="header-right">'
        f'{report_html}'
        '</div>'
        '</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)


def render_chat_history():
    """Render the chat history container with half-width messages."""
    chat_container = st.container()

    with chat_container:
        for message in st.session_state.messages:
            role = message.get("role", "assistant")
            content = message.get("content", "")

            if role == "user":
                # User message on the right half
                col1, col2 = st.columns([1, 1])
                with col2:
                    escaped_content = html.escape(content)
                    st.markdown(
                        f'<div class="user-message"><strong>You:</strong> {escaped_content}</div>',
                        unsafe_allow_html=True
                    )
            elif role == "system":
                # System message spans full width
                escaped_content = html.escape(content)
                st.markdown(
                    f'<div class="system-message">{escaped_content}</div>',
                    unsafe_allow_html=True
                )
            else:
                # Assistant message on the left half
                col1, col2 = st.columns([1, 1])
                with col1:
                    escaped_content = html.escape(content).replace("\n", "<br>")
                    st.markdown(
                        f'<div class="assistant-message">{escaped_content}</div>',
                        unsafe_allow_html=True
                    )
                    # Show download button if this message has an associated report
                    report_path = message.get("report_path")
                    if report_path:
                        pdf_path = Path(report_path)
                        if pdf_path.exists():
                            with open(pdf_path, "rb") as pdf_file:
                                pdf_bytes = pdf_file.read()
                            st.download_button(
                                label="Download Report PDF",
                                data=pdf_bytes,
                                file_name=pdf_path.name,
                                mime="application/pdf",
                                key=f"download_pdf_{id(message)}"
                            )

    return chat_container


def render_thinking_indicator(placeholder):
    """Show a thinking indicator."""
    placeholder.markdown(
        '<div class="thinking-indicator"><span class="thinking-dots">Thinking...</span></div>',
        unsafe_allow_html=True
    )


def render_stage_indicator(placeholder, current_stage: str, completed_stages: list, extra_info: str = ""):
    """
    Render pipeline stage indicator showing progress through stages.

    Args:
        placeholder: Streamlit placeholder to render into
        current_stage: ID of the currently active stage
        completed_stages: List of stage IDs that are completed
        extra_info: Optional extra information to display
    """
    stages_html = ['<div class="stage-container">']

    for stage in PIPELINE_STAGES:
        stage_id = stage["id"]
        label = stage["label"]

        if stage_id in completed_stages:
            # Completed stage
            icon = "&#10003;"  # Checkmark
            css_class = "completed"
        elif stage_id == current_stage:
            # Active stage
            icon = '<span class="spinning">&#8635;</span>'  # Spinning arrow
            css_class = "active"
        else:
            # Pending stage
            icon = "&#9675;"  # Empty circle
            css_class = ""

        stages_html.append(
            f'<div class="stage-item {css_class}">'
            f'<span class="stage-icon">{icon}</span>'
            f'{label}'
            f'</div>'
        )

    if extra_info:
        stages_html.append(f'<div class="stage-info">{html.escape(extra_info)}</div>')

    stages_html.append('</div>')

    placeholder.markdown("".join(stages_html), unsafe_allow_html=True)


def render_streaming_response(response_placeholder, intent: ParsedIntent, results: list,
                              transaction_insights, stage_placeholder, completed_stages: list):
    """Stream the response from the explainer."""
    try:
        # ==========================================================================
        # BACKEND INTEGRATION: Stream response from explainer
        # ==========================================================================
        pipeline = get_pipeline()
        explainer = pipeline.explainer

        full_response = ""
        first_chunk = True

        for chunk in explainer.stream_explain(intent, results, transaction_insights):
            if first_chunk:
                # Update stage to show streaming is happening
                completed_stages.append("generate")
                stage_placeholder.empty()
                first_chunk = False

            full_response += chunk
            # Update placeholder with accumulated response (escape HTML to prevent injection)
            formatted = html.escape(full_response).replace("\n", "<br>")
            response_placeholder.markdown(
                f'<div class="assistant-message">{formatted}</div>',
                unsafe_allow_html=True
            )

        return full_response

    except Exception as e:
        stage_placeholder.empty()
        error_msg = f"Error generating response: {str(e)}"
        response_placeholder.markdown(
            f'<div class="system-message">{html.escape(error_msg)}</div>',
            unsafe_allow_html=True
        )
        return error_msg


# =============================================================================
# BUSINESS LOGIC
# =============================================================================
def detect_report_intent(query: str) -> tuple[bool, int | None]:
    """
    Detect if the query is requesting a customer report.

    Returns:
        Tuple of (is_report_intent, customer_id)
    """
    try:
        # ==========================================================================
        # BACKEND INTEGRATION: Use IntentParser for accurate intent detection
        # ==========================================================================
        parser = get_parser()
        parsed = parser.parse(query)

        if parsed.intent == IntentType.CUSTOMER_REPORT and parsed.customer_id:
            return True, parsed.customer_id

        return False, None

    except Exception:
        # Fallback: if parser fails, return False
        return False, None


def generate_report(customer_id: int) -> tuple[bool, str | None]:
    """
    Generate PDF report for a customer.

    Returns:
        Tuple of (success, pdf_path or error_message)
    """
    try:
        # ==========================================================================
        # BACKEND INTEGRATION: Generate PDF report
        # ==========================================================================
        report, pdf_path = generate_customer_report_pdf(
            customer_id=customer_id,
            months=6,
            include_summary=True
        )

        # Update session state
        st.session_state.report_ready = True
        st.session_state.report_path = pdf_path
        st.session_state.report_customer = customer_id

        return True, pdf_path

    except Exception as e:
        return False, str(e)


def generate_bureau_report(customer_id: int) -> tuple[bool, str | None]:
    """
    Generate bureau PDF report for a customer.

    Returns:
        Tuple of (success, pdf_path or error_message)
    """
    try:
        report, pdf_path = generate_bureau_report_pdf(customer_id=customer_id)

        st.session_state.report_ready = True
        st.session_state.report_path = pdf_path
        st.session_state.report_customer = customer_id

        return True, pdf_path

    except Exception as e:
        return False, str(e)


def generate_combined(customer_id: int) -> tuple[bool, str | None]:
    """
    Generate combined (banking + bureau) PDF report for a customer.

    Returns:
        Tuple of (success, pdf_path or error_message)
    """
    try:
        _, _, pdf_path = generate_combined_report_pdf(customer_id=customer_id)

        st.session_state.report_ready = True
        st.session_state.report_path = pdf_path
        st.session_state.report_customer = customer_id

        return True, pdf_path

    except Exception as e:
        return False, str(e)


def process_query(query: str):
    """Process a user query through the pipeline with stage indicators."""
    if not query.strip():
        return

    # Add user message to history
    st.session_state.messages.append({
        "role": "user",
        "content": query
    })

    st.session_state.processing = True

    # Show user message immediately (right side)
    user_col1, user_col2 = st.columns([1, 1])
    with user_col2:
        escaped_query = html.escape(query)
        st.markdown(
            f'<div class="user-message"><strong>You:</strong> {escaped_query}</div>',
            unsafe_allow_html=True
        )

    # Create placeholders for stage indicator and response (left side)
    col1, col2 = st.columns([1, 1])

    with col1:
        stage_placeholder = st.empty()
        response_placeholder = st.empty()

    completed_stages = []

    try:
        # ==========================================================================
        # STAGE 1: Parse Intent
        # ==========================================================================
        render_stage_indicator(stage_placeholder, "parse", completed_stages)

        parser = get_parser()
        intent = parser.parse(query)

        # Resolve customer_id from session (fallback to last-used customer)
        pipeline = get_pipeline()
        pipeline.resolve_customer_id(intent)

        # Build extra info for stage display
        intent_info = f"Intent: {intent.intent.value}"
        if intent.customer_id:
            intent_info += f" | Customer: {mask_customer_id(intent.customer_id)}"

        completed_stages.append("parse")
        render_stage_indicator(stage_placeholder, "plan", completed_stages, intent_info)

        # ==========================================================================
        # STAGE 2: Create Plan
        # ==========================================================================
        planner = pipeline.planner

        plan, error = planner.create_plan(intent)

        if error:
            stage_placeholder.empty()
            response_placeholder.markdown(
                f'<div class="system-message">{html.escape(error)}</div>',
                unsafe_allow_html=True
            )
            st.session_state.messages.append({"role": "system", "content": error})
            st.session_state.processing = False
            st.rerun()
            return

        plan_info = f"Tools: {', '.join([p['tool'] for p in plan])}"
        completed_stages.append("plan")
        render_stage_indicator(stage_placeholder, "execute", completed_stages, plan_info)

        # ==========================================================================
        # STAGE 3: Execute Tools
        # ==========================================================================
        executor = pipeline.executor
        results = executor.execute(plan)

        # Check for report generation intent
        report_generated = False
        if intent.intent in (IntentType.CUSTOMER_REPORT, IntentType.BUREAU_REPORT, IntentType.COMBINED_REPORT) and intent.customer_id:
            if intent.intent == IntentType.COMBINED_REPORT:
                label = "Generating combined PDF report..."
            elif intent.intent == IntentType.BUREAU_REPORT:
                label = "Generating bureau PDF report..."
            else:
                label = "Generating PDF report..."
            render_stage_indicator(stage_placeholder, "execute", completed_stages, label)

            if intent.intent == IntentType.COMBINED_REPORT:
                success, result = generate_combined(intent.customer_id)
            elif intent.intent == IntentType.BUREAU_REPORT:
                success, result = generate_bureau_report(intent.customer_id)
            else:
                success, result = generate_report(intent.customer_id)

            if success:
                report_generated = True
            else:
                st.session_state.messages.append({
                    "role": "system",
                    "content": f"Failed to generate report: {result}"
                })

        exec_info = f"Executed {len(results)} tool(s)"
        completed_stages.append("execute")

        # ==========================================================================
        # STAGE 4: Extract Insights (if needed)
        # ==========================================================================
        transaction_insights = None
        if intent.intent in INSIGHT_INTENTS and intent.customer_id:
            render_stage_indicator(stage_placeholder, "insights", completed_stages, exec_info)
            transaction_insights = get_transaction_insights_if_needed(intent.customer_id)
            if transaction_insights:
                exec_info += f" | Patterns: {len(transaction_insights.patterns)}"

        completed_stages.append("insights")
        render_stage_indicator(stage_placeholder, "generate", completed_stages, exec_info)

        # ==========================================================================
        # STAGE 5: Generate Response (Streaming)
        # ==========================================================================
        full_response = render_streaming_response(
            response_placeholder,
            intent,
            results,
            transaction_insights,
            stage_placeholder,
            completed_stages
        )

        # Add assistant response to history (include report path if generated)
        message_data = {
            "role": "assistant",
            "content": full_response
        }
        if report_generated and st.session_state.report_path:
            message_data["report_path"] = st.session_state.report_path

        st.session_state.messages.append(message_data)

    except Exception as e:
        stage_placeholder.empty()
        error_msg = f"Error: {str(e)}"
        response_placeholder.markdown(
            f'<div class="system-message">{html.escape(error_msg)}</div>',
            unsafe_allow_html=True
        )
        st.session_state.messages.append({"role": "system", "content": error_msg})

    st.session_state.processing = False

    # Rerun to update UI
    st.rerun()


# =============================================================================
# MAIN APPLICATION
# =============================================================================
def main():
    """Main application entry point."""
    # Initialize
    init_session_state()
    apply_custom_css()

    # Render UI components
    render_header()
    render_chat_history()

    # Input area (fixed at bottom via st.chat_input)
    query = st.chat_input("Type here...")

    if query and not st.session_state.processing:
        process_query(query)


if __name__ == "__main__":
    main()
