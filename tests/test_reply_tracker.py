"""Tests for the Reply Tracker module."""

from __future__ import annotations

import pytest

from src.models import (
    ChaseEmail,
    EmailStatus,
    EventType,
    Priority,
    ReplyRecord,
    ReplyStatus,
    Task,
    TaskStatus,
)
from src.reply_tracker import ReplyTracker


@pytest.fixture
def tracker(tmp_path):
    """Create a ReplyTracker in mock mode with temp data file."""
    return ReplyTracker(mock=True, data_path=tmp_path / "replies.json")


@pytest.fixture
def chase_emails():
    """Sample chase emails for testing."""
    return [
        ChaseEmail(
            email_id="EMAIL-0001",
            to="finance@creativeagency.com.my",
            subject="Outstanding Payment — Invoice INV-CA-2026-078 — Creative Agency Sdn Bhd",
            body="Please remit payment...",
            status=EmailStatus.SENT,
            related_invoice="INV-CA-2026-078",
            related_task_id="TASK-0002",
        ),
        ChaseEmail(
            email_id="EMAIL-0002",
            to="billing@globallogistics.com.my",
            subject="Outstanding Payment — Invoice SHP-2026-045 — Global Logistics",
            body="Please remit payment...",
            status=EmailStatus.SENT,
            related_invoice="SHP-2026-045",
            related_task_id="TASK-0004",
        ),
        ChaseEmail(
            email_id="EMAIL-0003",
            to="unknown@vendor.com",
            subject="Outstanding Payment — Invoice INV-999",
            body="Please remit payment...",
            status=EmailStatus.SENT,
            related_invoice="INV-999",
            related_task_id="TASK-0009",
        ),
    ]


@pytest.fixture
def tasks():
    """Sample tasks for testing."""
    return [
        Task(
            task_id="TASK-0002",
            title="Chase overdue payment",
            description="Overdue invoice",
            priority=Priority.P2_HIGH,
            event_type=EventType.OVERDUE,
            invoice_number="INV-CA-2026-078",
            vendor_name="Creative Agency",
            amount=4800.00,
            action_required="Follow up",
            status=TaskStatus.PENDING,
        ),
        Task(
            task_id="TASK-0004",
            title="Chase overdue payment",
            description="Overdue invoice",
            priority=Priority.P2_HIGH,
            event_type=EventType.OVERDUE,
            invoice_number="SHP-2026-045",
            vendor_name="Global Logistics",
            amount=3200.00,
            action_required="Follow up",
            status=TaskStatus.PENDING,
        ),
    ]


class TestReplyDetection:
    """Tests for reply status detection from content."""

    def test_detect_payment_confirmed(self):
        """Should detect payment confirmation."""
        status = ReplyTracker.detect_reply_status(
            "Re: Payment", "We have processed the payment for this invoice."
        )
        assert status == ReplyStatus.PAYMENT_CONFIRMED

    def test_detect_payment_transferred(self):
        """Should detect bank transfer as payment."""
        status = ReplyTracker.detect_reply_status(
            "Re: Invoice", "Funds transferred to your account yesterday."
        )
        assert status == ReplyStatus.PAYMENT_CONFIRMED

    def test_detect_dispute(self):
        """Should detect dispute."""
        status = ReplyTracker.detect_reply_status(
            "Re: Invoice", "We dispute the charges. The amount is incorrect."
        )
        assert status == ReplyStatus.DISPUTED

    def test_detect_overcharged(self):
        """Should detect overcharged as dispute."""
        status = ReplyTracker.detect_reply_status(
            "Re: Payment", "We were overcharged for this service."
        )
        assert status == ReplyStatus.DISPUTED

    def test_detect_acknowledgment(self):
        """Should detect acknowledgment."""
        status = ReplyTracker.detect_reply_status(
            "Re: Invoice", "Received, thank you. We are looking into this."
        )
        assert status == ReplyStatus.REPLIED

    def test_detect_general_reply(self):
        """Should default to REPLIED for generic responses."""
        status = ReplyTracker.detect_reply_status(
            "Re: Invoice", "Hello, we received your email."
        )
        assert status == ReplyStatus.REPLIED

    def test_payment_takes_priority_over_dispute(self):
        """Payment keywords should be checked before dispute."""
        # If both keywords present, payment wins
        status = ReplyTracker.detect_reply_status(
            "Re: Invoice",
            "We have paid the invoice but dispute the additional charges."
        )
        assert status == ReplyStatus.PAYMENT_CONFIRMED


class TestMockCheckReplies:
    """Tests for mock reply checking."""

    def test_mock_returns_replies(self, tracker, chase_emails):
        """Mock mode should return replies for matching emails."""
        replies = tracker.check_replies(chase_emails)
        assert len(replies) > 0

    def test_mock_reply_count(self, tracker, chase_emails):
        """Should return 2 mock replies for 3 emails."""
        replies = tracker.check_replies(chase_emails)
        assert len(replies) == 2

    def test_mock_reply_has_id(self, tracker, chase_emails):
        """Each reply should have a reply_id."""
        replies = tracker.check_replies(chase_emails)
        for r in replies:
            assert r.reply_id.startswith("REP-")

    def test_mock_reply_has_status(self, tracker, chase_emails):
        """Replies should have detected statuses."""
        replies = tracker.check_replies(chase_emails)
        statuses = {r.detected_status for r in replies}
        assert ReplyStatus.PAYMENT_CONFIRMED in statuses
        assert ReplyStatus.DISPUTED in statuses

    def test_mock_reply_has_vendor_email(self, tracker, chase_emails):
        """Replies should have vendor email."""
        replies = tracker.check_replies(chase_emails)
        for r in replies:
            assert r.vendor_email
            assert "@" in r.vendor_email

    def test_mock_reply_has_linked_task(self, tracker, chase_emails):
        """Replies should link to task IDs."""
        replies = tracker.check_replies(chase_emails)
        for r in replies:
            assert r.linked_task_id
            assert r.linked_task_id.startswith("TASK-")

    def test_mock_reply_has_date(self, tracker, chase_emails):
        """Replies should have a date."""
        replies = tracker.check_replies(chase_emails)
        for r in replies:
            assert r.reply_date

    def test_mock_reply_has_snippet(self, tracker, chase_emails):
        """Replies should have a body snippet."""
        replies = tracker.check_replies(chase_emails)
        for r in replies:
            assert r.reply_snippet


