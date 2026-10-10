"""Tests for TaskGenerator (src/task_generator.py).

Tests cover:
- Each event type converts to the correct task
- Priority assignment is correct
- Duplicate precedence rule (duplicates before overdue)
- Chase emails are drafted only for overdue events
- Edge cases: confidence=0.70, amount=RM 500, duplicate+overdue on same invoice
"""

import pytest

from src.models import (
    EmailStatus,
    EventType,
    ExceptionEvent,
    Priority,
    TaskStatus,
)
from src.task_generator import TaskGenerator


class TestTaskGeneratorBasics:
    """Basic tests for TaskGenerator."""

    def test_empty_exceptions_returns_empty(self):
        """No exceptions should produce no tasks and no emails."""
        gen = TaskGenerator()
        tasks, emails = gen.process_exceptions([])
        assert tasks == []
        assert emails == []

    def test_single_overdue_produces_one_task_one_email(self, sample_overdue_event):
        """An overdue event should produce exactly 1 task and 1 chase email."""
        gen = TaskGenerator()
        tasks, emails = gen.process_exceptions([sample_overdue_event])
        assert len(tasks) == 1
        assert len(emails) == 1

    def test_task_ids_are_sequential(self, sample_overdue_event, sample_duplicate_event):
        """Task IDs should be sequential (TASK-0001, TASK-0002, ...)."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([
            sample_duplicate_event,  # processed first (higher priority)
            sample_overdue_event,
        ])
        assert tasks[0].task_id == "TASK-0001"
        assert tasks[1].task_id == "TASK-0002"


class TestOverdueHandling:
    """Tests for overdue event handling."""

    def test_overdue_task_has_p2_priority(self, sample_overdue_event):
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_overdue_event])
        assert tasks[0].priority == Priority.P2_HIGH

    def test_overdue_task_status_is_pending(self, sample_overdue_event):
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_overdue_event])
        assert tasks[0].status == TaskStatus.PENDING

    def test_overdue_email_is_draft(self, sample_overdue_event):
        """Chase email should start as draft (human-in-the-loop)."""
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_overdue_event])
        assert emails[0].status == EmailStatus.DRAFT

    def test_overdue_email_subject_contains_invoice_number(self, sample_overdue_event):
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_overdue_event])
        assert sample_overdue_event.invoice_number in emails[0].subject

    def test_overdue_email_subject_contains_vendor_name(self, sample_overdue_event):
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_overdue_event])
        assert sample_overdue_event.vendor_name in emails[0].subject

    def test_overdue_email_body_contains_amount(self, sample_overdue_event):
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_overdue_event])
        assert f"RM {sample_overdue_event.amount:.2f}" in emails[0].body

    def test_overdue_email_body_contains_due_date(self, sample_overdue_event):
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_overdue_event])
        assert sample_overdue_event.due_date in emails[0].body

    def test_email_linked_to_task(self, sample_overdue_event):
        """The task should have a related_email_id linking to the chase email."""
        gen = TaskGenerator()
        tasks, emails = gen.process_exceptions([sample_overdue_event])
        assert tasks[0].related_email_id == emails[0].email_id


class TestDuplicateHandling:
    """Tests for duplicate event handling."""

    def test_duplicate_task_has_p1_priority(self, sample_duplicate_event):
        """Duplicates should get P1_CRITICAL priority."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_duplicate_event])
        assert tasks[0].priority == Priority.P1_CRITICAL

    def test_duplicate_task_title_starts_with_VERIFY(self, sample_duplicate_event):
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_duplicate_event])
        assert tasks[0].title.startswith("VERIFY")

    def test_duplicate_does_not_generate_email(self, sample_duplicate_event):
        """Duplicates should NOT generate chase emails."""
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_duplicate_event])
        assert len(emails) == 0


