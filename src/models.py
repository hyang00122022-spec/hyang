"""Data models for the Secretary Agent.

All agents in the pipeline share these data contracts. The Secretary consumes
ExceptionEvent objects produced by the Financial agent and produces Task,
ChaseEmail, Plan, and FinalReport objects.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Types of exception events the Financial agent can raise."""
    OVERDUE = "overdue"
    DUPLICATE = "duplicate"
    ESCALATION = "escalation"
    FLAGGED = "flagged"


class Priority(int, Enum):
    """Task priority levels. Lower number = higher priority."""
    P1_CRITICAL = 1  # duplicates, large-amount escalations
    P2_HIGH = 2       # overdue payments, tax discrepancies
    P3_MEDIUM = 3      # category mismatches, low-confidence docs
    P4_LOW = 4         # informational flags


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class EmailStatus(str, Enum):
    DRAFT = "draft"        # Secretary drafted, awaiting approval
    APPROVED = "approved"  # Owner approved, ready to send
    SENT = "sent"           # Email was sent
    REJECTED = "rejected"  # Owner dismissed the draft


class PlanPhaseStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Input models (from Financial / Logistics agents)
# ---------------------------------------------------------------------------

class ExceptionEvent(BaseModel):
    """An exception event raised by the Financial agent.

    The Secretary reads these and converts them to tasks + chase emails.
    """
    event_type: EventType
    invoice_number: str
    vendor_name: str
    amount: float = Field(ge=0, description="Amount in MYR")
    currency: str = Field(default="MYR")
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    details: str = Field(description="Human-readable description of the issue")

    # Duplicate-specific
    duplicate_of: Optional[str] = Field(
        default=None, description="Invoice number this is a duplicate of"
    )

    # Escalation-specific
    escalation_reason: Optional[str] = None
    escalation_code: Optional[str] = None

    # Flagged-specific
    flag_reason: Optional[str] = None
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="OCR confidence score from Logistics (0.0-1.0)"
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        """Round to 2 decimal places for currency."""
        return round(v, 2)


class DocumentInfo(BaseModel):
    """Document metadata from the Logistics agent."""
    doc_id: str
    file_name: str
    doc_type: str  # invoice, receipt, PO
    vendor_name: str
    invoice_number: str
    invoice_date: str
    grand_total: float
    currency: str = "MYR"
    line_items: list[dict] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    quality_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Output models (from Secretary)
# ---------------------------------------------------------------------------

class Task(BaseModel):
    """A plain-language task generated from an exception event."""
    task_id: str
    title: str
    description: str
    priority: Priority
    event_type: EventType
    invoice_number: str
    vendor_name: str
    amount: float
    action_required: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    related_email_id: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        return round(v, 2)


class ChaseEmail(BaseModel):
    """A draft chase email for an overdue invoice.

    Status starts as 'draft'. The owner must approve before sending.
    Secretary NEVER sends without approval (human-in-the-loop).
    """
    email_id: str
    to: str = Field(description="Vendor contact email (placeholder if unknown)")
    cc: Optional[str] = None
    subject: str
    body: str
    status: EmailStatus = EmailStatus.DRAFT
    related_invoice: str
    related_task_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


class PlanPhase(BaseModel):
    """A single phase in the execution plan."""
    phase: int
    agent: str  # "Logistics", "Financial", "Secretary"
    action: str
    status: PlanPhaseStatus = PlanPhaseStatus.PENDING


class Plan(BaseModel):
    """The execution plan generated by the Secretary (P0)."""
    goal: str
    phases: list[PlanPhase]
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
    total_phases: int = Field(default=0)

    def model_post_init(self, __context) -> None:
        if self.total_phases == 0:
            self.total_phases = len(self.phases)


class CategorySummary(BaseModel):
    """Spending summary for a single category."""
    category: str
    total: float
    count: int


class FinalReport(BaseModel):
    """Final report produced by the Secretary (P1)."""
    goal: str
    period: str
    cash_in: float = Field(description="Total incoming (receipts)")
    cash_out: float = Field(description="Total outgoing (invoices paid)")
    net_cash: float = Field(default=0.0, description="cash_in - cash_out")
    categories: list[CategorySummary] = Field(default_factory=list)
    top_3_actions: list[str] = Field(default_factory=list)
    total_exceptions: int = 0
    tasks_generated: int = 0
    chase_emails_drafted: int = 0
    chase_emails_approved: int = 0
    generated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )

    def model_post_init(self, __context) -> None:
        self.net_cash = round(self.cash_in - self.cash_out, 2)


# ---------------------------------------------------------------------------
# Gmail crawler models
# ---------------------------------------------------------------------------

class AttachmentInfo(BaseModel):
    """Metadata for a single email attachment."""
    filename: str
    mime_type: str = "application/octet-stream"
    size: int = Field(default=0, description="Size in bytes")
    attachment_id: str = Field(default="")
    downloaded: bool = False
    local_path: Optional[str] = None

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: int) -> int:
        return max(v, 0)


