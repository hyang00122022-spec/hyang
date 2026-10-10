# Secretary Agent

A standalone, runnable Secretary agent for a 3-agent document processing pipeline (Logistics → Financial → Secretary) designed for Malaysian SME invoice/receipt/PO processing.

## What It Does

The Secretary agent:
1. **P0 — Plan**: Reads a business goal (e.g., "Close out September") and generates a phased execution plan
2. **P1 — Tasks + Report**: Converts Financial exceptions into plain-language tasks and generates a final report (cash flow, categories, top 3 actions)
3. **P2 — Chase Emails**: Drafts chase emails for overdue invoices (human-in-the-loop: never sends without approval)

## Project Structure

```
secretary-agent/
├── src/
│   ├── __init__.py          # Package init
│   ├── models.py            # Pydantic data models (ExceptionEvent, Task, ChaseEmail, Plan, FinalReport)
│   ├── config.py            # Business config + shared rules (S1-S8 thresholds)
│   ├── planner.py           # P0: Plan generation (standard, overdue-only, reconciliation)
│   ├── task_generator.py    # P1: Exception → task conversion + chase email drafting
│   ├── email_drafter.py     # P2: Chase email approval workflow
│   ├── reporter.py          # P1: Final report (cash flow, categories, top 3 actions)
│   ├── secretary.py         # Main orchestrator (ties all modules together)
│   └── cli.py               # CLI entry point
├── prompts/
│   ├── system_prompt.md     # Secretary's system prompt / role definition
│   ├── chase_email.txt      # Chase email template
│   ├── task_templates.json  # Task formatting templates per event type
│   └── report_template.md   # Final report template
├── schemas/
│   ├── exception_event.json # JSON schema for Financial exception events
│   ├── task.json            # JSON schema for Task output
│   ├── chase_email.json     # JSON schema for ChaseEmail output
│   ├── plan.json            # JSON schema for Plan output
│   └── final_report.json    # JSON schema for FinalReport output
├── tests/
│   ├── conftest.py          # Shared test fixtures
│   ├── test_models.py       # Data model tests
│   ├── test_task_generator.py  # Exception→task conversion tests
│   ├── test_email_drafter.py   # Chase email workflow tests
│   ├── test_planner.py      # Plan generation tests
│   └── test_reporter.py     # Report generation tests
├── examples/
│   ├── sample_exceptions.json  # Sample Financial exception events
│   └── sample_documents.json   # Sample Logistics document data
├── requirements.txt         # pydantic, pytest
├── .env.example             # Configuration template
├── run.py                   # Quick start script
└── README.md
```

## Quick Start

### 1. Install dependencies

```bash
# Create a virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run in demo mode

```bash
python -m src.cli --demo
```

This runs the full pipeline with sample data (4 exceptions, 3 documents) and prints:
- Execution plan
- Task list (with priorities)
- Draft chase emails (for overdue items)
- Final report (cash flow, categories, top 3 actions)

### 3. Run with your own data

```bash
# Process exceptions from a JSON file
python -m src.cli --goal "Close out September" --exceptions examples/sample_exceptions.json

# Process both documents and exceptions
python -m src.cli --goal "Reconcile October" --documents examples/sample_documents.json --exceptions examples/sample_exceptions.json

# Output as JSON
python -m src.cli --demo --json

# Save output to a file
python -m src.cli --demo --output result.txt
```

### 4. Interactive mode

```bash
python -m src.cli --interactive
```

### 5. Run tests

```bash
python -m pytest tests/ -v
```

## Data Flow

```
User Goal
    │
    ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ Planner  │────▶│ TaskGenerator│────▶│  Reporter    │
│ (P0)     │     │ (P1)         │     │  (P1)        │
└──────────┘     └──────┬───────┘     └──────────────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ EmailDrafter │
                 │ (P2)         │
                 └──────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │ PipelineResult   │
              │ (plan + tasks +  │
              │  emails + report)│
              └──────────────────┘
```

## Key Business Rules (S1-S8)

| Rule | Description |
|------|-------------|
| S1 | Duplicate detection: same vendor + amount + invoice number |
| S2 | Reconciliation tolerance: ±RM 1 (<RM 100) or ±RM 5 (≥RM 100) |
| S3 | PO matching: PO number, vendor, amount, line items |
| S4 | Overdue: payment due date passed, no payment record |
| S5 | 10 category codes: RAW, RENT, SAL, MKT, LOG, MNT, OFC, IT, PRO, TAX |
| S6 | 7 escalation triggers: large amount (≥RM 10k), tax mismatch, missing PO, etc. |
| S7 | Bad document flags: unreadable, missing pages, no invoice number, etc. |
| S8 | Traceability: all decisions must be auditable |

## Priority Assignment

| Priority | Event Type | Reason |
|----------|-----------|--------|
| P1 Critical | Duplicate | Potential double payment |
| P1 Critical | Escalation (≥RM 10k) | Large amount needs management approval |
| P2 High | Overdue | Chase email needed |
| P2 High | Escalation (<RM 10k) | Management review |
| P3 Medium | Flagged (confidence < 0.70) | OCR quality issue |
| P4 Low | Flagged (confidence ≥ 0.70) | Minor quality issue |

**Key rule**: Duplicate check takes precedence over overdue chase. If the same invoice has both flags, duplicate wins.

## Chase Email Template

```
Subject: Outstanding Payment — Invoice {invoice_number} — {vendor_name}

Dear Sir/Madam,

We are writing regarding the following invoice which appears to be outstanding:
  Invoice No:  {invoice_number}
  Date:        {invoice_date}
  Amount Due:  RM {grand_total}
  Due Date:    {due_date}

As of {today's_date}, we have not located a payment record...
```

Secretary **never** sends without owner approval — human-in-the-loop.

## Configuration

Edit `src/config.py` or set environment variables (see `.env.example`):

- `BUSINESS_NAME` — Your company name
- `BUSINESS_EMAIL` — Your accounts email
- `RECON_TOLERANCE_SMALL` — Tolerance for small invoices (RM)
- `RECON_TOLERANCE_LARGE` — Tolerance for large invoices (RM)
- `CONFIDENCE_THRESHOLD` — OCR confidence threshold (default 0.70)
- `LARGE_AMOUNT_THRESHOLD` — Escalation threshold (default RM 10,000)

## Running in VS Code

1. Open the `secretary-agent/` folder in VS Code
2. Open the integrated terminal (`Ctrl+` `~`)
3. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   python run.py --demo
   ```
5. Or use VS Code's Run Configuration (`.vscode/launch.json`):
   ```json
   {
     "version": "0.2.0",
     "configurations": [
       {
         "name": "Secretary Agent (Demo)",
         "type": "python",
         "request": "launch",
         "program": "${workspaceFolder}/run.py",
         "args": ["--demo"],
         "console": "integratedTerminal"
       }
     ]
   }
   ```

## License

This project is part of the document processing pipeline for Malaysian SMEs.