class TestTaskStatusUpdate:
    """Tests for updating task status based on replies."""

    def test_payment_confirmed_marks_done(self, tracker, tasks):
        """Payment confirmed should mark task as DONE."""
        reply = ReplyRecord(
            reply_id="REP-001",
            chase_email_id="EMAIL-0001",
            vendor_email="test@vendor.com",
            reply_date="2026-10-08T10:00:00",
            reply_subject="Re: Payment",
            detected_status=ReplyStatus.PAYMENT_CONFIRMED,
            linked_task_id="TASK-0002",
        )
        updated = tracker.update_task_status(reply, tasks)
        assert updated is not None
        assert updated.status == TaskStatus.DONE

    def test_dispute_marks_in_progress(self, tracker, tasks):
        """Dispute should mark task as IN_PROGRESS."""
        reply = ReplyRecord(
            reply_id="REP-002",
            chase_email_id="EMAIL-0002",
            vendor_email="test@vendor.com",
            reply_date="2026-10-09T10:00:00",
            reply_subject="Re: Dispute",
            detected_status=ReplyStatus.DISPUTED,
            linked_task_id="TASK-0004",
        )
        updated = tracker.update_task_status(reply, tasks)
        assert updated is not None
        assert updated.status == TaskStatus.IN_PROGRESS

    def test_replied_leaves_pending(self, tracker, tasks):
        """General reply should leave task as PENDING."""
        reply = ReplyRecord(
            reply_id="REP-003",
            chase_email_id="EMAIL-0001",
            vendor_email="test@vendor.com",
            reply_date="2026-10-08T10:00:00",
            reply_subject="Re: Acknowledged",
            detected_status=ReplyStatus.REPLIED,
            linked_task_id="TASK-0002",
        )
        updated = tracker.update_task_status(reply, tasks)
        assert updated is not None
        assert updated.status == TaskStatus.PENDING

    def test_task_not_found(self, tracker, tasks):
        """Should return None if task not found."""
        reply = ReplyRecord(
            reply_id="REP-004",
            chase_email_id="EMAIL-009",
            vendor_email="test@vendor.com",
            reply_date="2026-10-08T10:00:00",
            reply_subject="Re: Test",
            detected_status=ReplyStatus.PAYMENT_CONFIRMED,
            linked_task_id="TASK-9999",
        )
        assert tracker.update_task_status(reply, tasks) is None


class TestQueries:
    """Tests for query methods."""

    def test_get_all_replies(self, tracker, chase_emails):
        """Should return all detected replies."""
        tracker.check_replies(chase_emails)
        all_replies = tracker.get_all_replies()
        assert len(all_replies) == 2

    def test_get_by_status(self, tracker, chase_emails):
        """Should filter by status."""
        tracker.check_replies(chase_emails)
        paid = tracker.get_by_status(ReplyStatus.PAYMENT_CONFIRMED)
        assert len(paid) == 1
        disputed = tracker.get_by_status(ReplyStatus.DISPUTED)
        assert len(disputed) == 1

    def test_get_payment_confirmations(self, tracker, chase_emails):
        """Should return only payment confirmations."""
        tracker.check_replies(chase_emails)
        paid = tracker.get_payment_confirmations()
        assert len(paid) == 1
        assert all(r.detected_status == ReplyStatus.PAYMENT_CONFIRMED for r in paid)

    def test_get_disputes(self, tracker, chase_emails):
        """Should return only disputes."""
        tracker.check_replies(chase_emails)
        disputes = tracker.get_disputes()
        assert len(disputes) == 1
        assert all(r.detected_status == ReplyStatus.DISPUTED for r in disputes)

    def test_get_pending_replies(self, tracker, chase_emails):
        """Should return emails without replies."""
        tracker.check_replies(chase_emails)
        pending = tracker.get_pending_replies(chase_emails)
        # 3 emails, 2 replied → 1 pending
        assert len(pending) == 1
        assert pending[0].email_id == "EMAIL-0003"


class TestFormatting:
    """Tests for output formatting."""

    def test_format_replies(self, tracker, chase_emails):
        """Should format replies as readable text."""
        replies = tracker.check_replies(chase_emails)
        output = tracker.format_replies(replies)
        assert "REPLY TRACKER" in output
        assert "2" in output
        assert "[PAID]" in output or "[DISPUTE]" in output

    def test_format_replies_empty(self, tracker):
        """Should handle no replies."""
        output = tracker.format_replies()
        assert "No replies" in output

    def test_format_summary(self, tracker, chase_emails):
        """Should format a summary."""
        tracker.check_replies(chase_emails)
        output = tracker.format_summary(chase_emails)
        assert "REPLY TRACKER SUMMARY" in output
        assert "Payment confirmed" in output
        assert "Disputed" in output
        assert "Pending" in output
