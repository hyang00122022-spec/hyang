"""Gmail Crawler — auto-fetch invoice/receipt emails and download attachments.

This module connects to Gmail via the Gmail API (OAuth 2.0) and:
  1. Searches for emails matching invoice/receipt/PO keywords
  2. Downloads PDF/image attachments to a staging directory
  3. Extracts metadata (sender, date, subject, vendor name)
  4. Returns RawEmailDocument objects ready for the Logistics agent

The downloaded attachments can then be OCR'd by Logistics and converted
to DocumentInfo objects for the rest of the pipeline.

Setup:
  See prompts/gmail_setup_guide.md for Google Cloud Console setup.
  You need credentials.json from Google Cloud Console in the project root.

Usage:
  from src.gmail_crawler import GmailCrawler

  crawler = GmailCrawler()
  if crawler.authenticate():
      emails = crawler.fetch_invoice_emails(date_after="2026/09/01")
      for email in emails:
          print(email.to_summary())

Mock mode (for testing without real Gmail credentials):
  crawler = GmailCrawler(mock=True)
  emails = crawler.fetch_invoice_emails()
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .config import (
    GMAIL_ATTACHMENT_EXTENSIONS,
    GMAIL_ATTACHMENT_MIME_TYPES,
    GMAIL_CREDENTIALS_FILE,
    GMAIL_MAX_RESULTS,
    GMAIL_PROCESSED_CACHE,
    GMAIL_SCOPES,
    GMAIL_STAGING_DIR,
    GMAIL_SUBJECT_KEYWORDS,
    GMAIL_TOKEN_FILE,
    GMAIL_VENDOR_DOMAINS,
    PROJECT_ROOT,
)
from .models import AttachmentInfo, RawEmailDocument


# ---------------------------------------------------------------------------
# Mock data (used when mock=True or no credentials available)
# ---------------------------------------------------------------------------

_MOCK_EMAILS: list[dict[str, Any]] = [
    {
        "message_id": "msg_mock_001",
        "thread_id": "thread_mock_001",
        "sender": "Tech Supplies Sdn Bhd <billing@techsupplies.com.my>",
        "sender_email": "billing@techsupplies.com.my",
        "subject": "Tax Invoice INV-2026-001 — September 2026",
        "date": "2026-09-15T10:30:00+08:00",
        "body_snippet": "Please find attached our tax invoice for the laptops and software licenses supplied on 15 September 2026.",
        "attachments": [
            {
                "filename": "INV-2026-001.pdf",
                "mime_type": "application/pdf",
                "size": 245680,
                "attachment_id": "att_mock_001",
            }
        ],
        "detected_doc_type": "invoice",
        "vendor_name": "Tech Supplies Sdn Bhd",
    },
    {
        "message_id": "msg_mock_002",
        "thread_id": "thread_mock_002",
        "sender": "Pangsapila Management <accounts@pangsapila.my>",
        "sender_email": "accounts@pangsapila.my",
        "subject": "Receipt — Office Rent September 2026",
        "date": "2026-09-01T09:00:00+08:00",
        "body_snippet": "Thank you for your payment. Attached is the official receipt for office rent for September 2026.",
        "attachments": [
            {
                "filename": "RCT-2026-089.pdf",
                "mime_type": "application/pdf",
                "size": 89200,
                "attachment_id": "att_mock_002",
            }
        ],
        "detected_doc_type": "receipt",
        "vendor_name": "Pangsapila Management",
    },
    {
        "message_id": "msg_mock_003",
        "thread_id": "thread_mock_003",
        "sender": "Creative Agency <finance@creativeagency.com.my>",
        "sender_email": "finance@creativeagency.com.my",
        "subject": "Invoice INV-CA-2026-078 — Social Media Campaign",
        "date": "2026-09-20T14:15:00+08:00",
        "body_snippet": "Attached is our invoice for the social media campaign services rendered in September 2026. Payment terms: 15 days.",
        "attachments": [
            {
                "filename": "INV-CA-2026-078.pdf",
                "mime_type": "application/pdf",
                "size": 178400,
                "attachment_id": "att_mock_003",
            }
        ],
        "detected_doc_type": "invoice",
        "vendor_name": "Creative Agency",
    },
    {
        "message_id": "msg_mock_004",
        "thread_id": "thread_mock_004",
        "sender": "Workshop Partners <ap@workshoppartners.my>",
        "sender_email": "ap@workshoppartners.my",
        "subject": "Invoice INV-WP-2026-032 + scanned copy",
        "date": "2026-09-22T16:45:00+08:00",
        "body_snippet": "Please process the attached invoice for workshop maintenance services. The scan quality may be slightly low.",
        "attachments": [
            {
                "filename": "INV-WP-2026-032.jpg",
                "mime_type": "image/jpeg",
                "size": 534000,
                "attachment_id": "att_mock_004",
            }
        ],
        "detected_doc_type": "invoice",
        "vendor_name": "Workshop Partners",
    },
    {
        "message_id": "msg_mock_005",
        "thread_id": "thread_mock_005",
        "sender": "Global Logistics <billing@globallogistics.com.my>",
        "sender_email": "billing@globallogistics.com.my",
        "subject": "Shipping Invoice SHP-2026-045 — Freight Charges",
        "date": "2026-09-28T11:20:00+08:00",
        "body_snippet": "Freight charges for September shipments. Attached tax invoice and delivery notes.",
        "attachments": [
            {
                "filename": "SHP-2026-045.pdf",
                "mime_type": "application/pdf",
                "size": 312500,
                "attachment_id": "att_mock_005",
            },
            {
                "filename": "delivery_notes.pdf",
                "mime_type": "application/pdf",
                "size": 145000,
                "attachment_id": "att_mock_006",
            }
        ],
        "detected_doc_type": "invoice",
        "vendor_name": "Global Logistics",
    },
]

_MOCK_ATTACHMENT_CONTENT = b"%PDF-1.4\n%Mock PDF content for testing purposes.\n%%EOF"


class GmailCrawler:
    """Crawls Gmail for invoice/receipt/PO emails and downloads attachments.

    Modes:
      - Real mode: Uses Gmail API with OAuth 2.0. Requires credentials.json.
      - Mock mode: Returns sample data without any API calls. For testing.

    Deduplication: Tracks processed message IDs in a cache file so repeated
    runs don't re-download the same emails.
    """

    def __init__(
        self,
        credentials_path: Path | None = None,
        token_path: Path | None = None,
        staging_dir: Path | None = None,
        cache_path: Path | None = None,
        mock: bool = False,
    ):
        """Initialize the Gmail crawler.

        Args:
            credentials_path: Path to Google OAuth credentials.json.
            token_path: Path to save/load the OAuth token.
            staging_dir: Directory to save downloaded attachments.
            cache_path: Path for the deduplication cache file.
            mock: If True, use mock data instead of real Gmail API.
        """
        self.credentials_path = credentials_path or GMAIL_CREDENTIALS_FILE
        self.token_path = token_path or GMAIL_TOKEN_FILE
        self.staging_dir = staging_dir or GMAIL_STAGING_DIR
        self.cache_path = cache_path or GMAIL_PROCESSED_CACHE
        self.mock = mock
        self._service = None  # Lazy-initialized Gmail API service
        self._processed_ids: set[str] = self._load_processed_cache()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Authenticate with Gmail API using OAuth 2.0.

        Returns True if authentication succeeded (or mock mode).
        Returns False if credentials are not available.

        In mock mode, always returns True without real auth.
        """
        if self.mock:
            return True

        # Check for credentials.json BEFORE importing Google libraries
        if not self.credentials_path.exists():
            print(
                f"[GmailCrawler] credentials.json not found at {self.credentials_path}\n"
                "See prompts/gmail_setup_guide.md for setup instructions.\n"
                "Using mock mode as fallback."
            )
            self.mock = True
            return True

        # Lazy import — only needed for real mode
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            print(
                "[GmailCrawler] Google API libraries not installed.\n"
                "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2\n"
                "Or use mock mode: GmailCrawler(mock=True)\n"
                "Using mock mode as fallback."
            )
            self.mock = True
            return True

        # Load existing token if available
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), GMAIL_SCOPES
            )

        # Refresh or initiate new auth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token for future runs
            self.token_path.write_text(creds.to_json(), encoding="utf-8")

        # Build Gmail API service
        self._service = build("gmail", "v1", credentials=creds)
        return True

    # ------------------------------------------------------------------
    # Email search
    # ------------------------------------------------------------------

    def build_search_query(
        self,
        keywords: list[str] | None = None,
        date_after: str | None = None,
        date_before: str | None = None,
        sender_domains: list[str] | None = None,
    ) -> str:
        """Build a Gmail search query string.

        Args:
            keywords: Subject keywords to search for. Defaults to config keywords.
            date_after: Only emails after this date (format: YYYY/MM/DD).
            date_before: Only emails before this date (format: YYYY/MM/DD).
            sender_domains: Only emails from these domains.

        Returns:
            Gmail search query string.
        """
        keywords = keywords or GMAIL_SUBJECT_KEYWORDS
        parts: list[str] = []

        # Must have attachment
        parts.append("has:attachment")

        # Attachment file type filter
        ext_terms = " OR ".join(f"filename:{ext}" for ext in GMAIL_ATTACHMENT_EXTENSIONS)
        parts.append(f"({ext_terms})")

        # Subject keywords
        kw_terms = " OR ".join(f'subject:"{kw}"' for kw in keywords)
        parts.append(f"({kw_terms})")

        # Date range
        if date_after:
            parts.append(f"after:{date_after}")
        if date_before:
            parts.append(f"before:{date_before}")

        # Sender domains
        if sender_domains:
            domain_terms = " OR ".join(
                f"from:{domain}" for domain in sender_domains
            )
            parts.append(f"({domain_terms})")

        return " ".join(parts)

    def fetch_invoice_emails(
        self,
        max_results: int = GMAIL_MAX_RESULTS,
        date_after: str | None = None,
        date_before: str | None = None,
        sender_domains: list[str] | None = None,
        skip_processed: bool = True,
    ) -> list[RawEmailDocument]:
        """Fetch emails that likely contain invoice/receipt/PO attachments.

        Args:
            max_results: Maximum number of emails to fetch.
            date_after: Only emails after this date (YYYY/MM/DD).
            date_before: Only emails before this date (YYYY/MM/DD).
            sender_domains: Filter by sender domain whitelist.
            skip_processed: Skip emails already processed in previous runs.

        Returns:
            List of RawEmailDocument objects with attachment metadata.
        """
        if self.mock:
            return self._mock_fetch(
                max_results, date_after, date_before, skip_processed
            )

        if not self._service:
            if not self.authenticate():
                return []

        domains = sender_domains if sender_domains is not None else GMAIL_VENDOR_DOMAINS
        query = self.build_search_query(
            date_after=date_after,
            date_before=date_before,
            sender_domains=domains if domains else None,
        )

        print(f"[GmailCrawler] Search query: {query}")

        # Search Gmail
        results = (
            self._service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        message_ids = results.get("messages", [])

        if not message_ids:
            print("[GmailCrawler] No matching emails found.")
            return []

        print(f"[GmailCrawler] Found {len(message_ids)} matching emails.")

        emails: list[RawEmailDocument] = []
        for msg_ref in message_ids:
            msg_id = msg_ref["id"]

            # Deduplication
            if skip_processed and msg_id in self._processed_ids:
                continue

            # Fetch full message
            message = (
                self._service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            raw_doc = self.parse_email_metadata(message)
            if raw_doc:
                emails.append(raw_doc)
                self._processed_ids.add(msg_id)

        # Save processed IDs cache
        self._save_processed_cache()

        print(
            f"[GmailCrawler] Processed {len(emails)} new emails "
            f"({len(message_ids) - len(emails)} skipped as duplicates)."
        )
        return emails

    # ------------------------------------------------------------------
    # Email parsing
    # ------------------------------------------------------------------

    def parse_email_metadata(self, message: dict[str, Any]) -> RawEmailDocument | None:
        """Parse a Gmail API message dict into a RawEmailDocument.

        Args:
            message: Full message dict from Gmail API (format="full").

        Returns:
            RawEmailDocument or None if parsing fails.
        """
        try:
            # Basic structural validation
            msg_id = ""
            if not isinstance(message, dict) or "id" not in message:
                raise ValueError("Invalid message structure: missing 'id' field")
            if "payload" not in message:
                raise ValueError("Invalid message structure: missing 'payload' field")

            msg_id = message.get("id", "")
            thread_id = message.get("threadId", "")
            payload = message.get("payload", {})
            headers = payload.get("headers", [])

            # Extract headers
            header_map = {h["name"].lower(): h["value"] for h in headers}
            sender = header_map.get("from", "Unknown")
            subject = header_map.get("subject", "(no subject)")
            date_str = header_map.get("date", "")

            # Parse date to ISO format
            iso_date = self._parse_email_date(date_str)

            # Extract sender email
            sender_email = self._extract_email_address(sender)

            # Extract vendor name from sender
            vendor_name = self._extract_vendor_name(sender, subject)

            # Detect document type
            doc_type = self._detect_doc_type(subject)

            # Get body snippet
            body_snippet = self._extract_body_snippet(payload)

            # Find attachments
            attachments = self._find_attachments(payload)

            # Download attachments
            downloaded_files: list[str] = []
            for att in attachments:
                local_path = self._download_attachment(msg_id, att)
                if local_path:
                    att.downloaded = True
                    att.local_path = local_path
                    downloaded_files.append(local_path)

            return RawEmailDocument(
                message_id=msg_id,
                thread_id=thread_id,
                sender=sender,
                sender_email=sender_email,
                subject=subject,
                date=iso_date,
                body_snippet=body_snippet,
                has_attachment=len(attachments) > 0,
                attachments=attachments,
                downloaded_files=downloaded_files,
                detected_doc_type=doc_type,
                vendor_name=vendor_name,
            )
        except Exception as e:
            print(f"[GmailCrawler] Error parsing message {msg_id}: {e}")
            return None

    # ------------------------------------------------------------------
    # Attachment handling
    # ------------------------------------------------------------------

    def _find_attachments(self, payload: dict[str, Any]) -> list[AttachmentInfo]:
        """Recursively find all attachments in a message payload.

        Gmail nests attachments inside multipart parts, so we need to
        traverse the part tree.
        """
        attachments: list[AttachmentInfo] = []

        def _walk_parts(part: dict[str, Any]) -> None:
            # Check if this part is an attachment
            filename = part.get("filename", "")
            if filename:
                mime_type = part.get("mimeType", "application/octet-stream")
                body = part.get("body", {})
                size = body.get("size", 0)
                att_id = body.get("attachmentId", "")

                # Filter by extension
                ext = Path(filename).suffix.lower()
                if ext in GMAIL_ATTACHMENT_EXTENSIONS:
                    attachments.append(
                        AttachmentInfo(
                            filename=filename,
                            mime_type=mime_type,
                            size=size,
                            attachment_id=att_id,
                        )
                    )

            # Recurse into sub-parts
            for sub in part.get("parts", []):
                _walk_parts(sub)

        _walk_parts(payload)
        return attachments

    def _download_attachment(
        self, msg_id: str, att: AttachmentInfo
    ) -> str | None:
        """Download a single attachment from Gmail to the staging directory.

        Args:
            msg_id: Gmail message ID.
            att: AttachmentInfo with attachment_id.

        Returns:
            Local file path if downloaded, None on failure.
        """
        if self.mock or not self._service:
            # Mock mode: create a placeholder file
            return self._mock_download(att)

        try:
            result = (
                self._service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg_id, id=att.attachment_id)
                .execute()
            )
            data = base64.urlsafe_b64decode(result.get("data", ""))

            # Ensure staging dir exists
            self.staging_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize filename
            safe_name = re.sub(r'[<>:"/\\|?*]', "_", att.filename)
            local_path = self.staging_dir / f"{msg_id}_{safe_name}"
            local_path.write_bytes(data)

            return str(local_path)
        except Exception as e:
            print(f"[GmailCrawler] Error downloading {att.filename}: {e}")
            return None

    def _mock_download(self, att: AttachmentInfo) -> str | None:
        """Create a mock attachment file for testing."""
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", att.filename)
        local_path = self.staging_dir / f"mock_{safe_name}"
        local_path.write_bytes(_MOCK_ATTACHMENT_CONTENT)
        return str(local_path)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_email_date(date_str: str) -> str:
        """Parse various email date formats to ISO 8601.

        Gmail returns dates like: 'Mon, 15 Sep 2026 10:30:00 +0800'
        """
        if not date_str:
            return datetime.now().isoformat()

        # Try RFC 2822 format
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.isoformat()
        except Exception:
            pass

        # Fallback: just use the raw string
        return date_str

    @staticmethod
    def _extract_email_address(sender: str) -> str:
        """Extract email address from a 'Name <email>' string."""
        match = re.search(r'<([^>]+)>', sender)
        if match:
            return match.group(1).strip().lower()
        # No angle brackets — maybe it's just the email
        match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', sender)
        if match:
            return match.group(0).strip().lower()
        return "unknown@example.com"

    @staticmethod
    def _extract_vendor_name(sender: str, subject: str) -> str:
        """Extract vendor name from sender header.

        Priority:
          1. Display name before <email>
          2. Email username before @
          3. First word of subject
        """
        # Try display name in angle brackets: "Vendor Name <a@b.com>"
        match = re.match(r'^([^<]+)<', sender)
        if match:
            name = match.group(1).strip().strip('"')
            if name:
                return name

        # Try email username: remove @domain and common prefixes
        email_match = re.search(r'([\w.+-]+)@', sender)
        if email_match:
            username = email_match.group(1)
            # Remove common prefixes like "billing", "accounts", "ap"
            for prefix in ("billing", "accounts", "account", "ap", "finance", "invoicing", "inv"):
                if username.lower() == prefix:
                    break
            else:
                # Capitalize username parts
                parts = username.replace(".", " ").replace("_", " ").split()
                return " ".join(p.capitalize() for p in parts)

        # Fallback: first 2-3 words of subject
        words = subject.split()
        return " ".join(words[:3]) if words else "Unknown Vendor"

    @staticmethod
    def _detect_doc_type(subject: str) -> str:
        """Detect document type from email subject.

        Returns: 'invoice', 'receipt', 'PO', or 'unknown'
        """
        subject_lower = subject.lower()

        if "receipt" in subject_lower or "resit" in subject_lower:
            return "receipt"
        if "purchase order" in subject_lower or subject_lower.strip().startswith("po"):
            # "PO" as standalone is ambiguous; require context
            if "po " in subject_lower or "po-" in subject_lower or "po#" in subject_lower:
                return "PO"
        if "invoice" in subject_lower or "tax invoice" in subject_lower:
            return "invoice"
        if "shipping" in subject_lower or "freight" in subject_lower:
            return "invoice"  # Shipping invoices are still invoices
        if "statement" in subject_lower or "bill" in subject_lower:
            return "invoice"

        return "unknown"

    @staticmethod
    def _extract_body_snippet(payload: dict[str, Any]) -> str:
        """Extract first ~200 chars of the email body."""
        def _get_text(part: dict[str, Any]) -> str:
            mime = part.get("mimeType", "")
            if mime == "text/plain":
                body = part.get("body", {})
                data = body.get("data", "")
                if data:
                    try:
                        decoded = base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="replace"
                        )
                        return decoded
                    except Exception:
                        return ""
            # Recurse
            for sub in part.get("parts", []):
                text = _get_text(sub)
                if text:
                    return text
            return ""

        text = _get_text(payload)
        # Truncate and clean
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:200] if text else ""

    # ------------------------------------------------------------------
    # Deduplication cache
    # ------------------------------------------------------------------

    def _load_processed_cache(self) -> set[str]:
        """Load previously processed message IDs from cache file."""
        if not self.cache_path.exists():
            return set()
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return set(data.get("processed_ids", []))
        except Exception:
            return set()

    def _save_processed_cache(self) -> None:
        """Save processed message IDs to cache file."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(
                    {"processed_ids": list(self._processed_ids)},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[GmailCrawler] Warning: could not save processed cache: {e}")

    def clear_processed_cache(self) -> None:
        """Clear the deduplication cache. Useful for re-processing."""
        self._processed_ids.clear()
        if self.cache_path.exists():
            self.cache_path.unlink()

    def get_processed_count(self) -> int:
        """Return number of previously processed message IDs."""
        return len(self._processed_ids)

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------

    def _mock_fetch(
        self,
        max_results: int,
        date_after: str | None,
        date_before: str | None,
        skip_processed: bool,
    ) -> list[RawEmailDocument]:
        """Return mock email data for testing without real Gmail API."""
        # Convert date filters to datetime for comparison
        after_dt = self._date_str_to_dt(date_after) if date_after else None
        before_dt = self._date_str_to_dt(date_before) if date_before else None

        emails: list[RawEmailDocument] = []
        for mock in _MOCK_EMAILS:
            msg_id = mock["message_id"]

            # Deduplication
            if skip_processed and msg_id in self._processed_ids:
                continue

            # Date filtering
            # Date filtering — strip timezone for naive comparison
            mock_dt = datetime.fromisoformat(mock["date"]).replace(tzinfo=None)
            if after_dt and mock_dt < after_dt:
                continue
            if before_dt and mock_dt > before_dt:
                continue

            # Build attachments
            attachments = [
                AttachmentInfo(**att) for att in mock["attachments"]
            ]

            # Download mock attachments
            downloaded_files: list[str] = []
            for att in attachments:
                path = self._mock_download(att)
                if path:
                    att.downloaded = True
                    att.local_path = path
                    downloaded_files.append(path)

            doc = RawEmailDocument(
                message_id=msg_id,
                thread_id=mock["thread_id"],
                sender=mock["sender"],
                sender_email=mock["sender_email"],
                subject=mock["subject"],
                date=mock["date"],
                body_snippet=mock["body_snippet"],
                has_attachment=True,
                attachments=attachments,
                downloaded_files=downloaded_files,
                detected_doc_type=mock["detected_doc_type"],
                vendor_name=mock["vendor_name"],
            )
            emails.append(doc)
            self._processed_ids.add(msg_id)

            if len(emails) >= max_results:
                break

        self._save_processed_cache()
        return emails

    @staticmethod
    def _date_str_to_dt(date_str: str) -> datetime | None:
        """Convert YYYY/MM/DD to datetime."""
        try:
            return datetime.strptime(date_str, "%Y/%m/%d")
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Display / formatting
    # ------------------------------------------------------------------

    def format_emails_summary(self, emails: list[RawEmailDocument]) -> str:
        """Format a list of emails as a human-readable summary table."""
        if not emails:
            return "[GmailCrawler] No emails to display."

        lines = [
            "=" * 80,
            f"  GMAIL CRAWLER — {len(emails)} EMAIL(S) FOUND",
            "=" * 80,
            "",
        ]

        for i, email in enumerate(emails, 1):
            lines.append(f"  #{i} {email.to_summary()}")
            lines.append(f"      Sender:  {email.sender}")
            lines.append(f"      Date:    {email.date}")
            lines.append(f"      Files:   {len(email.downloaded_files)} downloaded")
            for f in email.downloaded_files:
                lines.append(f"               -> {Path(f).name}")
            lines.append("")

        lines.append("=" * 80)
        lines.append(
            f"  Staging directory: {self.staging_dir}"
        )
        lines.append("=" * 80)
        return "\n".join(lines)

    def to_json(self, emails: list[RawEmailDocument]) -> str:
        """Serialize emails to JSON string."""
        return json.dumps(
            [e.model_dump() for e in emails],
            indent=2,
            default=str,
            ensure_ascii=False,
        )
