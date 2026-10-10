"""Tests for the Export module."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.exporter import Exporter
from src.models import (
    CategorySummary,
    ChaseEmail,
    EmailStatus,
    EventType,
    FinalReport,
    PipelineResult,
    Plan,
    PlanPhase,
    Priority,
    Task,
    TaskStatus,
)
from src.secretary import Secretary


@pytest.fixture
def secretary():
    return Secretary()


@pytest.fixture
def pipeline_result(secretary):
    """Generate a full pipeline result for testing."""
    return secretary.run(
        goal="Close out September",
        exceptions=secretary._sample_exceptions(),
        documents=secretary._sample_documents(),
        auto_approve_emails=True,
    )


@pytest.fixture
def exporter(tmp_path):
    return Exporter(output_dir=tmp_path)


class TestCSVExport:
    """Tests for CSV export."""

    def test_csv_creates_file(self, exporter, pipeline_result, tmp_path):
        """Should create a CSV file."""
        path = exporter.export_csv(pipeline_result, tmp_path / "report.csv")
        assert Path(path).exists()

    def test_csv_has_sections(self, exporter, pipeline_result, tmp_path):
        """CSV should contain all sections."""
        path = exporter.export_csv(pipeline_result, tmp_path / "report.csv")
        content = Path(path).read_text(encoding="utf-8")
        assert "CASH FLOW SUMMARY" in content
        assert "CATEGORY BREAKDOWN" in content
        assert "TASK LIST" in content
        assert "CHASE EMAILS" in content

    def test_csv_cash_flow(self, exporter, pipeline_result, tmp_path):
        """CSV should contain cash flow data."""
        path = exporter.export_csv(pipeline_result, tmp_path / "report.csv")
        content = Path(path).read_text(encoding="utf-8")
        assert "Cash In" in content
        assert "Cash Out" in content
        assert "Net Cash" in content

    def test_csv_tasks(self, exporter, pipeline_result, tmp_path):
        """CSV should contain task data."""
        path = exporter.export_csv(pipeline_result, tmp_path / "report.csv")
        content = Path(path).read_text(encoding="utf-8")
        assert "Task ID" in content
        assert "TASK-0001" in content
        assert "Priority" in content

    def test_csv_emails(self, exporter, pipeline_result, tmp_path):
        """CSV should contain email data."""
        path = exporter.export_csv(pipeline_result, tmp_path / "report.csv")
        content = Path(path).read_text(encoding="utf-8")
        assert "Email ID" in content
        assert "EMAIL-" in content


class TestJournalExport:
    """Tests for journal entry export."""

    def test_journal_creates_file(self, exporter, pipeline_result, tmp_path):
        """Should create a journal CSV file."""
        path = exporter.export_journal(pipeline_result, tmp_path / "journal.csv")
        assert Path(path).exists()

    def test_journal_has_header(self, exporter, pipeline_result, tmp_path):
        """Journal should have accounting headers."""
        path = exporter.export_journal(pipeline_result, tmp_path / "journal.csv")
        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert "Date" in header
        assert "Account Code" in header
        assert "Debit (MYR)" in header
        assert "Credit (MYR)" in header

    def test_journal_has_cash_entries(self, exporter, pipeline_result, tmp_path):
        """Journal should have cash in/out entries."""
        path = exporter.export_journal(pipeline_result, tmp_path / "journal.csv")
        content = Path(path).read_text(encoding="utf-8")
        assert "Cash" in content
        assert "Revenue" in content

    def test_journal_has_category_entries(self, exporter, pipeline_result, tmp_path):
        """Journal should have category expense entries."""
        path = exporter.export_journal(pipeline_result, tmp_path / "journal.csv")
        content = Path(path).read_text(encoding="utf-8")
        assert "Expense" in content


class TestJSONExport:
    """Tests for JSON export."""

    def test_json_creates_file(self, exporter, pipeline_result, tmp_path):
        """Should create a JSON file."""
        path = exporter.export_json(pipeline_result, tmp_path / "report.json")
        assert Path(path).exists()

    def test_json_valid(self, exporter, pipeline_result, tmp_path):
        """Should be valid JSON."""
        path = exporter.export_json(pipeline_result, tmp_path / "report.json")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "plan" in data
        assert "tasks" in data
        assert "chase_emails" in data

    def test_json_has_report(self, exporter, pipeline_result, tmp_path):
        """JSON should contain final report."""
        path = exporter.export_json(pipeline_result, tmp_path / "report.json")
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data.get("final_report") is not None
        assert "cash_in" in data["final_report"]


class TestMarkdownExport:
    """Tests for Markdown export."""

    def test_md_creates_file(self, exporter, pipeline_result, tmp_path):
        """Should create a Markdown file."""
        path = exporter.export_markdown(pipeline_result, tmp_path / "report.md")
        assert Path(path).exists()

    def test_md_has_header(self, exporter, pipeline_result, tmp_path):
        """Markdown should have a report header."""
        path = exporter.export_markdown(pipeline_result, tmp_path / "report.md")
        content = Path(path).read_text(encoding="utf-8")
        assert content.startswith("#")
        assert "Financial Report" in content

    def test_md_has_cash_flow(self, exporter, pipeline_result, tmp_path):
        """Markdown should have cash flow section."""
        path = exporter.export_markdown(pipeline_result, tmp_path / "report.md")
        content = Path(path).read_text(encoding="utf-8")
        assert "Cash Flow" in content
        assert "Net Cash" in content

    def test_md_has_categories(self, exporter, pipeline_result, tmp_path):
        """Markdown should have category breakdown."""
        path = exporter.export_markdown(pipeline_result, tmp_path / "report.md")
        content = Path(path).read_text(encoding="utf-8")
        assert "Category" in content or "Spending" in content

    def test_md_has_tasks(self, exporter, pipeline_result, tmp_path):
        """Markdown should have task list."""
        path = exporter.export_markdown(pipeline_result, tmp_path / "report.md")
        content = Path(path).read_text(encoding="utf-8")
        assert "Task" in content
        assert "TASK-0001" in content

    def test_md_has_emails(self, exporter, pipeline_result, tmp_path):
        """Markdown should have chase emails."""
        path = exporter.export_markdown(pipeline_result, tmp_path / "report.md")
        content = Path(path).read_text(encoding="utf-8")
        assert "Chase" in content or "Email" in content


class TestExportAll:
    """Tests for exporting all formats at once."""

    def test_export_all_creates_all_files(self, exporter, pipeline_result, tmp_path):
        """Should create all format files."""
        paths = exporter.export_all(pipeline_result, tmp_path / "output", "september")
        assert "csv" in paths
        assert "json" in paths
        assert "markdown" in paths
        assert "journal" in paths
        for fmt, path in paths.items():
            assert Path(path).exists(), f"{fmt} file not created"

    def test_export_all_filenames(self, exporter, pipeline_result, tmp_path):
        """Should use base_name for filenames."""
        paths = exporter.export_all(pipeline_result, tmp_path / "output", "my_report")
        assert "my_report.csv" in paths["csv"]
        assert "my_report.json" in paths["json"]
        assert "my_report.md" in paths["markdown"]
        assert "my_report_journal.csv" in paths["journal"]


class TestExporterEdgeCases:
    """Tests for edge cases."""

    def test_csv_no_report(self, exporter, tmp_path):
        """Should handle result with no final report."""
        result = PipelineResult(
            plan=Plan(goal="Test", phases=[PlanPhase(phase=1, agent="Secretary", action="Test")]),
        )
        path = exporter.export_csv(result, tmp_path / "empty.csv")
        assert Path(path).exists()

    def test_csv_no_tasks(self, exporter, tmp_path):
        """Should handle result with no tasks."""
        result = PipelineResult(
            plan=Plan(goal="Test", phases=[PlanPhase(phase=1, agent="Secretary", action="Test")]),
            final_report=FinalReport(
                goal="Test", period="September",
                cash_in=1000, cash_out=500,
            ),
        )
        path = exporter.export_csv(result, tmp_path / "notasks.csv")
        assert Path(path).exists()

    def test_creates_output_dir(self, exporter, pipeline_result, tmp_path):
        """Should create nested output directories."""
        nested = tmp_path / "a" / "b" / "c"
        path = exporter.export_csv(pipeline_result, nested / "report.csv")
        assert Path(path).exists()
        assert nested.exists()
