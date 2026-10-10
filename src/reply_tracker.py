"""Chase Email Reply Tracker — detects and parses vendor replies to chase emails.

After the Secretary sends chase emails for overdue invoices, vendors may reply:
  - Confirm payment is on the way (PAYMENT_CONFIRMED)
  - Dispute the invoice amount (DISPUTED)
  - General acknowledgment (REPLIED)

This module checks for replies (via Gmail API in real mode, or mock data for
testing) and updates the linked task status accordingly.

Usage:
    from src.reply_tracker import ReplyTracker

    tracker = ReplyTracker(mock=True)
    replies = tracker.check_replies(chase_emails)
    for reply in replies:
        print(f"{reply.detected_status}: {reply.reply_subject}")
        tracker.update_task_status(reply, tasks)
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from .config import PROJECT_ROOT
from .models import ChaseEmail, ReplyRecord, ReplyStatus, Task, TaskStatus


# ---------------------------------------------------------------------------
# Mock reply data
# ---------------------------------------------------------------------------

_MOCK_REPLIES: list[dict] = [
    {
        "chase_email_id": "EMAIL-0001",
        "vendor_email": "finance@creativeagency.com.my",
        "reply_date": "2026-10-08T14:20:00+08:00",
        "reply_subject": "Re: Outstanding Payment — Invoice INV-CA-2026-078 — Creative Agency Sdn Bhd",
        "reply_snippet": "Hi, we have processed the payment for invoice INV-CA-2026-078. The funds should reach your account within 2-3 business days.",
        "detected_status": "payment_confirmed",
        "linked_task_id": "TASK-0002",
    },
    {
        "chase_email_id": "EMAIL-0002",
        "vendor_email": "billing@globallogistics.com.my",
        "reply_date": "2026-10-09T09:15:00+08:00",
        "reply_subject": "Re: Outstanding Payment — Invoice SHP-2026-045 — Global Logistics",
        "reply_snippet": "We dispute the freight charges on this invoice. The agreed rate was RM 3,200 not RM 4,500. Please review.",
        "detected_status": "disputed",
        "linked_task_id": "TASK-0004",
    },
]

# Keywords for detecting reply status
_PAYMENT_KEYWORDS = [
    "payment has been", "payment is processed", "we have paid",
    "funds transferred", "payment sent", "bank transfer",
    "will pay", "payment scheduled", "cheque issued",
    "payment made", "settled", "cleared",
    "tt done", "transfer done", "online transfer",
    "processed the payment", "processed payment",
    "payment has been made", "we've paid",
]

_DISPUTE_KEYWORDS = [
    "dispute", "incorrect", "wrong amount", "overcharged",
    "not agree", "disagree", "review the charges",
    "wrong rate", "price is wrong", "amount is incorrect",
    "contest", "challenge this invoice",
]

_ACKNOWLEDGMENT_KEYWORDS = [
    "received", "noted", "will check", "looking into",
    "thank you for", "acknowledged", "will get back",
    "reviewing", "checking on this",
]


class ReplyTracker:
    """Tracks vendor replies to chase emails and updates task statuses.

    Modes:
      - Mock mode: Returns sample reply data without real API calls.
      - Real mode: Would use Gmail API to check for replies (future).

    The reply detection logic works by analyzing the reply subject and body
    for keywords indicating payment confirmation, dispute, or acknowledgment.
    """

    def __init__(
        self,
        mock: bool = True,
        data_path: Optional[object] = None,
    ):
        """Initialize the reply tracker.

        Args:
            mock: If True, use mock data instead of real Gmail API.
            data_path: Path for persisting reply records.
        """
        self.mock = mock
        self.data_path = data_path or (PROJECT_ROOT / "replies.json")
        self._replies: list[ReplyRecord] = []
        self._load()

    def _load(self) -> None:
        """Load previously detected replies."""
        if hasattr(self.data_path, "exists") and self.data_path.exists():
            try:
                data = json.loads(self.data_path.read_text(encoding="utf-8"))
                for item in data.get("replies", []):
                    self._replies.append(ReplyRecord(**item))
            except Exception:
                pass

    def _save(self) -> None:
        """Save reply records."""
        try:
            if hasattr(self.data_path, "parent"):
                self.data_path.parent.mkdir(parents=True, exist_ok=True)
            self.data_path.write_text(
                json.dumps(
                    {
                        "replies": [r.model_dump() for r in self._replies],
                        "last_updated": datetime.now().isoformat(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Reply detection
    # ------------------------------------------------------------------

    def check_replies(
        self,
        chase_emails: list[ChaseEmail],
    ) -> list[ReplyRecord]:
        """Check for replies to the given chase emails.

        In mock mode, returns sample replies matching the provided emails.
        In real mode, would query Gmail for replies to sent chase emails.

        Args:
            chase_emails: List of sent chase emails to check for replies.

        Returns:
            List of ReplyRecord objects for detected replies.
        """
        if self.mock:
            return self._mock_check_replies(chase_emails)

        # Real mode: would use Gmail API to search for replies
        # For now, return empty (real Gmail integration is future work)
        # The reply detection logic below would be used to parse real replies
        return []

    def _mock_check_replies(
        self,
        chase_emails: list[ChaseEmail],
    ) -> list[ReplyRecord]:
        """Return mock replies matching the provided chase emails."""
        # Build a set of sent email IDs for matching
        sent_email_ids = {
            e.email_id for e in chase_emails if e.status.value == "sent"
        }
        # Also match draft/approved emails for testing
        all_email_ids = {e.email_id for e in chase_emails}

        replies: list[ReplyRecord] = []
        for mock in _MOCK_REPLIES:
            if mock["chase_email_id"] in all_email_ids or not all_email_ids:
                record = ReplyRecord(
                    reply_id=f"REP-{len(self._replies) + len(replies) + 1:04d}",
                    chase_email_id=mock["chase_email_id"],
                    vendor_email=mock["vendor_email"],
                    reply_date=mock["reply_date"],
                    reply_subject=mock["reply_subject"],
                    reply_snippet=mock["reply_snippet"],
                    detected_status=ReplyStatus(mock["detected_status"]),
                    linked_task_id=mock["linked_task_id"],
                )
                replies.append(record)
                self._replies.append(record)

        self._save()
        return replies

    # ------------------------------------------------------------------
    # Reply content analysis
    # ------------------------------------------------------------------

    @staticmethod
    def detect_reply_status(subject: str, body: str) -> ReplyStatus:
        """Analyze reply content to detect the vendor's intent.

        Args:
            subject: Reply subject line.
            body: Reply body text.

        Returns:
            Detected ReplyStatus (PAYMENT_CONFIRMED, DISPUTED, or REPLIED).
        """
        text = f"{subject} {body}".lower()

        # Check payment confirmation keywords first (highest priority)
        for keyword in _PAYMENT_KEYWORDS:
            if keyword in text:
                return ReplyStatus.PAYMENT_CONFIRMED

        # Check dispute keywords
        for keyword in _DISPUTE_KEYWORDS:
            if keyword in text:
                return ReplyStatus.DISPUTED

        # Check acknowledgment keywords
        for keyword in _ACKNOWLEDGMENT_KEYWORDS:
            if keyword in text:
                return ReplyStatus.REPLIED

        # Default: general reply
        return ReplyStatus.REPLIED

    # ------------------------------------------------------------------
    # Task status updates
    # ------------------------------------------------------------------

    def update_task_status(
        self,
        reply: ReplyRecord,
        tasks: list[Task],
    ) -> Task | None:
        """Update a task's status based on a detected reply.

        - PAYMENT_CONFIRMED → mark task as DONE
        - DISPUTED → mark task as IN_PROGRESS (needs manual review)
        - REPLIED → leave as PENDING (owner should follow up)

        Args:
            reply: The detected reply record.
            tasks: List of tasks to update.

        Returns:
            The updated Task, or None if not found.
        """
        for task in tasks:
            if task.task_id == reply.linked_task_id:
                if reply.detected_status == ReplyStatus.PAYMENT_CONFIRMED:
                    task.status = TaskStatus.DONE
                elif reply.detected_status == ReplyStatus.DISPUTED:
                    task.status = TaskStatus.IN_PROGRESS
                # REPLIED → no status change
                return task
        return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_all_replies(self) -> list[ReplyRecord]:
        """Return all detected reply records."""
        return list(self._replies)

    def get_by_status(self, status: ReplyStatus) -> list[ReplyRecord]:
        """Get replies with a specific status."""
        return [r for r in self._replies if r.detected_status == status]

    def get_payment_confirmations(self) -> list[ReplyRecord]:
        """Get replies confirming payment."""
        return self.get_by_status(ReplyStatus.PAYMENT_CONFIRMED)

    def get_disputes(self) -> list[ReplyRecord]:
        """Get disputed replies."""
        return self.get_by_status(ReplyStatus.DISPUTED)

    def get_pending_replies(
        self,
        chase_emails: list[ChaseEmail],
    ) -> list[ChaseEmail]:
        """Get chase emails that have NOT received a reply yet.

        Args:
            chase_emails: All chase emails sent.

        Returns:
            List of ChaseEmail objects with no detected reply.
        """
        replied_ids = {r.chase_email_id for r in self._replies}
        return [
            e for e in chase_emails
            if e.email_id not in replied_ids and e.status.value == "sent"
        ]

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_replies(self, replies: list[ReplyRecord] | None = None) -> str:
        """Format reply records as human-readable text."""
        replies = replies or self._replies
        if not replies:
            return "[ReplyTracker] No replies detected."

        lines = [
            "=" * 70,
            f"  REPLY TRACKER — {len(replies)} reply/replies detected",
            "=" * 70,
            "",
        ]

        for r in replies:
            status_icon = {
                ReplyStatus.PAYMENT_CONFIRMED: "[PAID]",
                ReplyStatus.DISPUTED: "[DISPUTE]",
                ReplyStatus.REPLIED: "[REPLIED]",
                ReplyStatus.NO_REPLY: "[NO REPLY]",
            }.get(r.detected_status, "[?]")

            lines.append(f"  {status_icon} {r.reply_id}")
            lines.append(f"    Chase Email: {r.chase_email_id}")
            lines.append(f"    Task:        {r.linked_task_id}")
            lines.append(f"    From:        {r.vendor_email}")
            lines.append(f"    Date:        {r.reply_date}")
            lines.append(f"    Subject:     {r.reply_subject[:60]}")
            lines.append(f"    Snippet:     {r.reply_snippet[:80]}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def format_summary(
        self,
        chase_emails: list[ChaseEmail] | None = None,
    ) -> str:
        """Format a summary of reply tracking status."""
        total = len(self._replies)
        paid = len(self.get_payment_confirmations())
        disputed = len(self.get_disputes())
        pending = len(self.get_pending_replies(chase_emails)) if chase_emails else 0

        lines = [
            "=" * 70,
            "  REPLY TRACKER SUMMARY",
            "=" * 70,
            "",
            f"  Payment confirmed: {paid}",
            f"  Disputed:          {disputed}",
            f"  General replies:   {total - paid - disputed}",
            f"  Pending (no reply): {pending}",
            "",
            "=" * 70,
        ]
        return "\n".join(lines)