class RawEmailDocument(BaseModel):
    """An email fetched from Gmail that may contain invoice/receipt/PO attachments.

    The GmailCrawler produces these. The Logistics agent (or a pre-processing
    step) can then OCR the downloaded attachments and convert them to
    DocumentInfo objects for the rest of the pipeline.
    """
    message_id: str = Field(description="Gmail message ID")
    thread_id: str = Field(default="")
    sender: str = Field(description="Full sender header, e.g. 'Vendor <a@b.com>'")
    sender_email: str = Field(description="Extracted email address")
    subject: str
    date: str = Field(description="Email date in ISO format")
    body_snippet: str = Field(default="", description="First ~200 chars of body")
    has_attachment: bool = True
    attachments: list[AttachmentInfo] = Field(default_factory=list)
    downloaded_files: list[str] = Field(
        default_factory=list,
        description="Local file paths of downloaded attachments",
    )
    detected_doc_type: str = Field(
        default="unknown",
        description="invoice, receipt, PO, or unknown (from subject/filename)",
    )
    vendor_name: str = Field(
        default="",
        description="Vendor name extracted from sender or subject",
    )
    processed_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )

    def to_summary(self) -> str:
        """One-line summary for display."""
        att_count = len(self.attachments)
        return (
            f"[{self.message_id}] {self.date} | {self.vendor_name} | "
            f"{self.subject[:50]} | {self.detected_doc_type} | "
            f"{att_count} attachment(s)"
        )


# ---------------------------------------------------------------------------
# Vendor Master Database models
# ---------------------------------------------------------------------------

class VendorInfo(BaseModel):
    """A vendor record in the master vendor database.

    Centralizes contact info, payment terms, and invoice history so the
    pipeline doesn't need to re-derive this from emails every time.
    """
    vendor_id: str
    name: str
    email: str = ""
    phone: Optional[str] = None
    payment_terms_days: int = Field(default=30, ge=0)
    category_code: str = Field(default="OFC", description="Default S5 category")
    tax_id: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    first_invoice_date: Optional[str] = None
    total_invoices: int = Field(default=0, ge=0)
    total_amount: float = Field(default=0.0, ge=0)
    is_new_vendor: bool = Field(default=True, description="True if <2 prior invoices")
    notes: str = ""

    @field_validator("total_amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        return round(v, 2)

    def to_summary(self) -> str:
        """One-line summary."""
        new_flag = " [NEW]" if self.is_new_vendor else ""
        return (
            f"[{self.vendor_id}] {self.name}{new_flag} | "
            f"{self.payment_terms_days}d terms | "
            f"{self.total_invoices} invoices | "
            f"RM {self.total_amount:.2f} total"
        )


# ---------------------------------------------------------------------------
# Audit Log models
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    """A single audit log entry tracking a state change in the pipeline."""
    entry_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    action: str = Field(description="created, updated, approved, rejected, sent, exported, etc.")
    entity_type: str = Field(description="task, email, report, vendor, document, reply")
    entity_id: str
    description: str
    actor: str = Field(default="system", description="Who/what performed the action")


# ---------------------------------------------------------------------------
# Chase Email Reply Tracking models
# ---------------------------------------------------------------------------

class ReplyStatus(str, Enum):
    """Status of a vendor's reply to a chase email."""
    NO_REPLY = "no_reply"
    REPLIED = "replied"
    PAYMENT_CONFIRMED = "payment_confirmed"
    DISPUTED = "disputed"


class ReplyRecord(BaseModel):
    """A reply from a vendor to a chase email, detected and parsed."""
    reply_id: str
    chase_email_id: str
    vendor_email: str
    reply_date: str
    reply_subject: str
    reply_snippet: str = Field(default="")
    detected_status: ReplyStatus = ReplyStatus.REPLIED
    linked_task_id: str
    processed_at: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


# ---------------------------------------------------------------------------
# Scheduler models
# ---------------------------------------------------------------------------

class ScheduleFrequency(str, Enum):
    """Frequency options for scheduled pipeline runs."""
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"


class ScheduleConfig(BaseModel):
    """Configuration for automated/scheduled pipeline runs."""
    frequency: ScheduleFrequency = ScheduleFrequency.MONTHLY
    day_of_month: Optional[int] = Field(default=1, ge=1, le=31, description="For monthly: day of month (1-31)")
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6, description="For weekly: 0=Monday")
    time: str = Field(default="09:00", description="HH:MM in 24h format")
    goal: str = Field(default="Close out current month")
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None


# ---------------------------------------------------------------------------
# Pipeline result (aggregate output)
# ---------------------------------------------------------------------------

class PipelineResult(BaseModel):
    """Complete output of the Secretary's pipeline run."""
    plan: Plan
    tasks: list[Task] = Field(default_factory=list)
    chase_emails: list[ChaseEmail] = Field(default_factory=list)
    final_report: Optional[FinalReport] = None
    exceptions_processed: int = 0
    warnings: list[str] = Field(default_factory=list)
    audit_entries: list[AuditEntry] = Field(default_factory=list)
    vendor_updates: list[VendorInfo] = Field(default_factory=list)
    reply_records: list[ReplyRecord] = Field(default_factory=list)
