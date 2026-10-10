"""Tests for the Gmail Crawler module.

Tests cover:
  - Mock mode data fetching
  - Email parsing (headers, attachments, vendor name, doc type detection)
  - Search query building
  - Deduplication cache
  - Attachment downloading (mock)
  - Date filtering
  - Utility methods (email extraction, vendor name, doc type detection)
  - Formatting output
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from src.gmail_crawler import GmailCrawler
from src.models import AttachmentInfo, RawEmailDocument


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_crawler(tmp_path):
    """Create a GmailCrawler in mock mode with a clean staging dir and cache."""
    staging = tmp_path / "staging"
    cache = tmp_path / "processed_ids.json"
    crawler = GmailCrawler(
        credentials_path=tmp_path / "credentials.json",
        token_path=tmp_path / "token.json",
        staging_dir=staging,
        cache_path=cache,
        mock=True,
    )
    yield crawler
    # Cleanup
    if staging.exists():
        shutil.rmtree(staging)


@pytest.fixture
def crawler_with_processed(clean_crawler):
    """A crawler with some pre-processed message IDs for dedup testing."""
    clean_crawler._processed_ids = {"msg_mock_001", "msg_mock_002"}
    yield clean_crawler


@pytest.fixture
def sample_gmail_message():
    """Simulate a Gmail API message dict for parse_email_metadata testing."""
    return {
        "id": "msg_test_100",
        "threadId": "thread_test_100",
        "payload": {
            "headers": [
                {"name": "From", "value": "Test Vendor Sdn Bhd <billing@testvendor.com.my>"},
                {"name": "Subject", "value": "Tax Invoice INV-TEST-001"},
                {"name": "Date", "value": "Mon, 15 Sep 2026 10:30:00 +0800"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": "UGxlYXNlIGZpbmQgYXR0YWNoZWQgb3VyIHRheCBpbnZvaWNlLg==",
                    },
                },
                {
                    "filename": "INV-TEST-001.pdf",
                    "mimeType": "application/pdf",
                    "body": {
                        "size": 150000,
                        "attachmentId": "att_test_100",
                    },
                },
                {
                    "filename": "signature.png",
                    "mimeType": "image/png",
                    "body": {
                        "size": 5000,
                        "attachmentId": "att_test_101",
                    },
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# Mock mode tests
# ---------------------------------------------------------------------------

class TestMockFetch:
    """Tests for mock mode email fetching."""

    def test_mock_returns_emails(self, clean_crawler):
        """Mock mode should return sample emails."""
        emails = clean_crawler.fetch_invoice_emails()
        assert len(emails) > 0
        assert all(isinstance(e, RawEmailDocument) for e in emails)

    def test_mock_email_count(self, clean_crawler):
        """Should return 5 mock emails."""
        emails = clean_crawler.fetch_invoice_emails()
        assert len(emails) == 5

    def test_mock_email_has_message_id(self, clean_crawler):
        """Each email should have a non-empty message_id."""
        emails = clean_crawler.fetch_invoice_emails()
        for email in emails:
            assert email.message_id
            assert email.message_id.startswith("msg_mock_")

    def test_mock_email_has_attachments(self, clean_crawler):
        """Each email should have at least one attachment."""
        emails = clean_crawler.fetch_invoice_emails()
        for email in emails:
            assert email.has_attachment is True
            assert len(email.attachments) >= 1

    def test_mock_email_has_downloaded_files(self, clean_crawler):
        """Attachments should be downloaded to staging dir."""
        emails = clean_crawler.fetch_invoice_emails()
        for email in emails:
            assert len(email.downloaded_files) == len(email.attachments)
            for path in email.downloaded_files:
                assert Path(path).exists()

    def test_mock_email_doc_types(self, clean_crawler):
        """Should detect correct document types from subjects."""
        emails = clean_crawler.fetch_invoice_emails()
        doc_types = {e.message_id: e.detected_doc_type for e in emails}
        assert "invoice" in doc_types.values()
        assert "receipt" in doc_types.values()

    def test_mock_email_vendor_names(self, clean_crawler):
        """Should extract vendor names from sender."""
        emails = clean_crawler.fetch_invoice_emails()
        for email in emails:
            assert email.vendor_name
            assert email.vendor_name != ""

    def test_mock_email_dates(self, clean_crawler):
        """Emails should have ISO-format dates."""
        emails = clean_crawler.fetch_invoice_emails()
        for email in emails:
            assert email.date
            # Should be parseable as ISO datetime
            datetime.fromisoformat(email.date)

    def test_mock_max_results(self, clean_crawler):
        """Should respect max_results limit."""
        emails = clean_crawler.fetch_invoice_emails(max_results=2)
        assert len(emails) == 2


class TestDateFiltering:
    """Tests for date range filtering."""

    def test_date_after_filter(self, clean_crawler):
        """Should only return emails after the given date."""
        emails = clean_crawler.fetch_invoice_emails(date_after="2026/09/20")
        for email in emails:
            dt = datetime.fromisoformat(email.date).replace(tzinfo=None)
            assert dt >= datetime(2026, 9, 20)

    def test_date_before_filter(self, clean_crawler):
        """Should only return emails before the given date."""
        emails = clean_crawler.fetch_invoice_emails(date_before="2026/09/15")
        for email in emails:
            dt = datetime.fromisoformat(email.date).replace(tzinfo=None)
            assert dt <= datetime(2026, 9, 16)  # inclusive of 15th end-of-day

    def test_date_range_filter(self, clean_crawler):
        """Should only return emails within the date range."""
        emails = clean_crawler.fetch_invoice_emails(
            date_after="2026/09/15", date_before="2026/09/22"
        )
        for email in emails:
            dt = datetime.fromisoformat(email.date).replace(tzinfo=None)
            assert datetime(2026, 9, 15) <= dt <= datetime(2026, 9, 23)


# ---------------------------------------------------------------------------
# Deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Tests for processed message ID deduplication."""

    def test_skip_processed(self, crawler_with_processed):
        """Should skip already-processed message IDs."""
        emails = crawler_with_processed.fetch_invoice_emails(skip_processed=True)
        msg_ids = {e.message_id for e in emails}
        assert "msg_mock_001" not in msg_ids
        assert "msg_mock_002" not in msg_ids
        assert len(emails) == 3  # 5 total - 2 processed

    def test_no_skip_processed(self, crawler_with_processed):
        """With skip_processed=False, should return all."""
        emails = crawler_with_processed.fetch_invoice_emails(skip_processed=False)
        assert len(emails) == 5

    def test_processed_count(self, crawler_with_processed):
        """Should report correct processed count."""
        assert crawler_with_processed.get_processed_count() == 2

    def test_clear_cache(self, crawler_with_processed):
        """Clearing cache should reset processed IDs."""
        assert crawler_with_processed.get_processed_count() == 2
        crawler_with_processed.clear_processed_cache()
        assert crawler_with_processed.get_processed_count() == 0

    def test_second_run_skips_all(self, clean_crawler):
        """Running twice should skip all on second run."""
        first = clean_crawler.fetch_invoice_emails()
        assert len(first) == 5
        second = clean_crawler.fetch_invoice_emails()
        assert len(second) == 0


