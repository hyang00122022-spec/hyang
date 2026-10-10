"""Configuration for the Secretary Agent.

All business-specific constants live here. Adjust these to match
your business rules (shared rules S1-S8 from the rules file).
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SCHEMAS_DIR = PROJECT_ROOT / "schemas"
EXAMPLES_DIR = PROJECT_ROOT / "examples"

# ---------------------------------------------------------------------------
# Business identity
# ---------------------------------------------------------------------------

BUSINESS_NAME = "Your Business Sdn Bhd"
BUSINESS_EMAIL = "accounts@yourbusiness.my"
BUSINESS_CURRENCY = "MYR"

# ---------------------------------------------------------------------------
# Shared rules (S1-S8) — key thresholds
# ---------------------------------------------------------------------------

# S2: Reconciliation tolerance — if amount difference is within tolerance,
#     treat as matched. Small invoices get tighter tolerance.
RECON_TOLERANCE_SMALL = 1.00   # +/- RM 1.00 for amounts < RM 100
RECON_TOLERANCE_LARGE = 5.00   # +/- RM 5.00 for amounts >= RM 100
RECON_SMALL_THRESHOLD = 100.00

# S1: Duplicate detection — same vendor + same amount + same invoice number
DUPLICATE_MATCH_FIELDS = ["vendor_name", "amount", "invoice_number"]

# S4: Overdue — payment due date has passed and no payment record found
OVERDUE_GRACE_DAYS = 0  # No grace period; due date is the deadline

# S5: Category codes (10 standard categories)
CATEGORY_CODES = {
    "RAW": "Raw Materials",
    "RENT": "Rent & Utilities",
    "SAL": "Salaries & Wages",
    "MKT": "Marketing & Advertising",
    "LOG": "Logistics & Shipping",
    "MNT": "Maintenance & Repairs",
    "OFC": "Office Supplies",
    "IT": "IT & Software",
    "PRO": "Professional Services",
    "TAX": "Taxes & Levies",
}

# S6: Escalation triggers (7 rules)
ESCALATION_TRIGGERS = {
    "LARGE_AMOUNT": 10000.00,   # Single invoice >= RM 10,000
    "TAX_DISCREPANCY": 0.01,    # SST/tax mismatch > 1%
    "MISSING_PO": None,          # No PO for purchases >= RM 500
    "DUPLICATE_SUSPECTED": None,
    "OVERDUE_30D": 30,           # Overdue by 30+ days
    "VENDOR_NEW": 1,             # First-time vendor (only 1 prior invoice)
    "ROUNDING_LARGE": 10.00,    # Rounding difference > RM 10
}

# S7: Bad document flags
BAD_DOC_FLAGS = [
    "unreadable",
    "missing_pages",
    "wrong_format",
    "no_invoice_number",
    "no_date",
    "no_amount",
    "duplicate_scan",
]

# S3: PO matching criteria
PO_MATCH_CRITERIA = [
    "po_number_present",
    "vendor_matches",
    "amount_within_tolerance",
    "line_items_match",
]

# Confidence threshold from Logistics (S7)
CONFIDENCE_THRESHOLD = 0.70  # Below this = flagged for review

# ---------------------------------------------------------------------------
# Priority mapping (exception type -> default priority)
# ---------------------------------------------------------------------------

PRIORITY_MAP = {
    "duplicate": 1,     # P1_CRITICAL — potential double payment
    "escalation": 2,    # P2_HIGH — needs management attention
    "overdue": 2,       # P2_HIGH — chase email needed
    "flagged": 3,       # P3_MEDIUM — review needed
}

# ---------------------------------------------------------------------------
# Email defaults
# ---------------------------------------------------------------------------

EMAIL_SIGNATURE = f"""
Best regards,
{BUSINESS_NAME}
{BUSINESS_EMAIL}
""".strip()

# ---------------------------------------------------------------------------
# Gmail crawler configuration
# ---------------------------------------------------------------------------

# OAuth credentials (download from Google Cloud Console)
# See prompts/gmail_setup_guide.md for setup instructions
GMAIL_CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
GMAIL_TOKEN_FILE = PROJECT_ROOT / "token.json"

# Where downloaded attachments are saved
GMAIL_STAGING_DIR = PROJECT_ROOT / "staging"

# Search keywords for invoice/receipt/PO emails
GMAIL_SUBJECT_KEYWORDS = [
    "invoice", "invoices",
    "receipt", "resit",  # "resit" = Malay for receipt
    "purchase order", "po",
    "bill", "statement",
    "tax invoice",  # Malaysian SST invoice format
]

# File extensions to download as attachments
GMAIL_ATTACHMENT_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".heic"]

# MIME types to accept
GMAIL_ATTACHMENT_MIME_TYPES = [
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
]

# Optional: whitelist of sender domains (empty = accept all)
# e.g. ["supplier.com.my", "vendor.com"]
GMAIL_VENDOR_DOMAINS: list[str] = []

# Max emails to fetch per run (Gmail API quota safety)
GMAIL_MAX_RESULTS = 50

# Cache file for processed message IDs (deduplication)
GMAIL_PROCESSED_CACHE = PROJECT_ROOT / ".gmail_processed_ids.json"

# Scopes — readonly is enough; we never send email via Gmail API
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
