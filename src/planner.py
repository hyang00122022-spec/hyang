"""P0: Plan generation module.

The Secretary reads the goal and writes a plan describing what each agent
(Logistics, Financial, Secretary) will do and in what order.

Build Priority: STUB EARLY — a rough plan must exist in the first hour.
"""

from __future__ import annotations

from .models import Plan, PlanPhase


class Planner:
    """Generates execution plans from user goals."""

    # Standard 3-phase pipeline for any document processing goal
    STANDARD_PHASES = [
        PlanPhase(
            phase=1,
            agent="Logistics",
            action=(
                "Collect and classify all documents (invoices, receipts, POs). "
                "Extract structured data via OCR. Score confidence. "
                "Flag low-quality or unreadable documents."
            ),
        ),
        PlanPhase(
            phase=2,
            agent="Financial",
            action=(
                "Build ledger from extracted documents. Validate arithmetic "
                "and tax. Detect duplicates (S1). Match POs (S3). "
                "Identify overdue payments (S4). Categorize spending (S5). "
                "Raise exceptions for escalation (S6)."
            ),
        ),
        PlanPhase(
            phase=3,
            agent="Secretary",
            action=(
                "Convert exceptions to plain-language tasks. "
                "Draft chase emails for overdue items. "
                "Generate final report: cash in/out, category breakdown, "
                "top 3 actions."
            ),
        ),
    ]

    def generate_plan(self, goal: str) -> Plan:
        """Generate an execution plan from a user goal.

        Args:
            goal: The business goal, e.g. "Close out September"

        Returns:
            A Plan with phased execution steps.
        """
        # Parse the goal to detect special cases
        goal_lower = goal.lower().strip()

        phases = []
        if "overdue" in goal_lower or "chase" in goal_lower:
            # Overdue-only workflow — skip Logistics, go straight to Financial
            phases = [
                PlanPhase(
                    phase=1,
                    agent="Financial",
                    action=(
                        "Scan existing ledger for overdue invoices (S4). "
                        "Cross-check payment records. Raise overdue exceptions."
                    ),
                ),
                PlanPhase(
                    phase=2,
                    agent="Secretary",
                    action=(
                        "Draft chase emails for all overdue items. "
                        "Create follow-up tasks with deadlines. "
                        "Surface for owner approval."
                    ),
                ),
            ]
        elif "reconcile" in goal_lower or "audit" in goal_lower:
            # Reconciliation-only workflow
            phases = [
                PlanPhase(
                    phase=1,
                    agent="Logistics",
                    action=(
                        "Collect all documents for the reconciliation period. "
                        "Extract and validate data quality."
                    ),
                ),
                PlanPhase(
                    phase=2,
                    agent="Financial",
                    action=(
                        "Reconcile documents against ledger entries (S2). "
                        "Check tolerance: +/-RM 1 (small) or +/-RM 5 (large). "
                        "Flag mismatches. Raise exceptions."
                    ),
                ),
                PlanPhase(
                    phase=3,
                    agent="Secretary",
                    action=(
                        "Generate reconciliation report. "
                        "Create tasks for mismatches. "
                        "Flag items needing manual review."
                    ),
                ),
            ]
        else:
            # Standard full pipeline
            phases = [
                PlanPhase(
                    phase=p.phase,
                    agent=p.agent,
                    action=p.action,
                )
                for p in self.STANDARD_PHASES
            ]

        plan = Plan(goal=goal, phases=phases)
        return plan

    def format_plan_text(self, plan: Plan) -> str:
        """Format a plan as human-readable text for the frontend.

        Args:
            plan: The Plan object to format.

        Returns:
            Multi-line string representation.
        """
        lines = [
            "=" * 60,
            f"  EXECUTION PLAN: {plan.goal}",
            "=" * 60,
            f"  Phases: {plan.total_phases}",
            "",
        ]

        for phase in plan.phases:
            status_icon = {
                "pending": "[ ]",
                "running": "[~]",
                "done": "[x]",
                "skipped": "[-]",
            }.get(phase.status.value, "[?]")
            lines.append(f"  Phase {phase.phase}: {status_icon} {phase.agent}")
            lines.append(f"    {phase.action}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)
