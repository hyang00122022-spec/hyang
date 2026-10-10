"""Export Module — exports pipeline results to CSV, JSON, Markdown, and journal formats.

Supports multiple output formats for different use cases:
  - CSV: For Excel/accounting software import
  - JSON: For API integration and data interchange
  - Markdown: For human-readable reports
  - Journal: For double-entry accounting (debit/credit format)

Usage:
    from src.exporter import Exporter
    from src.secretary import Secretary

    secretary = Secretary()
    result = secretary.run(goal="Close out September", ...)

    exporter = Exporter()
    exporter.export_csv(result, "output/september_report.csv")
    exporter.export_markdown(result, "output/september_report.md")
    exporter.export_journal(result, "output/september_journal.csv")
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Optional

from .config import BUSINESS_NAME, BUSINESS_CURRENCY, CATEGORY_CODES
from .models import (
    ChaseEmail,
    FinalReport,
    PipelineResult,
    Task,
)


class Exporter:
    """Exports pipeline results to various file formats.

    All export methods write to a file path and return the path.
    Output directory is created automatically if it doesn't exist.
    """

    def __init__(self, output_dir: Path | None = None):
        """Initialize the exporter.

        Args:
            output_dir: Default directory for exported files.
        """
        self.output_dir = output_dir

    # ------------------------------------------------------------------
    # CSV exports
    # ------------------------------------------------------------------

    def export_csv(self, result: PipelineResult, path: str | Path) -> str:
        """Export the full pipeline result as a multi-section CSV file.

        Sections:
          1. Cash Flow Summary
          2. Category Breakdown
          3. Task List
          4. Chase Emails

        Args:
            result: Pipeline result to export.
            path: Output file path.

        Returns:
            The output file path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Section 1: Cash Flow Summary
            writer.writerow(["=== CASH FLOW SUMMARY ==="])
            writer.writerow([])
            if result.final_report:
                report = result.final_report
                writer.writerow(["Goal", report.goal])
                writer.writerow(["Period", report.period])
                writer.writerow(["Cash In", f"{report.cash_in:.2f}"])
                writer.writerow(["Cash Out", f"{report.cash_out:.2f}"])
                writer.writerow(["Net Cash", f"{report.net_cash:.2f}"])
                writer.writerow(["Total Exceptions", report.total_exceptions])
                writer.writerow(["Tasks Generated", report.tasks_generated])
                writer.writerow(["Chase Emails Drafted", report.chase_emails_drafted])
                writer.writerow(["Chase Emails Approved", report.chase_emails_approved])
            writer.writerow([])

            # Section 2: Category Breakdown
            writer.writerow(["=== CATEGORY BREAKDOWN ==="])
            writer.writerow([])
            writer.writerow(["Category Code", "Category Name", "Total (MYR)", "Count"])
            if result.final_report:
                for cat in result.final_report.categories:
                    cat_name = CATEGORY_CODES.get(cat.category, cat.category)
                    writer.writerow([cat.category, cat_name, f"{cat.total:.2f}", cat.count])
            writer.writerow([])

            # Section 3: Task List
            writer.writerow(["=== TASK LIST ==="])
            writer.writerow([])
            writer.writerow([
                "Task ID", "Priority", "Title", "Invoice Number",
                "Vendor Name", "Amount (MYR)", "Action Required", "Status",
            ])
            for task in result.tasks:
                writer.writerow([
                    task.task_id,
                    f"P{task.priority.value}",
                    task.title,
                    task.invoice_number,
                    task.vendor_name,
                    f"{task.amount:.2f}",
                    task.action_required,
                    task.status.value,
                ])
            writer.writerow([])

            # Section 4: Chase Emails
            writer.writerow(["=== CHASE EMAILS ==="])
            writer.writerow([])
            writer.writerow([
                "Email ID", "To", "Subject", "Invoice", "Task ID", "Status",
            ])
            for email in result.chase_emails:
                writer.writerow([
                    email.email_id,
                    email.to,
                    email.subject,
                    email.related_invoice,
                    email.related_task_id,
                    email.status.value,
                ])

        return str(path)

    def export_journal(self, result: PipelineResult, path: str | Path) -> str:
        """Export as a double-entry accounting journal (CSV format).

        Creates journal entries for each document (invoice = expense debit,
        receipt = cash debit). This format can be imported into accounting
        software like QuickBooks, Xero, or SQL Ledger.

        Args:
            result: Pipeline result (uses final_report.categories).
            path: Output file path.

        Returns:
            The output file path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date", "Account Code", "Account Name",
                "Debit (MYR)", "Credit (MYR)", "Description", "Reference",
            ])

            if result.final_report:
                report = result.final_report
                journal_date = report.period or "2026-09-30"

                # Cash in entries (receipts → debit cash, credit revenue)
                writer.writerow([
                    journal_date, "1000", "Cash on Hand",
                    f"{report.cash_in:.2f}", "0.00",
                    f"Cash receipts for {report.period}",
                    "RECEIPTS",
                ])
                writer.writerow([
                    journal_date, "4000", "Revenue",
                    "0.00", f"{report.cash_in:.2f}",
                    f"Revenue recognized for {report.period}",
                    "RECEIPTS",
                ])

                # Category expense entries
                for cat in report.categories:
                    cat_name = CATEGORY_CODES.get(cat.category, cat.category)
                    writer.writerow([
                        journal_date, f"5{cat.category[:3]}0", f"Expense — {cat_name}",
                        f"{cat.total:.2f}", "0.00",
                        f"{cat_name} expenses ({cat.count} items)",
                        cat.category,
                    ])

                # Cash out (credit cash for payments)
                writer.writerow([
                    journal_date, "1000", "Cash on Hand",
                    "0.00", f"{report.cash_out:.2f}",
                    f"Cash payments for {report.period}",
                    "PAYMENTS",
                ])

        return str(path)

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def export_json(self, result: PipelineResult, path: str | Path) -> str:
        """Export the full pipeline result as a JSON file.

        Args:
            result: Pipeline result to export.
            path: Output file path.

        Returns:
            The output file path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                result.model_dump(),
                indent=2,
                default=str,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return str(path)

    # ------------------------------------------------------------------
    # Markdown export
    # ------------------------------------------------------------------

    def export_markdown(self, result: PipelineResult, path: str | Path) -> str:
        """Export as a formatted Markdown report.

        Args:
            result: Pipeline result to export.
            path: Output file path.

        Returns:
            The output file path.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        report = result.final_report

        # Header
        lines.append(f"# Financial Report — {report.period if report else 'N/A'}")
        lines.append("")
        lines.append(f"**Business:** {BUSINESS_NAME}")
        lines.append(f"**Goal:** {report.goal if report else result.plan.goal}")
        lines.append(f"**Generated:** {report.generated_at if report else 'N/A'}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Cash Flow
        if report:
            lines.append("## Cash Flow Summary")
            lines.append("")
            lines.append(f"| Metric | Amount ({BUSINESS_CURRENCY}) |")
            lines.append("|--------|----------|")
            lines.append(f"| Cash In | {report.cash_in:,.2f} |")
            lines.append(f"| Cash Out | {report.cash_out:,.2f} |")
            lines.append(f"| **Net Cash** | **{report.net_cash:,.2f}** |")
            lines.append("")

            # Categories
            if report.categories:
                lines.append("## Spending by Category")
                lines.append("")
                lines.append("| Category | Total (MYR) | Items |")
                lines.append("|----------|------------|-------|")
                for cat in report.categories:
                    cat_name = CATEGORY_CODES.get(cat.category, cat.category)
                    lines.append(f"| {cat_name} | {cat.total:,.2f} | {cat.count} |")
                lines.append("")

            # Top 3 Actions
            if report.top_3_actions:
                lines.append("## Top 3 Priority Actions")
                lines.append("")
                for i, action in enumerate(report.top_3_actions, 1):
                    lines.append(f"{i}. {action}")
                lines.append("")

        # Tasks
        if result.tasks:
            lines.append("## Task List")
            lines.append("")
            lines.append("| ID | Priority | Title | Vendor | Amount | Status |")
            lines.append("|-----|----------|-------|--------|--------|--------|")
            for task in result.tasks:
                lines.append(
                    f"| {task.task_id} | P{task.priority.value} | "
                    f"{task.title[:40]} | {task.vendor_name} | "
                    f"{task.amount:.2f} | {task.status.value} |"
                )
            lines.append("")

        # Chase Emails
        if result.chase_emails:
            lines.append("## Chase Emails")
            lines.append("")
            lines.append("| ID | To | Subject | Invoice | Status |")
            lines.append("|-----|-----|---------|---------|--------|")
            for email in result.chase_emails:
                lines.append(
                    f"| {email.email_id} | {email.to} | "
                    f"{email.subject[:40]} | {email.related_invoice} | "
                    f"{email.status.value} |"
                )
            lines.append("")

        # Warnings
        if result.warnings:
            lines.append("## Warnings")
            lines.append("")
            for w in result.warnings:
                lines.append(f"- {w}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    # ------------------------------------------------------------------
    # Export all formats at once
    # ------------------------------------------------------------------

    def export_all(
        self,
        result: PipelineResult,
        output_dir: str | Path,
        base_name: str = "report",
    ) -> dict[str, str]:
        """Export the result in all formats to the specified directory.

        Args:
            result: Pipeline result to export.
            output_dir: Directory to write files to.
            base_name: Base filename (without extension).

        Returns:
            Dict mapping format name to file path.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        return {
            "csv": self.export_csv(result, output_dir / f"{base_name}.csv"),
            "json": self.export_json(result, output_dir / f"{base_name}.json"),
            "markdown": self.export_markdown(result, output_dir / f"{base_name}.md"),
            "journal": self.export_journal(result, output_dir / f"{base_name}_journal.csv"),
        }
