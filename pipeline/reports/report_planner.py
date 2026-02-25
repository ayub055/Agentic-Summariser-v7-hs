"""Report planner - LLM-based section selection for customer reports.

This module uses an LLM to analyze a customer's data profile and decide:
1. Which report sections to include
2. The ordering of sections (by importance)
3. Emphasis level per section (high/medium/low)

The planner outputs structured JSON only - no free text.
All computation remains deterministic; LLM is only used for planning decisions.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
import json
import logging

from config.settings import PARSER_MODEL
from config.section_tools import AVAILABLE_SECTIONS, CORE_SECTIONS

logger = logging.getLogger(__name__)

# Valid emphasis levels
VALID_EMPHASIS_LEVELS = ("high", "medium", "low")


class PlannedSection(BaseModel):
    """A single section in the report plan."""
    section_name: str = Field(description="Section identifier from AVAILABLE_SECTIONS")
    emphasis: str = Field(default="medium", description="high/medium/low")
    reason: str = Field(default="", description="Why this section is included")

    @field_validator('section_name')
    @classmethod
    def validate_section_name(cls, v: str) -> str:
        if v not in AVAILABLE_SECTIONS:
            raise ValueError(f"Invalid section name: {v}. Must be one of {AVAILABLE_SECTIONS}")
        return v

    @field_validator('emphasis')
    @classmethod
    def validate_emphasis(cls, v: str) -> str:
        if v not in VALID_EMPHASIS_LEVELS:
            logger.warning(f"Invalid emphasis '{v}', defaulting to 'medium'")
            return "medium"
        return v


class ReportPlan(BaseModel):
    """The complete report plan output by the planner."""
    customer_id: int
    sections: List[PlannedSection] = Field(default_factory=list)
    excluded_sections: List[str] = Field(default_factory=list)
    planning_notes: str = Field(default="")


REPORT_PLANNER_PROMPT = """You are a financial report planner. Based on the customer data profile below, decide which report sections to include.

AVAILABLE SECTIONS:
- income_summary: Include if customer has salary/income data
- spending_summary: Include if customer has spending transactions
- cashflow_analysis: Include if multiple months of data available
- savings_analysis: Include if both income and spending data exist
- risk_indicators: Include if anomalies detected or income unstable
- recommendations: Always include for comprehensive reports
- emi_obligations: Include ONLY if EMI transactions detected
- rent_payments: Include ONLY if rent transactions detected
- utility_bills: Include ONLY if utility transactions detected

CUSTOMER DATA PROFILE:
{data_profile}

RULES:
1. Output ONLY valid JSON matching the schema below
2. Order sections by importance (most important first)
3. Set emphasis="high" for sections with significant findings
4. Exclude sections with no data (e.g., no EMI detected = exclude emi_obligations)
5. Always include income_summary, spending_summary if data exists
6. Always include recommendations

OUTPUT JSON SCHEMA:
{{"sections": [{{"section_name": "...", "emphasis": "high|medium|low", "reason": "..."}}], "excluded_sections": ["..."], "planning_notes": "..."}}

Output ONLY the JSON, no other text:"""


class ReportPlanner:
    """LLM-based report section planner.

    Uses an LLM to analyze customer data availability and decide which
    sections to include in the report, their order, and emphasis levels.
    Falls back to a default plan if LLM fails.
    """

    def __init__(self, model_name: str = PARSER_MODEL):
        self.llm = ChatOllama(model=model_name, temperature=0, format="json", seed=42)
        self.prompt = ChatPromptTemplate.from_template(REPORT_PLANNER_PROMPT)

    def plan(self, customer_id: int, data_profile: dict) -> ReportPlan:
        """
        Generate a report plan based on customer data profile.

        Args:
            customer_id: Customer identifier
            data_profile: Dict with keys indicating data availability, e.g.:
                - has_salary: bool
                - has_emi: bool
                - has_rent: bool
                - has_utilities: bool
                - transaction_count: int
                - month_count: int

        Returns:
            ReportPlan with ordered sections and emphasis levels
        """
        profile_str = self._format_data_profile(data_profile)

        try:
            response = self.llm.invoke(
                self.prompt.format(data_profile=profile_str)
            )
            data = json.loads(response.content)

            # Validate section names and build valid sections list
            valid_sections = []
            for section in data.get("sections", []):
                section_name = section.get("section_name")
                if section_name not in AVAILABLE_SECTIONS:
                    logger.warning(f"LLM returned invalid section '{section_name}', skipping")
                    continue
                try:
                    valid_sections.append(PlannedSection(**section))
                except ValueError as e:
                    logger.warning(f"Failed to create PlannedSection: {e}")
                    continue

            if not valid_sections:
                logger.warning("LLM returned no valid sections, using default plan")
                return self._default_plan(customer_id, data_profile)

            return ReportPlan(
                customer_id=customer_id,
                sections=valid_sections,
                excluded_sections=data.get("excluded_sections", []),
                planning_notes=data.get("planning_notes", "")
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}, using default plan")
            return self._default_plan(customer_id, data_profile)
        except Exception as e:
            logger.warning(f"Planner failed with error: {e}, using default plan")
            return self._default_plan(customer_id, data_profile)

    def _format_data_profile(self, profile: dict) -> str:
        """Format data profile dict as readable string for the prompt."""
        lines = []
        for key, value in profile.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    def _default_plan(self, customer_id: int, data_profile: dict) -> ReportPlan:
        """Default plan when LLM fails - include sections based on data availability."""
        sections = []

        # Always include core sections if data exists
        if data_profile.get("has_salary", False) or data_profile.get("transaction_count", 0) > 0:
            sections.append(PlannedSection(
                section_name="income_summary",
                emphasis="high",
                reason="Core section"
            ))

        if data_profile.get("transaction_count", 0) > 0:
            sections.append(PlannedSection(
                section_name="spending_summary",
                emphasis="high",
                reason="Core section"
            ))

        if data_profile.get("month_count", 0) > 1:
            sections.append(PlannedSection(
                section_name="cashflow_analysis",
                emphasis="medium",
                reason="Multiple months available"
            ))

        # Savings analysis - include if both income and spending data exist
        if data_profile.get("has_salary", False) and data_profile.get("transaction_count", 0) > 0:
            sections.append(PlannedSection(
                section_name="savings_analysis",
                emphasis="medium",
                reason="Income and spending data available"
            ))

        # Risk indicators - include if there's transaction history
        if data_profile.get("transaction_count", 0) > 10:
            sections.append(PlannedSection(
                section_name="risk_indicators",
                emphasis="medium",
                reason="Sufficient transaction history for risk analysis"
            ))

        # Presence-based sections
        if data_profile.get("has_emi", False):
            sections.append(PlannedSection(
                section_name="emi_obligations",
                emphasis="medium",
                reason="EMI detected"
            ))

        if data_profile.get("has_rent", False):
            sections.append(PlannedSection(
                section_name="rent_payments",
                emphasis="medium",
                reason="Rent detected"
            ))

        if data_profile.get("has_utilities", False):
            sections.append(PlannedSection(
                section_name="utility_bills",
                emphasis="low",
                reason="Utilities detected"
            ))

        # Always include recommendations
        sections.append(PlannedSection(
            section_name="recommendations",
            emphasis="medium",
            reason="Standard inclusion"
        ))

        return ReportPlan(
            customer_id=customer_id,
            sections=sections,
            planning_notes="Default plan (LLM fallback)"
        )
