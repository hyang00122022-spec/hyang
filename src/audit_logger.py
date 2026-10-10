"""Audit Logger — tracks every state change in the pipeline for traceability.

Records actions like task creation, email approval/rejection/sending, report
generation, vendor updates, and exports. Provides querying by entity, date,
or action type.

S8 (Traceability): Every change is logged with timestamp, actor, and description.

Usage:
    from src.audit_logger import AuditLogger

    logger = AuditLogger()
    logger.log("created", "task", "TASK-0001", "Created task for overdue invoice")
    logger.log("approved", "email", "EMAIL-0001", "Owner approved chase email")

    # Query
    entries = logger.get_by_entity("task", "TASK-0001")
    entries = logger.get_by_action("approved")
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import PROJECT_ROOT
from .models import AuditEntry


class AuditLogger:
    """Logs and queries audit entries for the pipeline.

    The log is stored as a JSON file (audit_log.json) in the project root.
    Entries are append-only — existing entries are never modified or deleted.
    """

    def __init__(self, log_path: Path | None = None):
        """Initialize the audit logger.

        Args:
            log_path: Path to audit_log.json. Defaults to project root.
        """
        self.log_path = log_path or (PROJECT_ROOT / "audit_log.json")
        self._entries: list[AuditEntry] = []
        self._counter: int = 0
        self._load()

    def _load(self) -> None:
        """Load existing audit entries from file."""
        if self.log_path.exists():
            try:
                data = json.loads(self.log_path.read_text(encoding="utf-8"))
                for item in data.get("entries", []):
                    self._entries.append(AuditEntry(**item))
                self._counter = data.get("counter", len(self._entries))
            except Exception as e:
                print(f"[AuditLogger] Error loading audit log: {e}")

    def _save(self) -> None:
        """Save audit entries to file."""
        try:
            self.log_path.write_text(
                json.dumps(
                    {
                        "entries": [e.model_dump() for e in self._entries],
                        "counter": self._counter,
                        "last_updated": datetime.now().isoformat(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[AuditLogger] Error saving audit log: {e}")

    def _next_entry_id(self) -> str:
        """Generate the next entry ID."""
        self._counter += 1
        return f"AUD-{self._counter:05d}"

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        description: str,
        actor: str = "system",
    ) -> AuditEntry:
        """Log a new audit entry.

        Args:
            action: What happened (created, updated, approved, rejected,
                    sent, exported, etc.)
            entity_type: What entity was affected (task, email, report,
                        vendor, document, reply)
            entity_id: ID of the affected entity.
            description: Human-readable description of the change.
            actor: Who/what performed the action.

        Returns:
            The created AuditEntry.
        """
        entry = AuditEntry(
            entry_id=self._next_entry_id(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            actor=actor,
        )
        self._entries.append(entry)
        self._save()
        return entry

    def log_batch(self, entries: list[tuple[str, str, str, str]]) -> list[AuditEntry]:
        """Log multiple entries at once. Each tuple is (action, entity_type,
        entity_id, description).

        Args:
            entries: List of (action, entity_type, entity_id, description) tuples.

        Returns:
            List of created AuditEntry objects.
        """
        created = []
        for action, entity_type, entity_id, description in entries:
            entry = self.log(action, entity_type, entity_id, description)
            created.append(entry)
        return created

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_all(self) -> list[AuditEntry]:
        """Return all audit entries."""
        return list(self._entries)

    def get_by_entity(self, entity_type: str, entity_id: str) -> list[AuditEntry]:
        """Get all entries for a specific entity.

        Args:
            entity_type: Entity type (task, email, report, etc.)
            entity_id: Entity ID.

        Returns:
            List of matching entries, chronologically sorted.
        """
        return [
            e for e in self._entries
            if e.entity_type == entity_type and e.entity_id == entity_id
        ]

    def get_by_action(self, action: str) -> list[AuditEntry]:
        """Get all entries with a specific action type."""
        return [e for e in self._entries if e.action == action]

    def get_by_entity_type(self, entity_type: str) -> list[AuditEntry]:
        """Get all entries for an entity type."""
        return [e for e in self._entries if e.entity_type == entity_type]

    def get_by_date_range(
        self, start: str, end: str
    ) -> list[AuditEntry]:
        """Get entries within a date range (ISO format strings).

        Args:
            start: Start datetime (ISO format).
            end: End datetime (ISO format).

        Returns:
            List of entries within the range.
        """
        results = []
        for e in self._entries:
            try:
                entry_dt = datetime.fromisoformat(e.timestamp)
                start_dt = datetime.fromisoformat(start)
                end_dt = datetime.fromisoformat(end)
                if start_dt <= entry_dt <= end_dt:
                    results.append(e)
            except (ValueError, TypeError):
                continue
        return results

    def get_recent(self, n: int = 10) -> list[AuditEntry]:
        """Get the N most recent entries."""
        return self._entries[-n:] if n > 0 else []

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_entry_count(self) -> int:
        """Return total number of audit entries."""
        return len(self._entries)

    def get_action_counts(self) -> dict[str, int]:
        """Return a count of entries by action type."""
        counts: dict[str, int] = {}
        for e in self._entries:
            counts[e.action] = counts.get(e.action, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_log(self, entries: list[AuditEntry] | None = None) -> str:
        """Format audit entries as a human-readable log.

        Args:
            entries: Entries to format. If None, formats all entries.

        Returns:
            Formatted multi-line string.
        """
        entries = entries or self._entries
        if not entries:
            return "[AuditLogger] No entries to display."

        lines = [
            "=" * 70,
            f"  AUDIT LOG — {len(entries)} entries",
            "=" * 70,
            "",
        ]

        for e in entries:
            lines.append(f"  [{e.entry_id}] {e.timestamp}")
            lines.append(f"    Action:  {e.action}")
            lines.append(f"    Entity:  {e.entity_type} / {e.entity_id}")
            lines.append(f"    Actor:   {e.actor}")
            lines.append(f"    Detail:  {e.description}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def format_summary(self) -> str:
        """Format a summary of the audit log."""
        counts = self.get_action_counts()
        lines = [
            "=" * 70,
            f"  AUDIT LOG SUMMARY — {self.get_entry_count()} total entries",
            "=" * 70,
            "",
            "  Actions breakdown:",
        ]

        for action, count in sorted(counts.items()):
            lines.append(f"    {action:15s}: {count}")

        lines.append("")
        lines.append("  Recent entries:")
        for e in self.get_recent(5):
            lines.append(f"    [{e.entry_id}] {e.action} — {e.description[:60]}")

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize all entries to JSON."""
        return json.dumps(
            [e.model_dump() for e in self._entries],
            indent=2,
            default=str,
            ensure_ascii=False,
        )

    def clear(self) -> None:
        """Clear all entries. Use with caution!"""
        self._entries.clear()
        self._counter = 0
        self._save()