# ---------------------------------------------------------------------------
# Search query tests
# ---------------------------------------------------------------------------

class TestSearchQuery:
    """Tests for Gmail search query building."""

    def test_query_has_attachment(self, clean_crawler):
        """Query should include has:attachment."""
        q = clean_crawler.build_search_query()
        assert "has:attachment" in q

    def test_query_has_extensions(self, clean_crawler):
        """Query should include file extension filters."""
        q = clean_crawler.build_search_query()
        assert "filename:.pdf" in q
        assert "filename:.jpg" in q
        assert "filename:.png" in q

    def test_query_has_keywords(self, clean_crawler):
        """Query should include subject keyword filters."""
        q = clean_crawler.build_search_query()
        assert "subject:" in q
        assert "invoice" in q

    def test_query_with_date(self, clean_crawler):
        """Query should include date filters."""
        q = clean_crawler.build_search_query(
            date_after="2026/09/01", date_before="2026/09/30"
        )
        assert "after:2026/09/01" in q
        assert "before:2026/09/30" in q

    def test_query_with_domains(self, clean_crawler):
        """Query should include sender domain filters."""
        q = clean_crawler.build_search_query(
            sender_domains=["supplier.com.my", "vendor.com"]
        )
        assert "from:supplier.com.my" in q
        assert "from:vendor.com" in q

    def test_query_with_custom_keywords(self, clean_crawler):
        """Should accept custom keywords."""
        q = clean_crawler.build_search_query(keywords=["faktur", "resit"])
        assert "faktur" in q
        assert "resit" in q


# ---------------------------------------------------------------------------
# Email parsing tests
# ---------------------------------------------------------------------------

