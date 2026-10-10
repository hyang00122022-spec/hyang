"""P1: Exception-to-task conversion module.

Converts ExceptionEvent objects from the Financial agent into plain-language
Task objects. Handles priority assignment and the key rule:
    duplicate check takes precedence over overdue chase.

Edge cases handled:
- confidence >= 0.70: OK, proceed normally
- confidence < 0.70: task gets P3_MEDIUM (review needed)
- amount = RM 500: does NOT trigger escalation (below LARGE_AMOUNT threshold)
- duplicate + overdue on same invoice: duplicate wins (higher priority)
"""

from __future__ import annotations

from datetime import datetime

from .config import (
    CONFIDENCE_THRESHOLD,
    PRIORITY_MAP,
)
from .models import (
    ChaseEmail,
    EmailStatus,
    ExceptionEvent,
    EventType,
    Priority,
    Task,
    TaskStatus,
)


class TaskGenerator:
    """Converts exception events to plain-language tasks."""

    def __init__(self):
        self._task_counter = 0
        self._email_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_exceptions(
        self, exceptions: list[ExceptionEvent]
    ) -> tuple[list[Task], list[ChaseEmail]]:
        """Process a batch of exceptions and return tasks + chase emails.

        This is the main entry point. It:
        1. Sorts exceptions so duplicates come first (precedence rule)
        2. Converts each exception to a task
        3. Drafts chase emails for overdue items
        4. Links emails to their related tasks

        Args:
            exceptions: List of ExceptionEvent objects from Financial agent.

        Returns:
            Tuple of (tasks, chase_emails).
        """
        if not exceptions:
            return [], []

        # Key rule: duplicate check takes precedence over overdue chase.
        # Sort so duplicates are processed first.
        sorted_exceptions = self._sort_by_priority(exceptions)

        tasks: list[Task] = []
        emails: list[ChaseEmail] = []

        for event in sorted_exceptions:
            task = self._convert_to_task(event)
            tasks.append(task)

            # Draft chase email only for overdue items
            if event.event_type == EventType.OVERDUE:
                email = self._draft_chase_email(event, task)
                emails.append(email)
                # Link email to task
                task.related_email_id = email.email_id

        return tasks, emails

    # ------------------------------------------------------------------
    # Sorting / precedence
    # ------------------------------------------------------------------

    def _sort_by_priority(
        self, exceptions: list[ExceptionEvent]
    ) -> list[ExceptionEvent]:
        """Sort exceptions so duplicates come first.

        Rule from shared rules: if an invoice has both duplicate AND overdue
        flags, duplicate takes precedence. We sort by the priority map so
        duplicates (P1) are always processed before overdue (P2).
        """
        def sort_key(event: ExceptionEvent) -> int:
            return PRIORITY_MAP.get(event.event_type.value, 99)

        return sorted(exceptions, key=sort_key)

    # ------------------------------------------------------------------
    # Task conversion
    # ------------------------------------------------------------------

    def _convert_to_task(self, event: ExceptionEvent) -> Task:
        """Convert a single exception event to a plain-language task.

        Dispatches to the appropriate handler based on event_type.
        """
        handlers = {
            EventType.OVERDUE: self._handle_overdue,
            EventType.DUPLICATE: self._handle_duplicate,
            EventType.ESCALATION: self._handle_escalation,
            EventType.FLAGGED: self._handle_flagged,
        }

        handler = handlers.get(event.event_type, self._handle_unknown)
        return handler(event)

    def _handle_overdue(self, event: ExceptionEvent) -> Task:
        """Overdue: payment due date passed, no payment record found.

        Action: Draft chase email + create follow-up task.
        Priority: P2_HIGH
        """
        self._task_counter += 1
        return Task(
            task_id=f"TASK-{self._task_counter:04d}",
            title=f"Chase overdue payment: {event.vendor_name} (RM {event.amount:.2f})",
            description=(
                f"Invoice {event.invoice_number} from {event.vendor_name} "
                f"for RM {event.amount:.2f} is overdue. "
                f"Due date: {event.due_date or 'N/A'}. "
                f"No payment record found. "
                f"Details: {event.details}"
            ),
            priority=Priority.P2_HIGH,
            event_type=EventType.OVERDUE,
            invoice_number=event.invoice_number,
            vendor_name=event.vendor_name,
            amount=event.amount,
            action_required=(
                "Review the draft chase email. Approve to send, or reject "
                "if payment has already been made."
            ),
            status=TaskStatus.PENDING,
        )

    def _handle_duplicate(self, event: ExceptionEvent) -> Task:
        """Duplicate: same vendor + amount + invoice number detected.

        Action: Verify which copy is the original, void the other.
        Priority: P1_CRITICAL (potential double payment)
        """
        self._task_counter += 1
        dup_of = event.duplicate_of or "unknown"
        return Task(
            task_id=f"TASK-{self._task_counter:04d}",
            title=f"VERIFY duplicate invoice: {event.invoice_number} (RM {event.amount:.2f})",
            description=(
                f"Invoice {event.invoice_number} from {event.vendor_name} "
                f"for RM {event.amount:.2f} appears to be a duplicate "
                f"of invoice {dup_of}. "
                f"Details: {event.details}"
            ),
            priority=Priority.P1_CRITICAL,
            event_type=EventType.DUPLICATE,
            invoice_number=event.invoice_number,
            vendor_name=event.vendor_name,
            amount=event.amount,
            action_required=(
                "Confirm which invoice is the original. "
                "Void the duplicate and update the ledger. "
                "If both were paid, request a refund from the vendor."
            ),
            status=TaskStatus.PENDING,
        )

    def _handle_escalation(self, event: ExceptionEvent) -> Task:
        """Escalation: triggered by S6 rules (large amount, tax mismatch, etc.)

        Action: Surface to management for decision.
        Priority: P2_HIGH (default), P1 if very large amount
        """
        self._task_counter += 1

        # Determine if this needs P1 (very large amounts)
        priority = Priority.P2_HIGH
        if event.amount >= 10000:
            priority = Priority.P1_CRITICAL

        reason = event.escalation_reason or event.details
        return Task(
            task_id=f"TASK-{self._task_counter:04d}",
            title=f"ESCALATION: {reason} ({event.vendor_name})",
            description=(
                f"Invoice {event.invoice_number} from {event.vendor_name} "
                f"for RM {event.amount:.2f} has been flagged for escalation. "
                f"Reason: {reason}. "
                f"Details: {event.details}"
            ),
            priority=priority,
            event_type=EventType.ESCALATION,
            invoice_number=event.invoice_number,
            vendor_name=event.vendor_name,
            amount=event.amount,
            action_required=(
                "Management review required. Approve the payment, "
                "reject it, or request additional documentation from the vendor."
            ),
            status=TaskStatus.PENDING,
        )

    def _handle_flagged(self, event: ExceptionEvent) -> Task:
        """Flagged: document quality issue or low OCR confidence.

        Action: Review the document and re-process if needed.
        Priority: P3_MEDIUM (default), P4_LOW if confidence is borderline
        """
        self._task_counter += 1

        # Confidence edge case: exactly 0.70 is OK, below is flagged
        confidence = event.confidence
        if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
            priority = Priority.P3_MEDIUM
            confidence_note = (
                f"OCR confidence is {confidence:.0%} (below {CONFIDENCE_THRESHOLD:.0%} threshold). "
            )
        elif confidence is not None:
            priority = Priority.P4_LOW
            confidence_note = f"OCR confidence is {confidence:.0%}. "
        else:
            priority = Priority.P3_MEDIUM
            confidence_note = ""

        flag_reason = event.flag_reason or event.details
        return Task(
            task_id=f"TASK-{self._task_counter:04d}",
            title=f"Review flagged document: {event.invoice_number}",
            description=(
                f"Document {event.invoice_number} from {event.vendor_name} "
                f"has been flagged. {confidence_note}"
                f"Flag reason: {flag_reason}. "
                f"Details: {event.details}"
            ),
            priority=priority,
            event_type=EventType.FLAGGED,
            invoice_number=event.invoice_number,
            vendor_name=event.vendor_name,
            amount=event.amount,
            action_required=(
                "Review the source document. If readable, re-process with "
                "manual data entry. If unreadable, request a new copy "
                "from the vendor."
            ),
            status=TaskStatus.PENDING,
        )

    def _handle_unknown(self, event: ExceptionEvent) -> Task:
        """Fallback for unrecognized event types."""
        self._task_counter += 1
        return Task(
            task_id=f"TASK-{self._task_counter:04d}",
            title=f"Review exception: {event.invoice_number}",
            description=(
                f"Unrecognized exception type '{event.event_type}' "
                f"for invoice {event.invoice_number} from {event.vendor_name}. "
                f"Details: {event.details}"
            ),
            priority=Priority.P3_MEDIUM,
            event_type=event.event_type,
            invoice_number=event.invoice_number,
            vendor_name=event.vendor_name,
            amount=event.amount,
            action_required="Manual review required.",
            status=TaskStatus.PENDING,
        )

    # ------------------------------------------------------------------
    # Chase email drafting
    # ------------------------------------------------------------------

    def _draft_chase_email(
        self, event: ExceptionEvent, task: Task
    ) -> ChaseEmail:
        """Draft a chase email for an overdue invoice.

        Secretary NEVER sends without approval — email starts as 'draft'.
        """
        self._email_counter += 1

        today = datetime.now().strftime("%d %B %Y")
        email_id = f"EMAIL-{self._email_counter:04d}"

        subject = (
            f"Outstanding Payment — Invoice {event.invoice_number} "
            f"— {event.vendor_name}"
        )

        body = self._format_email_body(
            vendor_name=event.vendor_name,
            invoice_number=event.invoice_number,
            invoice_date=event.invoice_date or "N/A",
            grand_total=f"{event.amount:.2f}",
            due_date=event.due_date or "N/A",
            today_date=today,
        )

        return ChaseEmail(
            email_id=email_id,
            to=f"accounts@{event.vendor_name.lower().replace(' ', '')}.com.my",  # placeholder
            subject=subject,
            body=body,
            status=EmailStatus.DRAFT,
            related_invoice=event.invoice_number,
            related_task_id=task.task_id,
        )

    def _format_email_body(
        self,
        vendor_name: str,
        invoice_number: str,
        invoice_date: str,
        grand_total: str,
        due_date: str,
        today_date: str,
    ) -> str:
        """Format the chase email body using the standard template."""
        from .config import BUSINESS_NAME, EMAIL_SIGNATURE

        return f"""Dear Sir/Madam,

We are writing regarding the following invoice which appears to be outstanding:

  Invoice No:  {invoice_number}
  Date:        {invoice_date}
  Amount Due:  RM {grand_total}
  Due Date:    {due_date}

As of {today_date}, we have not located a payment record for this invoice in our system. If payment has been made, kindly share the receipt or bank transfer reference so we can reconcile our records.

If payment has not yet been made, please let us know the expected payment date so we can plan accordingly.

Thank you for your prompt attention.

{EMAIL_SIGNATURE}"""
