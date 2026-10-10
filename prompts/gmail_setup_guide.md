# Gmail API Setup Guide

This guide walks you through setting up Gmail API access for the Secretary Agent's
email crawler module. The crawler auto-fetches invoice/receipt/PO emails and downloads
attachments for processing.

## Overview

```
[Gmail Inbox] → GmailCrawler (OAuth 2.0) → staging/ → Logistics (OCR) → Pipeline
```

The crawler uses **read-only** Gmail API access. It never sends or modifies emails.
You approve chase emails separately through the Secretary's human-in-the-loop workflow.

---

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown → **New Project**
3. Name it (e.g., `secretary-agent`) → **Create**
4. Select the new project from the dropdown

## Step 2: Enable Gmail API

1. In the Cloud Console, go to **APIs & Services → Library**
2. Search for **Gmail API**
3. Click it → **Enable**

## Step 3: Configure OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**
2. Choose **External** (unless you have a Google Workspace org) → **Create**
3. Fill in:
   - App name: `Secretary Agent`
   - User support email: your email
   - Developer contact email: your email
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes**
   - Search for `gmail.readonly`
   - Check `https://www.googleapis.com/auth/gmail.readonly`
   - Click **Update** → **Save and Continue**
6. On the **Test Users** page, click **Add Users**
   - Add your own Gmail address
   - **Save and Continue**
7. Review summary → **Back to Dashboard**

> **Note:** The app stays in "Testing" mode. This is fine for personal use.
> You don't need to publish it. Testing mode allows up to 100 users.

## Step 4: Create OAuth Credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Name: `Secretary Agent Client`
5. Click **Create**
6. A dialog appears with your **Client ID** and **Client Secret**
7. Click **Download JSON** — this downloads your `credentials.json` file

## Step 5: Place credentials.json

Move the downloaded file to your project root:

```bash
# The file you downloaded is named something like:
# client_secret_123456789-abcdef.apps.googleusercontent.com.json
# Rename it to credentials.json and place it in the project root:

cp ~/Downloads/client_secret_*.json secretary-agent/credentials.json
```

The file should be at:
```
secretary-agent/
├── credentials.json   ← here
├── src/
├── prompts/
└── ...
```

> **Security:** `credentials.json` is in `.gitignore` and will NOT be pushed to GitHub.
> `token.json` (generated after first auth) is also gitignored.

## Step 6: Install Dependencies

```bash
# Activate your venv first
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

Or install from requirements.txt (already updated):
```bash
pip install -r requirements.txt
```

## Step 7: First Run — Browser Authentication

On the first run, a browser window will open asking you to authorize the app:

```bash
python -m src.cli --gmail
```

1. Select your Google account
2. You'll see a "Google hasn't verified this app" warning — this is normal
3. Click **Advanced → Go to Secretary Agent (unsafe)**
4. Review the permissions (read-only Gmail access) → **Continue**
5. The token is saved as `token.json` for future runs

After the first run, subsequent runs won't need browser interaction.

## Step 8: Using the Gmail Crawler

### CLI Mode

```bash
# Fetch emails from last 30 days
python -m src.cli --gmail --goal "Close out September"

# Fetch with date range
python -m src.cli --gmail --gmail-after "2026/09/01" --gmail-before "2026/09/30"

# Output as JSON
python -m src.cli --gmail --json

# Mock mode (no real Gmail credentials needed)
python -m src.cli --gmail --gmail-mock
```

### Python API

```python
from src.gmail_crawler import GmailCrawler

# Real mode
crawler = GmailCrawler()
if crawler.authenticate():
    emails = crawler.fetch_invoice_emails(
        date_after="2026/09/01",
        date_before="2026/09/30",
    )
    for email in emails:
        print(email.to_summary())
        # email.downloaded_files contains paths to attachments
        # Feed these to Logistics for OCR processing

# Mock mode (for testing)
crawler = GmailCrawler(mock=True)
emails = crawler.fetch_invoice_emails()
```

### Integration with Secretary Pipeline

```python
from src.gmail_crawler import GmailCrawler
from src.secretary import Secretary

# 1. Fetch emails
crawler = GmailCrawler(mock=True)  # Use mock=True for testing
emails = crawler.fetch_invoice_emails()

# 2. Downloaded files are in staging/
#    In production, Logistics agent would OCR these files
#    For now, use sample documents that match the email vendors

# 3. Run Secretary pipeline with sample data
#    (In production, Logistics would produce DocumentInfo from the attachments)
secretary = Secretary()
result = secretary.run(
    goal="Close out September",
    documents=secretary._sample_documents(),
    exceptions=secretary._sample_exceptions(),
)
print(secretary.format_result(result))
```

---

## Configuration

### Environment Variables (.env)

```bash
# Gmail crawler settings (optional - defaults are in src/config.py)
GMAIL_MAX_RESULTS=50
GMAIL_VENDOR_DOMAINS=  # comma-separated, e.g. "supplier.com.my,vendor.com"
```

### Vendor Domain Whitelist

To only fetch emails from known vendor domains, edit `src/config.py`:

```python
GMAIL_VENDOR_DOMAINS = [
    "techsupplies.com.my",
    "pangsapila.my",
    "creativeagency.com.my",
    # Add your vendor domains here
]
```

Or pass at runtime:

```python
emails = crawler.fetch_invoice_emails(
    sender_domains=["techsupplies.com.my", "pangsapila.my"]
)
```

### Deduplication

The crawler tracks processed message IDs in `.gmail_processed_ids.json`.
On subsequent runs, already-processed emails are skipped automatically.

To re-process all emails:

```python
crawler.clear_processed_cache()
emails = crawler.fetch_invoice_emails()
```

---

## Security Notes

1. **Read-only access:** The crawler only has `gmail.readonly` scope. It cannot
   send, delete, or modify emails.
2. **credentials.json is gitignored:** Never commit this file to version control.
3. **token.json is gitignored:** The OAuth token is also excluded from git.
4. **Chase emails are separate:** The Secretary's chase email workflow uses the
   human-in-the-loop approval process. Gmail crawling is for **incoming** vendor
   emails only.

---

## Troubleshooting

### "credentials.json not found"
Make sure you downloaded the OAuth credentials JSON from Google Cloud Console
and placed it in the project root as `credentials.json`.

### "Google hasn't verified this app"
This is expected for apps in Testing mode. Click **Advanced → Go to Secretary Agent (unsafe)**.
This just means the app hasn't gone through Google's verification process, which
is only needed for public apps with 100+ users.

### "Access blocked: Authorization Error"
Make sure your Gmail address is added as a Test User in the OAuth consent screen
(Step 3, point 6).

### "ModuleNotFoundError: No module named 'googleapiclient'"
Install the Google API dependencies:
```bash
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### Token expired
Delete `token.json` and run again. A new browser auth flow will be triggered.

### Want to test without real Gmail?
Use mock mode:
```bash
python -m src.cli --gmail --gmail-mock
```
This returns 5 sample vendor emails with attachments without any API calls.