class TestEmailParsing:
    """Tests for parse_email_metadata with simulated Gmail API data."""

    def test_parse_extracts_message_id(self, clean_crawler, sample_gmail_message):
        """Should extract message ID from Gmail message."""
        # Switch to non-mock for this test (parse doesn't need API)
        clean_crawler.mock = False
        clean_crawler._service = None  # No real service
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        assert doc is not None
        assert doc.message_id == "msg_test_100"
        assert doc.thread_id == "thread_test_100"

    def test_parse_extracts_sender(self, clean_crawler, sample_gmail_message):
        """Should extract sender info."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        assert "Test Vendor Sdn Bhd" in doc.sender
        assert doc.sender_email == "billing@testvendor.com.my"

    def test_parse_extracts_subject(self, clean_crawler, sample_gmail_message):
        """Should extract subject."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        assert "Tax Invoice" in doc.subject
        assert "INV-TEST-001" in doc.subject

    def test_parse_extracts_date(self, clean_crawler, sample_gmail_message):
        """Should parse date to ISO format."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        assert "2026" in doc.date
        # Should be parseable as ISO datetime
        datetime.fromisoformat(doc.date)

    def test_parse_finds_attachments(self, clean_crawler, sample_gmail_message):
        """Should find attachments in message parts."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        # Should find PDF and PNG (both in allowed extensions)
        assert len(doc.attachments) == 2
        filenames = [a.filename for a in doc.attachments]
        assert "INV-TEST-001.pdf" in filenames
        assert "signature.png" in filenames

    def test_parse_detects_doc_type(self, clean_crawler, sample_gmail_message):
        """Should detect document type from subject."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        assert doc.detected_doc_type == "invoice"

    def test_parse_extracts_vendor_name(self, clean_crawler, sample_gmail_message):
        """Should extract vendor name from sender."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        assert "Test Vendor" in doc.vendor_name

    def test_parse_extracts_body_snippet(self, clean_crawler, sample_gmail_message):
        """Should extract body text snippet."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata(sample_gmail_message)
        assert doc.body_snippet
        assert "tax invoice" in doc.body_snippet.lower()

    def test_parse_returns_none_on_error(self, clean_crawler):
        """Should return None if parsing fails."""
        clean_crawler.mock = False
        doc = clean_crawler.parse_email_metadata({"invalid": "data"})
        assert doc is None


# ---------------------------------------------------------------------------
# Utility method tests
# ---------------------------------------------------------------------------

class TestUtilities:
    """Tests for static utility methods."""

    def test_extract_email_address_with_name(self):
        """Should extract email from 'Name <email>' format."""
        result = GmailCrawler._extract_email_address("Vendor <test@vendor.com>")
        assert result == "test@vendor.com"

    def test_extract_email_address_plain(self):
        """Should extract email from plain address."""
        result = GmailCrawler._extract_email_address("test@vendor.com")
        assert result == "test@vendor.com"

    def test_extract_email_address_unknown(self):
        """Should return placeholder for unparseable strings."""
        result = GmailCrawler._extract_email_address("no email here")
        assert "unknown" in result

    def test_extract_vendor_name_from_display(self):
        """Should extract display name before angle brackets."""
        result = GmailCrawler._extract_vendor_name(
            "Tech Supplies Sdn Bhd <billing@tech.com>", "Invoice"
        )
        assert "Tech Supplies" in result

    def test_extract_vendor_name_from_username(self):
        """Should derive name from email username when no display name."""
        result = GmailCrawler._extract_vendor_name(
            "john.doe@example.com", "Invoice"
        )
        assert "John" in result or "Doe" in result

    def test_extract_vendor_name_generic_prefix(self):
        """Should fall back to subject for generic email prefixes."""
        result = GmailCrawler._extract_vendor_name(
            "billing@unknown.com", "September Statement"
        )
        # "billing" is a generic prefix, should use subject
        assert "September" in result or "Statement" in result

    def test_detect_doc_type_invoice(self):
        """Should detect invoice type."""
        assert GmailCrawler._detect_doc_type("Tax Invoice INV-001") == "invoice"
        assert GmailCrawler._detect_doc_type("Invoice #123") == "invoice"

    def test_detect_doc_type_receipt(self):
        """Should detect receipt type."""
        assert GmailCrawler._detect_doc_type("Receipt RCT-001") == "receipt"
        assert GmailCrawler._detect_doc_type("Resit September") == "receipt"

    def test_detect_doc_type_unknown(self):
        """Should return unknown for unrelated subjects."""
        assert GmailCrawler._detect_doc_type("Hello team") == "unknown"
        assert GmailCrawler._detect_doc_type("Meeting notes") == "unknown"

    def test_detect_doc_type_shipping(self):
        """Should detect shipping invoice as invoice."""
        assert GmailCrawler._detect_doc_type("Shipping Invoice SHP-001") == "invoice"


# ---------------------------------------------------------------------------
# Attachment tests
# ---------------------------------------------------------------------------

class TestAttachments:
    """Tests for attachment handling."""

    def test_attachment_info_creation(self):
        """AttachmentInfo should be created with correct fields."""
        att = AttachmentInfo(
            filename="test.pdf",
            mime_type="application/pdf",
            size=1000,
            attachment_id="att_001",
        )
        assert att.filename == "test.pdf"
        assert att.mime_type == "application/pdf"
        assert att.size == 1000
        assert att.downloaded is False

    def test_attachment_negative_size(self):
        """Negative size should be clamped to 0."""
        att = AttachmentInfo(
            filename="test.pdf",
            size=-100,
        )
        assert att.size == 0

    def test_mock_attachment_downloaded(self, clean_crawler):
        """Mock attachments should be downloaded as files."""
        emails = clean_crawler.fetch_invoice_emails()
        for email in emails:
            for att in email.attachments:
                assert att.downloaded is True
                assert att.local_path is not None
                assert Path(att.local_path).exists()

    def test_staging_dir_created(self, clean_crawler):
        """Staging directory should be created automatically."""
        clean_crawler.fetch_invoice_emails()
        assert clean_crawler.staging_dir.exists()
        assert clean_crawler.staging_dir.is_dir()


# ---------------------------------------------------------------------------
# RawEmailDocument model tests
# ---------------------------------------------------------------------------

class TestRawEmailDocument:
    """Tests for the RawEmailDocument model."""

    def test_to_summary(self):
        """to_summary should produce a one-line summary."""
        doc = RawEmailDocument(
            message_id="msg_001",
            sender="Vendor <v@test.com>",
            sender_email="v@test.com",
            subject="Invoice INV-001",
            date="2026-09-15T10:00:00+08:00",
            detected_doc_type="invoice",
            vendor_name="Test Vendor",
            attachments=[AttachmentInfo(filename="inv.pdf", size=1000)],
        )
        summary = doc.to_summary()
        assert "msg_001" in summary
        assert "Test Vendor" in summary
        assert "invoice" in summary
        assert "1 attachment" in summary

    def test_default_values(self):
        """Should have correct defaults."""
        doc = RawEmailDocument(
            message_id="msg_001",
            sender="v@test.com",
            sender_email="v@test.com",
            subject="Test",
            date="2026-01-01T00:00:00",
        )
        assert doc.has_attachment is True
        assert doc.detected_doc_type == "unknown"
        assert doc.vendor_name == ""
        assert doc.attachments == []
        assert doc.downloaded_files == []


# ---------------------------------------------------------------------------
# Formatting tests
# ---------------------------------------------------------------------------

class TestFormatting:
    """Tests for output formatting."""

    def test_format_summary_with_emails(self, clean_crawler):
        """Should format emails as a readable summary."""
        emails = clean_crawler.fetch_invoice_emails()
        output = clean_crawler.format_emails_summary(emails)
        assert "GMAIL CRAWLER" in output
        assert str(len(emails)) in output
        assert "Staging directory" in output

    def test_format_summary_empty(self, clean_crawler):
        """Should handle empty list gracefully."""
        output = clean_crawler.format_emails_summary([])
        assert "No emails" in output

    def test_to_json(self, clean_crawler):
        """Should serialize emails to JSON."""
        emails = clean_crawler.fetch_invoice_emails()
        json_str = clean_crawler.to_json(emails)
        data = json.loads(json_str)
        assert isinstance(data, list)
        assert len(data) == len(emails)
        assert "message_id" in data[0]


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------

class TestAuthentication:
    """Tests for the authenticate method."""

    def test_mock_auth_always_true(self, clean_crawler):
        """Mock mode should always authenticate successfully."""
        assert clean_crawler.authenticate() is True

    def test_no_credentials_falls_back_to_mock(self, tmp_path):
        """Without credentials.json, should fall back to mock mode."""
        crawler = GmailCrawler(
            credentials_path=tmp_path / "nonexistent.json",
            token_path=tmp_path / "token.json",
            staging_dir=tmp_path / "staging",
            mock=False,
        )
        result = crawler.authenticate()
        assert result is True
        assert crawler.mock is True  # Should have switched to mock
