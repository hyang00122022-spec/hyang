"""Tests for Planner (src/planner.py).

Tests cover:
- Standard plan generation (3 phases: Logistics, Financial, Secretary)
- Overdue-only plan (2 phases: Financial, Secretary)
- Reconciliation plan (3 phases with reconciliation focus)
- Plan text formatting
"""

import pytest

from src.models import PlanPhaseStatus
from src.planner import Planner


class TestPlannerStandard:
    """Tests for standard plan generation."""

    def test_standard_plan_has_3_phases(self):
        """A standard goal should produce a 3-phase plan."""
        planner = Planner()
        plan = planner.generate_plan("Close out September")
        assert plan.total_phases == 3

    def test_standard_plan_phases_are_logistics_financial_secretary(self):
        """Standard plan should have Logistics -> Financial -> Secretary order."""
        planner = Planner()
        plan = planner.generate_plan("Close out September")
        agents = [p.agent for p in plan.phases]
        assert agents == ["Logistics", "Financial", "Secretary"]

    def test_all_phases_start_as_pending(self):
        """All phases should start with status 'pending'."""
        planner = Planner()
        plan = planner.generate_plan("Process invoices")
        for phase in plan.phases:
            assert phase.status == PlanPhaseStatus.PENDING

    def test_phases_are_sequential(self):
        """Phase numbers should be 1, 2, 3..."""
        planner = Planner()
        plan = planner.generate_plan("Close out September")
        for i, phase in enumerate(plan.phases, 1):
            assert phase.phase == i


class TestPlannerOverdue:
    """Tests for overdue-only plan (detected by 'overdue' or 'chase' in goal)."""

    def test_overdue_plan_has_2_phases(self):
        """An overdue-focused goal should produce a 2-phase plan (skip Logistics)."""
        planner = Planner()
        plan = planner.generate_plan("Check overdue payments")
        assert plan.total_phases == 2

    def test_overdue_plan_skips_logistics(self):
        """Overdue plan should start with Financial, not Logistics."""
        planner = Planner()
        plan = planner.generate_plan("Chase overdue invoices")
        assert plan.phases[0].agent == "Financial"

    def test_chase_keyword_triggers_overdue_plan(self):
        """The word 'chase' should trigger the overdue plan."""
        planner = Planner()
        plan = planner.generate_plan("Chase all unpaid invoices")
        assert plan.total_phases == 2


class TestPlannerReconciliation:
    """Tests for reconciliation plan (detected by 'reconcile' or 'audit')."""

    def test_reconcile_plan_has_3_phases(self):
        """A reconciliation goal should produce a 3-phase plan."""
        planner = Planner()
        plan = planner.generate_plan("Reconcile October 2026")
        assert plan.total_phases == 3

    def test_reconcile_plan_first_phase_mentions_reconciliation(self):
        planner = Planner()
        plan = planner.generate_plan("Reconcile October")
        assert "reconcil" in plan.phases[1].action.lower()

    def test_audit_keyword_triggers_reconciliation_plan(self):
        planner = Planner()
        plan = planner.generate_plan("Audit September documents")
        assert plan.total_phases == 3


class TestPlanFormatting:
    """Tests for plan text formatting."""

    def test_format_plan_contains_goal(self):
        planner = Planner()
        plan = planner.generate_plan("Close out September")
        text = planner.format_plan_text(plan)
        assert "Close out September" in text

    def test_format_plan_contains_phase_count(self):
        planner = Planner()
        plan = planner.generate_plan("Close out September")
        text = planner.format_plan_text(plan)
        assert "3" in text  # total phases

    def test_format_plan_contains_agent_names(self):
        planner = Planner()
        plan = planner.generate_plan("Close out September")
        text = planner.format_plan_text(plan)
        assert "Logistics" in text
        assert "Financial" in text
        assert "Secretary" in text
