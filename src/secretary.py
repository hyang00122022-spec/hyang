"""Main Secretary agent orchestrator.

Ties together all modules:
  P0: Planner  — read goal, write plan, dispatch
  P1: TaskGenerator + Reporter — exceptions -> tasks, final report
  P2: EmailDrafter — chase emails for approval

This is the entry point for the full pipeline. It simulates the dispatch
to Logistics and Financial (in a real system, those would be separate agents
that communicate via message passing).

Usage:
    from src.secretary import Secretary

    secretary = Secretary()
    result = secretary.run(
        goal="Close out September",
        exceptions=financial_exceptions,
        documents=logistics_documents,
    )
    print(result)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import BUSINESS_NAME, BUSINESS_CURRENCY
from .email_drafter import EmailDrafter
from .audit_logger import AuditLogger
from .models import (
    DocumentInfo,
    ExceptionEvent,
    PipelineResult,
    Plan,
)
from .planner import Planner
from .reporter import Reporter
from .task_generator import TaskGenerator
from .vendor_manager import VendorManager


class Secretary:
    """Main Secretary agent that orchestrates the full pipeline.

    The Secretary:
    1. Reads the goal and writes an execution plan (P0)
    2. Dispatches to Logistics (document collection) and Financial (reconciliation)
    3. Receives exceptions from Financial and converts to tasks (P1)
    4. Drafts chase emails for overdue items (P2)
    5. Generates a final report (P1)

    In this standalone implementation, Logistics and Financial outputs are
    provided as input (simulating the dispatch results).
    """

    def __init__(self):
        self.planner = Planner()
        self.task_generator = TaskGenerator()
        self.email_drafter = EmailDrafter()
        self.reporter = Reporter()
        self.audit_logger = AuditLogger()
        self.vendor_manager = VendorManager()

    def run(
        self,
        goal: str,
        exceptions: list[ExceptionEvent] | None = None,
        documents: list[DocumentInfo] | None = None,
        auto_approve_emails: bool = False,
    ) -> PipelineResult:
        """Run the full Secretary pipeline.

        Args:
            goal: The business goal, e.g. "Close out September".
            exceptions: Exception events from the Financial agent.
            documents: Document info from the Logistics agent.
            auto_approve_emails: If True, auto-approve all chase emails
                (for testing only — never do this in production).

        Returns:
            A PipelineResult containing the plan, tasks, emails, and report.
        """
        exceptions = exceptions or []
        documents = documents or []
        warnings: list[str] = []
        audit_entries: list = []

        # ---------------------------------------------------------------
        # P0: Generate plan
        # ---------------------------------------------------------------
        plan = self.planner.generate_plan(goal)
        audit_entries.append(self.audit_logger.log(
            "created", "plan", "PLAN",
            f"Generated execution plan for: {goal}",
        ))

        # ---------------------------------------------------------------
        # P1 + P2: Process exceptions -> tasks + chase emails
        # ---------------------------------------------------------------
        tasks, chase_emails = self.task_generator.process_exceptions(
            exceptions
        )

        # Log task creation
        for task in tasks:
            audit_entries.append(self.audit_logger.log(
                "created", "task", task.task_id,
                f"Created {task.priority.name} task: {task.title}",
            ))

        # Log chase email creation
        for email in chase_emails:
            audit_entries.append(self.audit_logger.log(
                "created", "email", email.email_id,
                f"Drafted chase email for {email.related_invoice}",
            ))

        # Update vendor database with invoice info from exceptions
        vendor_updates: list = []
        for exc in exceptions:
            vendor = self.vendor_manager.add_or_update_vendor(
                name=exc.vendor_name,
                invoice_amount=exc.amount,
                invoice_date=exc.invoice_date,
            )
            vendor_updates.append(vendor)

        # Add emails to the drafter for approval workflow
        self.email_drafter.add_drafts(chase_emails)

        # Auto-approve for testing (NOT recommended in production)
        if auto_approve_emails:
            for email in chase_emails:
                self.email_drafter.approve(email.email_id)
            warnings.append(
                "Auto-approved all chase emails (testing mode). "
                "In production, emails require manual approval."
            )

        # ---------------------------------------------------------------
        # P1: Generate final report
        # ---------------------------------------------------------------
        final_report = self.reporter.generate(
            goal=goal,
            documents=documents,
            tasks=tasks,
            chase_emails=chase_emails,
            exceptions_count=len(exceptions),
        )

        if final_report:
            audit_entries.append(self.audit_logger.log(
                "created", "report", "RPT",
                f"Generated final report: {goal}",
            ))

        # ---------------------------------------------------------------
        # Assemble result
        # ---------------------------------------------------------------
        return PipelineResult(
            plan=plan,
            tasks=tasks,
            chase_emails=chase_emails,
            final_report=final_report,
            exceptions_processed=len(exceptions),
            warnings=warnings,
            audit_entries=audit_entries,
            vendor_updates=vendor_updates,
        )

    # ------------------------------------------------------------------
    # Dispatch simulation (for standalone mode)
    # ------------------------------------------------------------------

    def dispatch_to_logistics(self, file_paths: list[str]) -> list[DocumentInfo]:
        """Simulate dispatching to the Logistics agent.

        In production, this would send a message to the Logistics agent
        with the file paths and receive extracted document data back.
        Here we load from a JSON file or create sample data.

        Args:
            file_paths: List of document file paths to process.

        Returns:
            List of DocumentInfo objects.
        """
        if not file_paths:
            return self._sample_documents()

        documents = []
        for path in file_paths:
            p = Path(path)
            if p.exists() and p.suffix == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        documents.append(DocumentInfo(**item))
                else:
                    documents.append(DocumentInfo(**data))
        return documents

    def dispatch_to_financial(
        self, documents: list[DocumentInfo]
    ) -> list[ExceptionEvent]:
        """Simulate dispatching to the Financial agent.

        In production, this would send documents to the Financial agent
        and receive exception events back. Here we load from a JSON file
        or use sample data.

        Args:
            documents: Documents from Logistics.

        Returns:
            List of ExceptionEvent objects.
        """
        return self._sample_exceptions()

    # ------------------------------------------------------------------
    # Sample data (for demo mode)
    # ------------------------------------------------------------------

    def _sample_documents(self) -> list[DocumentInfo]:
        """Generate sample documents for demo mode."""
        return [
            DocumentInfo(
                doc_id="DOC-001",
                file_name="invoice_tech_supplies.pdf",
                doc_type="invoice",
                vendor_name="Tech Supplies Sdn Bhd",
                invoice_number="INV-2026-001",
                invoice_date="2026-09-15",
                grand_total=12500.00,
                currency="MYR",
                line_items=[
                    {"description": "Laptops x5", "amount": 10000, "category": "IT"},
                    {"description": "Software licenses", "amount": 2500, "category": "IT"},
                ],
                confidence=0.95,
                quality_flags=[],
            ),
            DocumentInfo(
                doc_id="DOC-002",
                file_name="receipt_office_rent.pdf",
                doc_type="receipt",
                vendor_name="Pangsapila Management",
                invoice_number="RCT-2026-089",
                invoice_date="2026-09-01",
                grand_total=3500.00,
                currency="MYR",
                line_items=[
                    {"description": "Office rent September", "amount": 3500, "category": "RENT"},
                ],
                confidence=0.98,
                quality_flags=[],
            ),
            DocumentInfo(
                doc_id="DOC-003",
                file_name="invoice_marketing.pdf",
                doc_type="invoice",
                vendor_name="Creative Agency Sdn Bhd",
                invoice_number="INV-CA-2026-078",
                invoice_date="2026-09-20",
                grand_total=4800.00,
                currency="MYR",
                line_items=[
                    {"description": "Social media campaign", "amount": 4800, "category": "MKT"},
                ],
                confidence=0.88,
                quality_flags=[],
            ),
        ]

    def _sample_exceptions(self) -> list[ExceptionEvent]:
        """Generate sample exceptions for demo mode."""
        return [
            ExceptionEvent(
                event_type="duplicate",
                invoice_number="INV-2026-001",
                vendor_name="Tech Supplies Sdn Bhd",
                amount=12500.00,
                invoice_date="2026-09-15",
                details="Invoice number and amount match an existing entry in the ledger.",
                duplicate_of="INV-2026-001 (original entry from 2026-09-16)",
            ),
            ExceptionEvent(
                event_type="overdue",
                invoice_number="INV-CA-2026-078",
                vendor_name="Creative Agency Sdn Bhd",
                amount=4800.00,
                invoice_date="2026-09-20",
                due_date="2026-10-05",
                details="Payment was due on 2026-10-05. No payment record found in the ledger.",
            ),
            ExceptionEvent(
                event_type="escalation",
                invoice_number="INV-2026-001",
                vendor_name="Tech Supplies Sdn Bhd",
                amount=12500.00,
                details="Single invoice exceeds RM 10,000 threshold. Management approval required.",
                escalation_reason="Large amount exceeds threshold",
                escalation_code="LARGE_AMOUNT",
            ),
            ExceptionEvent(
                event_type="flagged",
                invoice_number="INV-WP-2026-032",
                vendor_name="Workshop Partners Sdn Bhd",
                amount=750.00,
                invoice_date="2026-09-22",
                details="OCR confidence is 0.65. Several line items could not be clearly read.",
                flag_reason="Low OCR confidence",
                confidence=0.65,
            ),
        ]

    # ------------------------------------------------------------------
    # Output formatting
    # ------------------------------------------------------------------

    def format_result(self, result: PipelineResult) -> str:
        """Format the entire pipeline result as human-readable text.

        Args:
            result: The PipelineResult to format.

        Returns:
            Multi-line formatted string.
        """
        lines: list[str] = []

        # Plan
        lines.append(self.planner.format_plan_text(result.plan))
        lines.append("")

        # Tasks
        if result.tasks:
            lines.append("=" * 60)
            lines.append(f"  TASK LIST ({len(result.tasks)} tasks)")
            lines.append("=" * 60)
            for task in result.tasks:
                lines.append(self._format_task(task))
            lines.append("")
        else:
            lines.append("  No tasks generated (no exceptions found).")
            lines.append("")

        # Chase emails
        if result.chase_emails:
            lines.append(self.email_drafter.format_all_drafts())
            lines.append("")
        else:
            lines.append("  No chase emails drafted.")
            lines.append("")

        # Final report
        if result.final_report:
            lines.append(self.reporter.format_report(result.final_report))

        # Warnings
        if result.warnings:
            lines.append("")
            lines.append("  WARNINGS:")
            for w in result.warnings:
                lines.append(f"    ! {w}")

        return "\n".join(lines)

    def _format_task(self, task) -> str:
        """Format a single task for display."""
        priority_label = {
            1: "P1-CRITICAL",
            2: "P2-HIGH",
            3: "P3-MEDIUM",
            4: "P4-LOW",
        }.get(task.priority.value, "UNKNOWN")

        return (
            f"\n  [{priority_label}] {task.task_id}\n"
            f"    Title:     {task.title}\n"
            f"    Invoice:   {task.invoice_number}\n"
            f"    Vendor:    {task.vendor_name}\n"
            f"    Amount:    RM {task.amount:.2f}\n"
            f"    Action:    {task.action_required}\n"
            f"    Status:    {task.status.value}\n"
        )

    # ------------------------------------------------------------------
    # JSON output
    # ------------------------------------------------------------------

    def result_to_json(self, result: PipelineResult) -> str:
        """Convert the pipeline result to a JSON string.

        Args:
            result: The PipelineResult to serialize.

        Returns:
            Pretty-printed JSON string.
        """
        return json.dumps(
            result.model_dump(),
            indent=2,
            default=str,
            ensure_ascii=False,
        )
