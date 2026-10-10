"""Vendor Master Database — centralizes vendor info, payment terms, and history.

Replaces hardcoded vendor data scattered across the pipeline. The VendorManager
loads/saves a vendors.json file and provides lookup, stats, and update methods.

Usage:
    from src.vendor_manager import VendorManager

    vm = VendorManager()
    vm.add_or_update_vendor(
        name="Tech Supplies Sdn Bhd",
        email="billing@techsupplies.com.my",
        invoice_amount=12500.00,
        invoice_date="2026-09-15",
    )
    vendor = vm.get_vendor_by_name("Tech Supplies Sdn Bhd")
    print(vendor.to_summary())
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import CATEGORY_CODES, PROJECT_ROOT
from .models import VendorInfo


class VendorManager:
    """Manages the vendor master database.

    The database is stored as a JSON file (vendors.json) in the project root.
    On first run, it's seeded with default vendors from the sample data.
    """

    DEFAULT_VENDORS: list[dict] = [
        {
            "vendor_id": "VND-001",
            "name": "Tech Supplies Sdn Bhd",
            "email": "billing@techsupplies.com.my",
            "phone": "+603-1234-5678",
            "payment_terms_days": 30,
            "category_code": "IT",
            "tax_id": "ST-1234567",
            "bank_name": "Maybank",
            "bank_account": "5123-4567-8901",
            "first_invoice_date": "2026-01-15",
            "total_invoices": 8,
            "total_amount": 45000.00,
            "is_new_vendor": False,
            "notes": "Preferred IT supplier. Fast delivery.",
        },
        {
            "vendor_id": "VND-002",
            "name": "Pangsapila Management",
            "email": "accounts@pangsapila.my",
            "phone": "+603-9876-5432",
            "payment_terms_days": 0,
            "category_code": "RENT",
            "tax_id": None,
            "bank_name": "CIMB",
            "bank_account": "8000-1234-5678",
            "first_invoice_date": "2026-01-01",
            "total_invoices": 10,
            "total_amount": 35000.00,
            "is_new_vendor": False,
            "notes": "Office landlord. Auto-pay rent monthly.",
        },
        {
            "vendor_id": "VND-003",
            "name": "Creative Agency Sdn Bhd",
            "email": "finance@creativeagency.com.my",
            "phone": "+603-5555-1234",
            "payment_terms_days": 15,
            "category_code": "MKT",
            "tax_id": "ST-7654321",
            "bank_name": "Public Bank",
            "bank_account": "3000-9876-5432",
            "first_invoice_date": "2026-06-01",
            "total_invoices": 4,
            "total_amount": 19200.00,
            "is_new_vendor": False,
            "notes": "Marketing campaigns. 15-day payment terms.",
        },
        {
            "vendor_id": "VND-004",
            "name": "Workshop Partners Sdn Bhd",
            "email": "ap@workshoppartners.my",
            "phone": "+603-7777-8888",
            "payment_terms_days": 30,
            "category_code": "MNT",
            "tax_id": "ST-9876543",
            "bank_name": "RHB Bank",
            "bank_account": "2000-1111-2222",
            "first_invoice_date": "2026-09-22",
            "total_invoices": 1,
            "total_amount": 750.00,
            "is_new_vendor": True,
            "notes": "New vendor. First invoice Sep 2026. Low OCR confidence on scan.",
        },
        {
            "vendor_id": "VND-005",
            "name": "Global Logistics",
            "email": "billing@globallogistics.com.my",
            "phone": "+603-4444-3333",
            "payment_terms_days": 14,
            "category_code": "LOG",
            "tax_id": "ST-5555555",
            "bank_name": "Maybank",
            "bank_account": "5678-9012-3456",
            "first_invoice_date": "2026-03-01",
            "total_invoices": 7,
            "total_amount": 22000.00,
            "is_new_vendor": False,
            "notes": "Shipping and freight. 14-day terms.",
        },
    ]

    def __init__(self, data_path: Path | None = None):
        """Initialize the vendor manager.

        Args:
            data_path: Path to vendors.json. Defaults to project root.
        """
        self.data_path = data_path or (PROJECT_ROOT / "vendors.json")
        self._vendors: dict[str, VendorInfo] = {}
        self._load()

    def _load(self) -> None:
        """Load vendors from JSON file, or seed defaults if file doesn't exist."""
        if self.data_path.exists():
            try:
                data = json.loads(self.data_path.read_text(encoding="utf-8"))
                for item in data.get("vendors", []):
                    v = VendorInfo(**item)
                    self._vendors[v.name.lower()] = v
            except Exception as e:
                print(f"[VendorManager] Error loading vendors: {e}")
                self._seed_defaults()
        else:
            self._seed_defaults()

    def _seed_defaults(self) -> None:
        """Seed the database with default vendors."""
        for item in self.DEFAULT_VENDORS:
            v = VendorInfo(**item)
            self._vendors[v.name.lower()] = v
        self._save()

    def _save(self) -> None:
        """Save vendors to JSON file."""
        try:
            self.data_path.write_text(
                json.dumps(
                    {
                        "vendors": [v.model_dump() for v in self._vendors.values()],
                        "last_updated": datetime.now().isoformat(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[VendorManager] Error saving vendors: {e}")

    # ------------------------------------------------------------------
    # Lookup methods
    # ------------------------------------------------------------------

    def get_vendor_by_name(self, name: str) -> VendorInfo | None:
        """Look up a vendor by name (case-insensitive)."""
        return self._vendors.get(name.lower().strip())

    def get_vendor_by_email(self, email: str) -> VendorInfo | None:
        """Look up a vendor by email address (case-insensitive)."""
        email_lower = email.lower().strip()
        for v in self._vendors.values():
            if v.email.lower() == email_lower:
                return v
        return None

    def get_vendor_by_id(self, vendor_id: str) -> VendorInfo | None:
        """Look up a vendor by vendor_id."""
        for v in self._vendors.values():
            if v.vendor_id == vendor_id:
                return v
        return None

    def get_all_vendors(self) -> list[VendorInfo]:
        """Return all vendors sorted by name."""
        return sorted(self._vendors.values(), key=lambda v: v.name)

    def get_new_vendors(self) -> list[VendorInfo]:
        """Return vendors flagged as new (is_new_vendor=True)."""
        return [v for v in self._vendors.values() if v.is_new_vendor]

    # ------------------------------------------------------------------
    # Update methods
    # ------------------------------------------------------------------

    def add_or_update_vendor(
        self,
        name: str,
        email: str = "",
        invoice_amount: float = 0.0,
        invoice_date: str | None = None,
        payment_terms_days: int = 30,
        category_code: str = "OFC",
        **kwargs,
    ) -> VendorInfo:
        """Add a new vendor or update an existing one with invoice info.

        Args:
            name: Vendor name.
            email: Vendor contact email.
            invoice_amount: Amount of the new invoice.
            invoice_date: Date of the new invoice (ISO format).
            payment_terms_days: Payment terms in days.
            category_code: Default category code (S5).
            **kwargs: Additional VendorInfo fields.

        Returns:
            The updated or newly created VendorInfo.
        """
        existing = self.get_vendor_by_name(name)

        if existing:
            # Update existing vendor
            existing.total_invoices += 1
            existing.total_amount = round(existing.total_amount + invoice_amount, 2)
            if email and not existing.email:
                existing.email = email
            # After 2+ invoices, no longer new
            if existing.total_invoices >= 2:
                existing.is_new_vendor = False
            self._save()
            return existing
        else:
            # Create new vendor
            vendor_id = self._next_vendor_id()
            vendor = VendorInfo(
                vendor_id=vendor_id,
                name=name,
                email=email,
                payment_terms_days=payment_terms_days,
                category_code=category_code,
                first_invoice_date=invoice_date,
                total_invoices=1,
                total_amount=round(invoice_amount, 2),
                is_new_vendor=True,
                **{k: v for k, v in kwargs.items() if v is not None},
            )
            self._vendors[name.lower()] = vendor
            self._save()
            return vendor

    def update_vendor(self, vendor_id: str, **kwargs) -> VendorInfo | None:
        """Update specific fields on an existing vendor.

        Args:
            vendor_id: The vendor ID to update.
            **kwargs: Fields to update.

        Returns:
            Updated VendorInfo or None if not found.
        """
        vendor = self.get_vendor_by_id(vendor_id)
        if not vendor:
            return None

        for key, value in kwargs.items():
            if hasattr(vendor, key) and value is not None:
                setattr(vendor, key, value)

        self._save()
        return vendor

    def record_invoice(
        self, vendor_name: str, amount: float, invoice_date: str
    ) -> VendorInfo | None:
        """Record a new invoice against a vendor (increments counters).

        Args:
            vendor_name: Vendor name.
            amount: Invoice amount.
            invoice_date: Invoice date (ISO format).

        Returns:
            Updated VendorInfo or None if vendor not found.
        """
        vendor = self.get_vendor_by_name(vendor_name)
        if not vendor:
            return None

        vendor.total_invoices += 1
        vendor.total_amount = round(vendor.total_amount + amount, 2)
        if vendor.total_invoices >= 2:
            vendor.is_new_vendor = False
        if not vendor.first_invoice_date:
            vendor.first_invoice_date = invoice_date

        self._save()
        return vendor

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_total_vendors(self) -> int:
        """Return total number of vendors."""
        return len(self._vendors)

    def get_total_spend(self) -> float:
        """Return total amount across all vendors."""
        return round(sum(v.total_amount for v in self._vendors.values()), 2)

    def get_top_vendors(self, n: int = 5) -> list[VendorInfo]:
        """Return top N vendors by total spend."""
        return sorted(
            self._vendors.values(),
            key=lambda v: v.total_amount,
            reverse=True,
        )[:n]

    def get_vendors_by_category(self, category_code: str) -> list[VendorInfo]:
        """Return vendors in a specific category."""
        return [
            v for v in self._vendors.values()
            if v.category_code == category_code
        ]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _next_vendor_id(self) -> str:
        """Generate the next vendor ID."""
        existing_ids = [
            int(v.vendor_id.split("-")[1])
            for v in self._vendors.values()
            if v.vendor_id.startswith("VND-")
        ]
        next_num = max(existing_ids, default=0) + 1
        return f"VND-{next_num:03d}"

    def format_summary(self) -> str:
        """Format all vendors as a human-readable summary."""
        lines = [
            "=" * 70,
            f"  VENDOR DATABASE — {self.get_total_vendors()} vendors",
            f"  Total spend: RM {self.get_total_spend():,.2f}",
            "=" * 70,
            "",
        ]

        for v in self.get_all_vendors():
            lines.append(f"  {v.to_summary()}")
            if v.email:
                lines.append(f"    Email:  {v.email}")
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)
