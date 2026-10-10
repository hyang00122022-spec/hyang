"""Shared test fixtures for the Secretary Agent test suite."""

import sys
from pathlib import Path

import pytest

# Add project root to path so we can import src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models import (
    CategorySummary,
    ChaseEmail,
    DocumentInfo,
    EmailStatus,
    ExceptionEvent,
    EventType,
    FinalReport,
    Plan,
    PlanPhase,
    Priority,
    Task,
    TaskStatus,
)


@pytest.fixture
def sample_overdue_event():
    """An overdue exception event."""
    return ExceptionEvent(
        event_type=EventType.OVERDUE,
        invoice_number="INV-2026-078",
        vendor_name="Creative Agency Sdn Bhd",
        amount=4800.00,
        invoice_date="2026-09-20",
        due_date="2026-10-05",
        details="Payment was due on 2026-10-05. No payment record found.",
    )


@pytest.fixture
def sample_duplicate_event():
    """A duplicate exception event."""
    return ExceptionEvent(
        event_type=EventType.DUPLICATE,
        invoice_number="INV-2026-001",
        vendor_name="Tech Supplies Sdn Bhd",
        amount=12500.00,
        invoice_date="2026-09-15",
        details="Invoice number and amount match an existing entry.",
        duplicate_of="INV-2026-001 (original)",
    )


@pytest.fixture
def sample_escalation_event():
    """An escalation exception event."""
    return ExceptionEvent(
        event_type=EventType.ESCALATION,
        invoice_number="INV-2026-001",
        vendor_name="Tech Supplies Sdn Bhd",
        amount=12500.00,
        details="Single invoice exceeds RM 10,000 threshold.",
        escalation_reason="Large amount exceeds threshold",
        escalation_code="LARGE_AMOUNT",
    )


@pytest.fixture
def sample_flagged_event_low_confidence():
    """A flagged document event with low OCR confidence."""
    return ExceptionEvent(
        event_type=EventType.FLAGGED,
        invoice_number="INV-WP-2026-032",
        vendor_name="Workshop Partners Sdn Bhd",
        amount=750.00,
        invoice_date="2026-09-22",
        details="OCR confidence is 0.65. Several line items unreadable.",
        flag_reason="Low OCR confidence",
        confidence=0.65,
    )


@pytest.fixture
def sample_flagged_event_ok_confidence():
    """A flagged document event with acceptable OCR confidence (exactly 0.70)."""
    return ExceptionEvent(
        event_type=EventType.FLAGGED,
        invoice_number="INV-FS-2026-045",
        vendor_name="Fresh Supplies Sdn Bhd",
        amount=320.00,
        invoice_date="2026-09-28",
        details="Vendor name has slight OCR mismatch.",
        flag_reason="Vendor name OCR mismatch",
        confidence=0.72,
    )


@pytest.fixture
def sample_small_amount_event():
    """An event with amount RM 500 — should NOT trigger escalation."""
    return ExceptionEvent(
        event_type=EventType.ESCALATION,
        invoice_number="INV-SM-2026-009",
        vendor_name="Small Vendor Sdn Bhd",
        amount=500.00,
        details="Small amount invoice.",
        escalation_reason="Below escalation threshold",
        escalation_code="BELOW_THRESHOLD",
    )


@pytest.fixture
def all_sample_events(
    sample_overdue_event,
    sample_duplicate_event,
    sample_escalation_event,
    sample_flagged_event_low_confidence,
    sample_flagged_event_ok_confidence,
):
    """All sample events combined."""
    return [
        sample_overdue_event,
        sample_duplicate_event,
        sample_escalation_event,
        sample_flagged_event_low_confidence,
        sample_flagged_event_ok_confidence,
    ]


@pytest.fixture
def sample_documents():
    """Sample document data for report testing."""
    return [
        DocumentInfo(
            doc_id="DOC-001",
            file_name="invoice_tech.pdf",
            doc_type="invoice",
            vendor_name="Tech Supplies Sdn Bhd",
            invoice_number="INV-2026-001",
            invoice_date="2026-09-15",
            grand_total=12500.00,
            line_items=[
                {"description": "Laptops", "amount": 10000, "category": "IT"},
                {"description": "Software", "amount": 2500, "category": "IT"},
            ],
            confidence=0.95,
            quality_flags=[],
        ),
        DocumentInfo(
            doc_id="DOC-002",
            file_name="receipt_rent.pdf",
            doc_type="receipt",
            vendor_name="Pangsapila Management",
            invoice_number="RCT-2026-089",
            invoice_date="2026-09-01",
            grand_total=3500.00,
            line_items=[
                {"description": "Office rent", "amount": 3500, "category": "RENT"},
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
            line_items=[
                {"description": "Campaign", "amount": 4800, "category": "MKT"},
            ],
            confidence=0.88,
            quality_flags=[],
        ),
    ]


@pytest.fixture
def sample_plan():
    """A sample execution plan."""
    return Plan(
        goal="Close out September",
        phases=[
            PlanPhase(
                phase=1,
                agent="Logistics",
                action="Collect and classify all documents.",
            ),
            PlanPhase(
                phase=2,
                agent="Financial",
                action="Build ledger, validate, raise exceptions.",
            ),
            PlanPhase(
                phase=3,
                agent="Secretary",
                action="Convert exceptions to tasks and generate report.",
            ),
        ],
    )
