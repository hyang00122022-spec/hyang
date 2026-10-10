"""Tests for Reporter (src/reporter.py).

Tests cover:
- Cash flow calculation (cash_in from receipts, cash_out from invoices)
- Category breakdown
- Top 3 actions generation
- Period extraction from goal
- Report formatting
"""

import pytest

from src.models import (
    DocumentInfo,
    ExceptionEvent,
    EventType,
    Priority,
    Task,
    TaskStatus,
)
from src.reporter import Reporter


@pytest.fixture
def sample_tasks():
    """Sample tasks for report testing."""
    return [
        Task(
            task_id="TASK-0001",
            title="VERIFY duplicate: INV-001",
            description="Duplicate detected",
            priority=Priority.P1_CRITICAL,
            event_type=EventType.DUPLICATE,
            invoice_number="INV-001",
            vendor_name="Vendor A",
            amount=5000.00,
            action_required="Verify original",
        ),
        Task(
            task_id="TASK-0002",
            title="Chase overdue: INV-002",
            description="Overdue payment",
            priority=Priority.P2_HIGH,
            event_type=EventType.OVERDUE,
            invoice_number="INV-002",
            vendor_name="Vendor B",
            amount=3000.00,
            action_required="Approve chase email",
        ),
    ]


class TestCashFlow:
    """Tests for cash flow calculation."""

    def test_cash_in_from_receipts(self, sample_documents):
        """Cash in should be the sum of receipt-type documents."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
        )
        # Only DOC-002 is a receipt with amount 3500
        assert report.cash_in == 3500.00

    def test_cash_out_from_invoices(self, sample_documents):
        """Cash out should be the sum of non-receipt documents."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
        )
        # DOC-001 (12500) + DOC-003 (4800) = 17300
        assert report.cash_out == 17300.00

    def test_net_cash_calculated(self, sample_documents):
        """Net cash should be cash_in - cash_out."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
        )
        assert report.net_cash == 3500.00 - 17300.00

    def test_empty_documents_zero_cash(self):
        """No documents should produce zero cash flow."""
        reporter = Reporter()
        report = reporter.generate(goal="Test", documents=[])
        assert report.cash_in == 0
        assert report.cash_out == 0
        assert report.net_cash == 0


class TestCategorization:
    """Tests for category breakdown (S5)."""

    def test_categories_populated(self, sample_documents):
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
        )
        assert len(report.categories) > 0

    def test_it_category_total(self, sample_documents):
        """IT category should sum all IT line items."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
        )
        it_cat = next(c for c in report.categories if c.category == "IT")
        assert it_cat.total == 12500.00
        assert it_cat.count == 1

    def test_categories_sorted_by_total_descending(self, sample_documents):
        """Categories should be sorted by total, descending."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
        )
        totals = [c.total for c in report.categories]
        assert totals == sorted(totals, reverse=True)


class TestTop3Actions:
    """Tests for top 3 actions generation."""

    def test_top_3_actions_count(self, sample_documents, sample_tasks):
        """Should always return exactly 3 actions."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
            tasks=sample_tasks,
        )
        assert len(report.top_3_actions) == 3

    def test_critical_task_is_first_action(self, sample_documents, sample_tasks):
        """P1 critical tasks should be the first recommended action."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
            tasks=sample_tasks,
        )
        assert "URGENT" in report.top_3_actions[0]

    def test_actions_generated_without_tasks(self, sample_documents):
        """Should still generate 3 actions even with no tasks."""
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
            tasks=[],
        )
        assert len(report.top_3_actions) == 3


class TestPeriodExtraction:
    """Tests for period extraction from goal string."""

    def test_extract_month_from_goal(self):
        reporter = Reporter()
        report = reporter.generate(goal="Close out September", documents=[])
        assert "September" in report.period

    def test_extract_month_and_year(self):
        reporter = Reporter()
        report = reporter.generate(
            goal="Reconcile October 2026", documents=[]
        )
        assert "October" in report.period
        assert "2026" in report.period

    def test_default_period_when_no_month(self):
        reporter = Reporter()
        report = reporter.generate(goal="Process invoices", documents=[])
        assert report.period == "Current period"


class TestReportFormatting:
    """Tests for report text formatting."""

    def test_report_contains_goal(self, sample_documents):
        reporter = Reporter()
        report = reporter.generate(
            goal="Close out September",
            documents=sample_documents,
        )
        text = reporter.format_report(report)
        assert "Close out September" in text

    def test_report_contains_cash_flow(self, sample_documents):
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
        )
        text = reporter.format_report(report)
        assert "Cash In" in text
        assert "Cash Out" in text
        assert "Net Cash" in text

    def test_report_contains_top_3_actions(self, sample_documents, sample_tasks):
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
            tasks=sample_tasks,
        )
        text = reporter.format_report(report)
        assert "TOP 3" in text

    def test_report_contains_statistics(self, sample_documents, sample_tasks):
        reporter = Reporter()
        report = reporter.generate(
            goal="Test",
            documents=sample_documents,
            tasks=sample_tasks,
        )
        text = reporter.format_report(report)
        assert "Exceptions" in text
        assert "Tasks" in text
