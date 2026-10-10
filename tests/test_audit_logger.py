"""Tests for the Audit Logger module."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.audit_logger import AuditLogger
from src.models import AuditEntry


@pytest.fixture
def logger(tmp_path):
    """Create an AuditLogger with a temp log file."""
    return AuditLogger(log_path=tmp_path / "audit_log.json")


@pytest.fixture
def populated_logger(logger):
    """Create a logger with some pre-populated entries."""
    logger.log("created", "task", "TASK-0001", "Created task for overdue invoice")
    logger.log("created", "task", "TASK-0002", "Created task for duplicate invoice")
    logger.log("approved", "email", "EMAIL-0001", "Owner approved chase email")
    logger.log("sent", "email", "EMAIL-0001", "Chase email sent to vendor")
    logger.log("exported", "report", "RPT-001", "Exported final report to CSV")
    return logger


class TestAuditLogging:
    """Tests for logging entries."""

    def test_log_creates_entry(self, logger):
        """Should create an audit entry."""
        entry = logger.log("created", "task", "TASK-001", "Test description")
        assert entry.entry_id.startswith("AUD-")
        assert entry.action == "created"
        assert entry.entity_type == "task"
        assert entry.entity_id == "TASK-001"
        assert entry.description == "Test description"
        assert entry.actor == "system"

    def test_log_with_actor(self, logger):
        """Should accept a custom actor."""
        entry = logger.log("approved", "email", "EMAIL-001", "Approved", actor="owner")
        assert entry.actor == "owner"

    def test_log_has_timestamp(self, logger):
        """Should have a timestamp."""
        entry = logger.log("created", "task", "TASK-001", "Test")
        assert entry.timestamp
        datetime.fromisoformat(entry.timestamp)

    def test_log_batch(self, logger):
        """Should log multiple entries."""
        entries = logger.log_batch([
            ("created", "task", "TASK-001", "First"),
            ("created", "task", "TASK-002", "Second"),
            ("created", "task", "TASK-003", "Third"),
        ])
        assert len(entries) == 3
        assert logger.get_entry_count() == 3

    def test_entry_ids_sequential(self, logger):
        """Entry IDs should be sequential."""
        e1 = logger.log("created", "task", "T1", "1")
        e2 = logger.log("created", "task", "T2", "2")
        e3 = logger.log("created", "task", "T3", "3")
        # IDs should be sequential
        num1 = int(e1.entry_id.split("-")[1])
        num2 = int(e2.entry_id.split("-")[1])
        num3 = int(e3.entry_id.split("-")[1])
        assert num2 == num1 + 1
        assert num3 == num2 + 1


class TestAuditQuery:
    """Tests for querying audit entries."""

    def test_get_all(self, populated_logger):
        """Should return all entries."""
        assert len(populated_logger.get_all()) == 5

    def test_get_by_entity(self, populated_logger):
        """Should filter by entity type and ID."""
        entries = populated_logger.get_by_entity("email", "EMAIL-0001")
        assert len(entries) == 2  # approved + sent
        actions = [e.action for e in entries]
        assert "approved" in actions
        assert "sent" in actions

    def test_get_by_action(self, populated_logger):
        """Should filter by action."""
        entries = populated_logger.get_by_action("created")
        assert len(entries) == 2
        assert all(e.action == "created" for e in entries)

    def test_get_by_entity_type(self, populated_logger):
        """Should filter by entity type."""
        entries = populated_logger.get_by_entity_type("task")
        assert len(entries) == 2
        assert all(e.entity_type == "task" for e in entries)

    def test_get_recent(self, populated_logger):
        """Should return N most recent."""
        recent = populated_logger.get_recent(3)
        assert len(recent) == 3
        # Last entry should be the most recent one logged
        assert recent[-1].action == "exported"

    def test_get_recent_more_than_available(self, logger):
        """Should handle requesting more than available."""
        logger.log("created", "task", "T1", "Test")
        recent = logger.get_recent(10)
        assert len(recent) == 1

    def test_get_recent_zero(self, logger):
        """Should return empty for n=0."""
        logger.log("created", "task", "T1", "Test")
        assert logger.get_recent(0) == []

    def test_get_by_date_range(self, populated_logger):
        """Should filter by date range."""
        now = datetime.now()
        start = (now - timedelta(minutes=1)).isoformat()
        end = (now + timedelta(minutes=1)).isoformat()
        entries = populated_logger.get_by_date_range(start, end)
        assert len(entries) == 5


class TestAuditStats:
    """Tests for audit statistics."""

    def test_entry_count(self, populated_logger):
        """Should return correct count."""
        assert populated_logger.get_entry_count() == 5

    def test_action_counts(self, populated_logger):
        """Should count entries by action."""
        counts = populated_logger.get_action_counts()
        assert counts["created"] == 2
        assert counts["approved"] == 1
        assert counts["sent"] == 1
        assert counts["exported"] == 1


class TestAuditPersistence:
    """Tests for saving and loading."""

    def test_save_creates_file(self, tmp_path):
        """Should create a file when saving."""
        path = tmp_path / "audit.json"
        logger = AuditLogger(log_path=path)
        logger.log("created", "task", "T1", "Test")
        assert path.exists()

    def test_load_existing_file(self, tmp_path):
        """Should load entries from existing file."""
        path = tmp_path / "audit.json"
        logger1 = AuditLogger(log_path=path)
        logger1.log("created", "task", "T1", "First")
        logger1.log("approved", "email", "E1", "Second")

        logger2 = AuditLogger(log_path=path)
        assert logger2.get_entry_count() == 2

    def test_clear(self, logger):
        """Should clear all entries."""
        logger.log("created", "task", "T1", "Test")
        logger.log("created", "task", "T2", "Test2")
        assert logger.get_entry_count() == 2
        logger.clear()
        assert logger.get_entry_count() == 0


class TestAuditFormatting:
    """Tests for output formatting."""

    def test_format_log(self, populated_logger):
        """Should format entries as readable text."""
        output = populated_logger.format_log()
        assert "AUDIT LOG" in output
        assert "5" in output
        assert "created" in output
        assert "TASK-0001" in output

    def test_format_log_empty(self, logger):
        """Should handle empty log."""
        output = logger.format_log()
        assert "No entries" in output

    def test_format_summary(self, populated_logger):
        """Should format a summary."""
        output = populated_logger.format_summary()
        assert "AUDIT LOG SUMMARY" in output
        assert "5" in output
        assert "created" in output

    def test_to_json(self, populated_logger):
        """Should serialize to JSON."""
        json_str = populated_logger.to_json()
        data = json.loads(json_str)
        assert isinstance(data, list)
        assert len(data) == 5
        assert "entry_id" in data[0]


class TestAuditEntryModel:
    """Tests for the AuditEntry model."""

    def test_defaults(self):
        """Should have correct defaults."""
        entry = AuditEntry(
            entry_id="AUD-001",
            action="created",
            entity_type="task",
            entity_id="TASK-001",
            description="Test",
        )
        assert entry.actor == "system"
        assert entry.timestamp  # auto-generated

    def test_all_fields(self):
        """Should accept all fields."""
        entry = AuditEntry(
            entry_id="AUD-001",
            timestamp="2026-09-15T10:00:00",
            action="approved",
            entity_type="email",
            entity_id="EMAIL-001",
            description="Owner approved",
            actor="owner",
        )
        assert entry.action == "approved"
        assert entry.actor == "owner"
