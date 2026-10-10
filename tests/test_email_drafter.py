"""Tests for EmailDrafter (src/email_drafter.py).

Tests cover:
- Adding drafts to the manager
- Approval workflow (draft -> approved -> sent)
- Rejection workflow (draft -> rejected)
- Filtering by status
- Email preview formatting
"""

import pytest

from src.email_drafter import EmailDrafter
from src.models import ChaseEmail, EmailStatus
from src.task_generator import TaskGenerator


@pytest.fixture
def sample_chase_emails():
    """Generate sample chase emails using TaskGenerator."""
    from src.models import ExceptionEvent, EventType

    gen = TaskGenerator()
    events = [
        ExceptionEvent(
            event_type=EventType.OVERDUE,
            invoice_number="INV-001",
            vendor_name="Vendor One Sdn Bhd",
            amount=1000.00,
            due_date="2026-10-01",
            details="Overdue",
        ),
        ExceptionEvent(
            event_type=EventType.OVERDUE,
            invoice_number="INV-002",
            vendor_name="Vendor Two Sdn Bhd",
            amount=2000.00,
            due_date="2026-09-15",
            details="Overdue",
        ),
        ExceptionEvent(
            event_type=EventType.OVERDUE,
            invoice_number="INV-003",
            vendor_name="Vendor Three Sdn Bhd",
            amount=3000.00,
            due_date="2026-09-01",
            details="Overdue",
        ),
    ]
    _, emails = gen.process_exceptions(events)
    return emails


class TestEmailDrafterBasics:
    """Basic tests for EmailDrafter."""

    def test_empty_drafter_has_no_drafts(self):
        drafter = EmailDrafter()
        assert len(drafter.get_drafts()) == 0

    def test_add_drafts(self, sample_chase_emails):
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)
        assert len(drafter.get_drafts()) == 3


class TestApprovalWorkflow:
    """Tests for the email approval workflow."""

    def test_approve_draft(self, sample_chase_emails):
        """Approving a draft should change status to approved."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        email_id = sample_chase_emails[0].email_id
        approved = drafter.approve(email_id)

        assert approved is not None
        assert approved.status == EmailStatus.APPROVED

    def test_approve_nonexistent_returns_none(self, sample_chase_emails):
        """Approving a non-existent email should return None."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        result = drafter.approve("EMAIL-9999")
        assert result is None

    def test_approve_already_approved_returns_none(self, sample_chase_emails):
        """Approving an already-approved email should return None."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        email_id = sample_chase_emails[0].email_id
        drafter.approve(email_id)

        # Second approval should return None (already approved)
        result = drafter.approve(email_id)
        assert result is None

    def test_reject_draft(self, sample_chase_emails):
        """Rejecting a draft should change status to rejected."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        email_id = sample_chase_emails[1].email_id
        rejected = drafter.reject(email_id)

        assert rejected is not None
        assert rejected.status == EmailStatus.REJECTED

    def test_mark_sent(self, sample_chase_emails):
        """Marking an approved email as sent should change status to sent."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        email_id = sample_chase_emails[0].email_id
        drafter.approve(email_id)
        sent = drafter.mark_sent(email_id)

        assert sent is not None
        assert sent.status == EmailStatus.SENT

    def test_mark_sent_without_approval_fails(self, sample_chase_emails):
        """Marking a draft as sent (without approval) should fail."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        email_id = sample_chase_emails[0].email_id
        result = drafter.mark_sent(email_id)
        assert result is None


class TestStatusFiltering:
    """Tests for filtering emails by status."""

    def test_get_drafts(self, sample_chase_emails):
        """get_drafts should return only draft-status emails."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        # Approve one
        drafter.approve(sample_chase_emails[0].email_id)

        drafts = drafter.get_drafts()
        assert len(drafts) == 2
        assert all(e.status == EmailStatus.DRAFT for e in drafts)

    def test_get_approved(self, sample_chase_emails):
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        drafter.approve(sample_chase_emails[0].email_id)
        drafter.approve(sample_chase_emails[1].email_id)

        approved = drafter.get_approved()
        assert len(approved) == 2

    def test_get_rejected(self, sample_chase_emails):
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        drafter.reject(sample_chase_emails[0].email_id)

        rejected = drafter.get_rejected()
        assert len(rejected) == 1

    def test_get_sent(self, sample_chase_emails):
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        drafter.approve(sample_chase_emails[0].email_id)
        drafter.mark_sent(sample_chase_emails[0].email_id)

        sent = drafter.get_sent()
        assert len(sent) == 1


class TestApprovedCount:
    """Tests for the approved count (used in final report)."""

    def test_approved_count_includes_sent(self, sample_chase_emails):
        """get_approved_count should count both approved and sent emails."""
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)

        drafter.approve(sample_chase_emails[0].email_id)
        drafter.approve(sample_chase_emails[1].email_id)
        drafter.mark_sent(sample_chase_emails[0].email_id)

        # 1 sent + 1 approved = 2
        assert drafter.get_approved_count() == 2

    def test_approved_count_zero_when_all_drafts(self, sample_chase_emails):
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)
        assert drafter.get_approved_count() == 0


class TestFormatting:
    """Tests for email formatting."""

    def test_format_email_preview_contains_subject(self, sample_chase_emails):
        drafter = EmailDrafter()
        preview = drafter.format_email_preview(sample_chase_emails[0])
        assert sample_chase_emails[0].subject in preview

    def test_format_email_preview_contains_status(self, sample_chase_emails):
        drafter = EmailDrafter()
        preview = drafter.format_email_preview(sample_chase_emails[0])
        assert "[DRAFT]" in preview

    def test_format_all_drafts_message(self, sample_chase_emails):
        drafter = EmailDrafter()
        drafter.add_drafts(sample_chase_emails)
        output = drafter.format_all_drafts()
        assert "DRAFT EMAILS" in output
        assert "3" in output  # count

    def test_format_all_drafts_empty_message(self):
        drafter = EmailDrafter()
        output = drafter.format_all_drafts()
        assert "No draft emails" in output
