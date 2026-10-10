"""P2: Chase email drafting module.

Provides utilities for managing chase email drafts. The actual email body
generation happens in TaskGenerator._draft_chase_email(); this module
provides higher-level operations like batch formatting, approval workflow,
and email-to-task linkage checks.
"""

from __future__ import annotations

from datetime import datetime

from .models import ChaseEmail, EmailStatus
from .config import BUSINESS_NAME, BUSINESS_EMAIL


class EmailDrafter:
    """Manages chase email drafts and approval workflow.

    The Secretary drafts emails but NEVER sends without owner approval.
    This class provides the approval/rejection workflow.
    """

    def __init__(self):
        self.emails: list[ChaseEmail] = []

    def add_drafts(self, emails: list[ChaseEmail]) -> None:
        """Add drafted emails to the manager."""
        self.emails.extend(emails)

    def approve(self, email_id: str) -> ChaseEmail | None:
        """Approve a draft email for sending.

        Args:
            email_id: The ID of the email to approve.

        Returns:
            The updated email if found, None otherwise.
        """
        for email in self.emails:
            if email.email_id == email_id and email.status == EmailStatus.DRAFT:
                email.status = EmailStatus.APPROVED
                return email
        return None

    def reject(self, email_id: str) -> ChaseEmail | None:
        """Reject (dismiss) a draft email.

        Args:
            email_id: The ID of the email to reject.

        Returns:
            The updated email if found, None otherwise.
        """
        for email in self.emails:
            if email.email_id == email_id and email.status == EmailStatus.DRAFT:
                email.status = EmailStatus.REJECTED
                return email
        return None

    def mark_sent(self, email_id: str) -> ChaseEmail | None:
        """Mark an approved email as sent.

        Args:
            email_id: The ID of the email to mark as sent.

        Returns:
            The updated email if found, None otherwise.
        """
        for email in self.emails:
            if email.email_id == email_id and email.status == EmailStatus.APPROVED:
                email.status = EmailStatus.SENT
                return email
        return None

    def get_drafts(self) -> list[ChaseEmail]:
        """Return all emails that are still in draft status."""
        return [e for e in self.emails if e.status == EmailStatus.DRAFT]

    def get_approved(self) -> list[ChaseEmail]:
        """Return all emails that have been approved (ready to send)."""
        return [e for e in self.emails if e.status == EmailStatus.APPROVED]

    def get_sent(self) -> list[ChaseEmail]:
        """Return all emails that have been sent."""
        return [e for e in self.emails if e.status == EmailStatus.SENT]

    def get_rejected(self) -> list[ChaseEmail]:
        """Return all emails that were rejected."""
        return [e for e in self.emails if e.status == EmailStatus.REJECTED]

    def get_approved_count(self) -> int:
        """Count of approved emails (for final report)."""
        return len(self.get_approved()) + len(self.get_sent())

    def format_email_preview(self, email: ChaseEmail) -> str:
        """Format an email for preview in the frontend.

        Args:
            email: The ChaseEmail to format.

        Returns:
            Formatted string for display.
        """
        status_icon = {
            EmailStatus.DRAFT: "[DRAFT]",
            EmailStatus.APPROVED: "[APPROVED]",
            EmailStatus.SENT: "[SENT]",
            EmailStatus.REJECTED: "[REJECTED]",
        }.get(email.status, "[?]")

        return (
            f"{'=' * 60}\n"
            f"  {status_icon} {email.email_id}\n"
            f"  Invoice: {email.related_invoice}\n"
            f"  Task:    {email.related_task_id}\n"
            f"{'=' * 60}\n"
            f"  To:      {email.to}\n"
            f"  Subject: {email.subject}\n"
            f"{'-' * 60}\n"
            f"{email.body}\n"
            f"{'=' * 60}\n"
        )

    def format_all_drafts(self) -> str:
        """Format all draft emails for the 'Draft Emails' section."""
        drafts = self.get_drafts()
        if not drafts:
            return "No draft emails pending approval."

        lines = [f"DRAFT EMAILS ({len(drafts)} pending approval)\n"]
        for email in drafts:
            lines.append(self.format_email_preview(email))
        return "\n".join(lines)