class TestEscalationHandling:
    """Tests for escalation event handling."""

    def test_escalation_default_p2(self, sample_small_amount_event):
        """Small amount escalations should be P2_HIGH."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_small_amount_event])
        assert tasks[0].priority == Priority.P2_HIGH

    def test_escalation_large_amount_p1(self, sample_escalation_event):
        """Large amount (>= RM 10,000) escalations should be P1_CRITICAL."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_escalation_event])
        assert tasks[0].priority == Priority.P1_CRITICAL

    def test_escalation_does_not_generate_email(self, sample_escalation_event):
        """Escalations should NOT generate chase emails."""
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_escalation_event])
        assert len(emails) == 0

    def test_rm_500_does_not_trigger_high_priority(self, sample_small_amount_event):
        """Amount RM 500 is below the RM 10,000 escalation threshold."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_small_amount_event])
        # Should be P2, NOT P1
        assert tasks[0].priority == Priority.P2_HIGH
        assert tasks[0].priority != Priority.P1_CRITICAL


class TestFlaggedHandling:
    """Tests for flagged document handling."""

    def test_low_confidence_gets_p3(self, sample_flagged_event_low_confidence):
        """Confidence below 0.70 should get P3_MEDIUM priority."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_flagged_event_low_confidence])
        assert tasks[0].priority == Priority.P3_MEDIUM

    def test_ok_confidence_gets_p4(self, sample_flagged_event_ok_confidence):
        """Confidence >= 0.70 but still flagged should get P4_LOW."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_flagged_event_ok_confidence])
        assert tasks[0].priority == Priority.P4_LOW

    def test_flagged_does_not_generate_email(
        self, sample_flagged_event_low_confidence
    ):
        """Flagged documents should NOT generate chase emails."""
        gen = TaskGenerator()
        _, emails = gen.process_exceptions([sample_flagged_event_low_confidence])
        assert len(emails) == 0

    def test_confidence_mentioned_in_description(
        self, sample_flagged_event_low_confidence
    ):
        """The OCR confidence should be mentioned in the task description."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions([sample_flagged_event_low_confidence])
        assert "0.65" in tasks[0].description or "65%" in tasks[0].description


class TestDuplicatePrecedenceRule:
    """Test the key rule: duplicate check takes precedence over overdue chase."""

    def test_duplicate_processed_before_overdue(
        self, sample_duplicate_event, sample_overdue_event
    ):
        """When both duplicate and overdue exist, duplicate should be first."""
        gen = TaskGenerator()
        # Insert overdue first, but duplicate should come out first
        tasks, _ = gen.process_exceptions([
            sample_overdue_event,
            sample_duplicate_event,
        ])
        assert tasks[0].event_type == EventType.DUPLICATE
        assert tasks[1].event_type == EventType.OVERDUE

    def test_same_invoice_duplicate_and_overdue_duplicate_wins(self):
        """If the same invoice has both duplicate and overdue, duplicate wins."""
        gen = TaskGenerator()
        events = [
            ExceptionEvent(
                event_type=EventType.OVERDUE,
                invoice_number="INV-DUAL-001",
                vendor_name="Dual Vendor",
                amount=5000.00,
                due_date="2026-10-01",
                details="Overdue payment",
            ),
            ExceptionEvent(
                event_type=EventType.DUPLICATE,
                invoice_number="INV-DUAL-001",
                vendor_name="Dual Vendor",
                amount=5000.00,
                details="Duplicate entry detected",
                duplicate_of="INV-DUAL-001 (original)",
            ),
        ]
        tasks, _ = gen.process_exceptions(events)
        # Duplicate should be first (P1 < P2)
        assert tasks[0].event_type == EventType.DUPLICATE
        assert tasks[0].priority == Priority.P1_CRITICAL


class TestBatchProcessing:
    """Tests for processing multiple exceptions at once."""

    def test_all_event_types_processed(self, all_sample_events):
        """All event types should be processed correctly in a batch."""
        gen = TaskGenerator()
        tasks, emails = gen.process_exceptions(all_sample_events)

        event_types = {t.event_type for t in tasks}
        assert EventType.DUPLICATE in event_types
        assert EventType.OVERDUE in event_types
        assert EventType.ESCALATION in event_types
        assert EventType.FLAGGED in event_types

    def test_emails_only_for_overdue(self, all_sample_events):
        """Chase emails should only be generated for overdue events."""
        gen = TaskGenerator()
        _, emails = gen.process_exceptions(all_sample_events)
        # Count overdue events in the input
        overdue_count = sum(
            1 for e in all_sample_events if e.event_type == EventType.OVERDUE
        )
        assert len(emails) == overdue_count

    def test_duplicate_comes_first_in_batch(self, all_sample_events):
        """In a mixed batch, duplicates should always be processed first."""
        gen = TaskGenerator()
        tasks, _ = gen.process_exceptions(all_sample_events)
        assert tasks[0].event_type == EventType.DUPLICATE
