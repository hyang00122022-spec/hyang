"""Tests for data models (src/models.py)."""

import pytest
from pydantic import ValidationError

from src.models import (
    CategorySummary,
    ChaseEmail,
    DocumentInfo,
    EmailStatus,
    ExceptionEvent,
    EventType,
    FinalReport,
    Plan,
    PlanPhase,
    Priority,
    Task,
    TaskStatus,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_all_event_types_exist(self):
        assert EventType.OVERDUE == "overdue"
        assert EventType.DUPLICATE == "duplicate"
        assert EventType.ESCALATION == "escalation"
        assert EventType.FLAGGED == "flagged"

    def test_event_type_is_string(self):
        assert isinstance(EventType.OVERDUE.value, str)


class TestPriority:
    """Tests for Priority enum."""

    def test_priority_ordering(self):
        assert Priority.P1_CRITICAL < Priority.P2_HIGH
        assert Priority.P2_HIGH < Priority.P3_MEDIUM
        assert Priority.P3_MEDIUM < Priority.P4_LOW

    def test_priority_values(self):
        assert Priority.P1_CRITICAL.value == 1
        assert Priority.P2_HIGH.value == 2
        assert Priority.P3_MEDIUM.value == 3
        assert Priority.P4_LOW.value == 4


class TestExceptionEvent:
    """Tests for ExceptionEvent model."""

    def test_valid_overdue_event(self, sample_overdue_event):
        assert sample_overdue_event.event_type == EventType.OVERDUE
        assert sample_overdue_event.amount == 4800.00
        assert sample_overdue_event.currency == "MYR"

    def test_valid_duplicate_event(self, sample_duplicate_event):
        assert sample_duplicate_event.event_type == EventType.DUPLICATE
        assert sample_duplicate_event.duplicate_of is not None

    def test_amount_rounding(self):
        """Amounts should be rounded to 2 decimal places."""
        event = ExceptionEvent(
            event_type=EventType.OVERDUE,
            invoice_number="INV-001",
            vendor_name="Test Vendor",
            amount=100.999,
            details="Test",
        )
        assert event.amount == 101.00

    def test_negative_amount_rejected(self):
        """Amounts should not be negative."""
        with pytest.raises(ValidationError):
            ExceptionEvent(
                event_type=EventType.OVERDUE,
                invoice_number="INV-001",
                vendor_name="Test Vendor",
                amount=-100.00,
                details="Test",
            )

    def test_confidence_range_validation(self):
        """Confidence should be between 0.0 and 1.0."""
        # Valid
        event = ExceptionEvent(
            event_type=EventType.FLAGGED,
            invoice_number="INV-001",
            vendor_name="Test",
            amount=100.00,
            details="Test",
            confidence=0.5,
        )
        assert event.confidence == 0.5

        # Invalid - too high
        with pytest.raises(ValidationError):
            ExceptionEvent(
                event_type=EventType.FLAGGED,
                invoice_number="INV-001",
                vendor_name="Test",
                amount=100.00,
                details="Test",
                confidence=1.5,
            )

        # Invalid - too low
        with pytest.raises(ValidationError):
            ExceptionEvent(
                event_type=EventType.FLAGGED,
                invoice_number="INV-001",
                vendor_name="Test",
                amount=100.00,
                details="Test",
                confidence=-0.1,
            )

    def test_optional_fields_default_none(self):
        """Optional fields should default to None."""
        event = ExceptionEvent(
            event_type=EventType.OVERDUE,
            invoice_number="INV-001",
            vendor_name="Test",
            amount=100.00,
            details="Test",
        )
        assert event.duplicate_of is None
        assert event.escalation_reason is None
        assert event.confidence is None
        assert event.invoice_date is None


class TestTask:
    """Tests for Task model."""

    def test_valid_task(self):
        task = Task(
            task_id="TASK-0001",
            title="Test task",
            description="Test description",
            priority=Priority.P2_HIGH,
            event_type=EventType.OVERDUE,
            invoice_number="INV-001",
            vendor_name="Test Vendor",
            amount=500.00,
            action_required="Review the email",
        )
        assert task.task_id == "TASK-0001"
        assert task.status == TaskStatus.PENDING
        assert task.created_at is not None

    def test_amount_rounding(self):
        task = Task(
            task_id="TASK-0001",
            title="Test",
            description="Test",
            priority=Priority.P1_CRITICAL,
            event_type=EventType.DUPLICATE,
            invoice_number="INV-001",
            vendor_name="Test",
            amount=99.999,
            action_required="Check",
        )
        assert task.amount == 100.00


class TestChaseEmail:
    """Tests for ChaseEmail model."""

    def test_default_status_is_draft(self):
        """New chase emails should start as draft (human-in-the-loop)."""
        email = ChaseEmail(
            email_id="EMAIL-0001",
            to="vendor@test.com",
            subject="Test subject",
            body="Test body",
            related_invoice="INV-001",
            related_task_id="TASK-0001",
        )
        assert email.status == EmailStatus.DRAFT

    def test_status_can_be_approved(self):
        email = ChaseEmail(
            email_id="EMAIL-0001",
            to="vendor@test.com",
            subject="Test",
            body="Test",
            status=EmailStatus.APPROVED,
            related_invoice="INV-001",
            related_task_id="TASK-0001",
        )
        assert email.status == EmailStatus.APPROVED


class TestPlan:
    """Tests for Plan model."""

    def test_plan_total_phases_auto_calculated(self, sample_plan):
        """total_phases should auto-calculate from len(phases)."""
        assert sample_plan.total_phases == 3

    def test_plan_has_created_at(self, sample_plan):
        assert sample_plan.created_at is not None


class TestFinalReport:
    """Tests for FinalReport model."""

    def test_net_cash_auto_calculated(self):
        """net_cash should be auto-calculated as cash_in - cash_out."""
        report = FinalReport(
            goal="Test",
            period="September",
            cash_in=10000.00,
            cash_out=7000.00,
            categories=[],
            top_3_actions=["Action 1", "Action 2", "Action 3"],
        )
        assert report.net_cash == 3000.00

    def test_net_cash_negative(self):
        """net_cash can be negative if cash_out > cash_in."""
        report = FinalReport(
            goal="Test",
            period="September",
            cash_in=5000.00,
            cash_out=8000.00,
            categories=[],
            top_3_actions=["Action 1"],
        )
        assert report.net_cash == -3000.00

    def test_net_cash_rounded(self):
        """net_cash should be rounded to 2 decimal places."""
        report = FinalReport(
            goal="Test",
            period="September",
            cash_in=100.555,
            cash_out=50.333,
            categories=[],
            top_3_actions=["Action 1"],
        )
        assert report.net_cash == round(100.555 - 50.333, 2)


class TestDocumentInfo:
    """Tests for DocumentInfo model."""

    def test_valid_document(self, sample_documents):
        doc = sample_documents[0]
        assert doc.doc_id == "DOC-001"
        assert doc.doc_type == "invoice"
        assert doc.grand_total == 12500.00

    def test_confidence_validation(self):
        """Confidence should be between 0.0 and 1.0."""
        with pytest.raises(ValidationError):
            DocumentInfo(
                doc_id="DOC-001",
                file_name="test.pdf",
                doc_type="invoice",
                vendor_name="Test",
                invoice_number="INV-001",
                invoice_date="2026-01-01",
                grand_total=100.00,
                confidence=1.5,
            )
