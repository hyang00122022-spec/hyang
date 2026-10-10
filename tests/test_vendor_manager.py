"""Tests for the Vendor Manager module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models import VendorInfo
from src.vendor_manager import VendorManager


@pytest.fixture
def vm(tmp_path):
    """Create a VendorManager with a temp data file."""
    return VendorManager(data_path=tmp_path / "vendors.json")


@pytest.fixture
def empty_vm(tmp_path):
    """Create a VendorManager with no defaults."""
    manager = VendorManager(data_path=tmp_path / "vendors.json")
    manager._vendors.clear()
    return manager


class TestVendorLookup:
    """Tests for vendor lookup methods."""

    def test_get_vendor_by_name(self, vm):
        """Should find vendor by name (case-insensitive)."""
        v = vm.get_vendor_by_name("Tech Supplies Sdn Bhd")
        assert v is not None
        assert v.vendor_id == "VND-001"

    def test_get_vendor_by_name_case_insensitive(self, vm):
        """Should find vendor regardless of case."""
        v = vm.get_vendor_by_name("tech supplies sdn bhd")
        assert v is not None

    def test_get_vendor_by_name_not_found(self, vm):
        """Should return None for unknown vendor."""
        assert vm.get_vendor_by_name("Unknown Vendor") is None

    def test_get_vendor_by_email(self, vm):
        """Should find vendor by email."""
        v = vm.get_vendor_by_email("billing@techsupplies.com.my")
        assert v is not None
        assert v.name == "Tech Supplies Sdn Bhd"

    def test_get_vendor_by_email_case_insensitive(self, vm):
        """Should find vendor regardless of email case."""
        v = vm.get_vendor_by_email("BILLING@TechSupplies.com.my")
        assert v is not None

    def test_get_vendor_by_email_not_found(self, vm):
        """Should return None for unknown email."""
        assert vm.get_vendor_by_email("unknown@test.com") is None

    def test_get_vendor_by_id(self, vm):
        """Should find vendor by ID."""
        v = vm.get_vendor_by_id("VND-001")
        assert v is not None
        assert v.name == "Tech Supplies Sdn Bhd"

    def test_get_all_vendors(self, vm):
        """Should return all vendors sorted by name."""
        vendors = vm.get_all_vendors()
        assert len(vendors) == 5
        # Should be sorted alphabetically
        names = [v.name for v in vendors]
        assert names == sorted(names)

    def test_get_new_vendors(self, vm):
        """Should return vendors flagged as new."""
        new = vm.get_new_vendors()
        assert len(new) >= 1
        assert all(v.is_new_vendor for v in new)


class TestVendorUpdate:
    """Tests for adding and updating vendors."""

    def test_add_new_vendor(self, empty_vm):
        """Should create a new vendor."""
        v = empty_vm.add_or_update_vendor(
            name="New Vendor Sdn Bhd",
            email="test@newvendor.com",
            invoice_amount=500.00,
            invoice_date="2026-09-15",
        )
        assert v.vendor_id.startswith("VND-")
        assert v.name == "New Vendor Sdn Bhd"
        assert v.is_new_vendor is True
        assert v.total_invoices == 1
        assert v.total_amount == 500.00

    def test_update_existing_vendor(self, vm):
        """Should update existing vendor when same name."""
        original = vm.get_vendor_by_name("Tech Supplies Sdn Bhd")
        original_invoices = original.total_invoices
        original_amount = original.total_amount

        v = vm.add_or_update_vendor(
            name="Tech Supplies Sdn Bhd",
            invoice_amount=1000.00,
            invoice_date="2026-09-20",
        )
        assert v.total_invoices == original_invoices + 1
        assert v.total_amount == round(original_amount + 1000.00, 2)

    def test_new_vendor_becomes_not_new_after_second_invoice(self, empty_vm):
        """Vendor should no longer be new after 2 invoices."""
        v = empty_vm.add_or_update_vendor(
            name="Test Vendor",
            invoice_amount=100.00,
            invoice_date="2026-01-01",
        )
        assert v.is_new_vendor is True

        v = empty_vm.add_or_update_vendor(
            name="Test Vendor",
            invoice_amount=200.00,
            invoice_date="2026-02-01",
        )
        assert v.is_new_vendor is False
        assert v.total_invoices == 2

    def test_record_invoice(self, vm):
        """Should increment counters when recording an invoice."""
        original = vm.get_vendor_by_name("Creative Agency Sdn Bhd")
        original_invoices = original.total_invoices
        original_amount = original.total_amount
        v = vm.record_invoice("Creative Agency Sdn Bhd", 5000.00, "2026-09-25")
        assert v is not None
        assert v.total_invoices == original_invoices + 1
        assert v.total_amount == round(original_amount + 5000.00, 2)

    def test_record_invoice_not_found(self, vm):
        """Should return None for unknown vendor."""
        assert vm.record_invoice("Unknown", 100.00, "2026-01-01") is None

    def test_update_vendor_fields(self, vm):
        """Should update specific fields."""
        v = vm.update_vendor("VND-001", phone="+603-9999-0000", notes="Updated notes")
        assert v is not None
        assert v.phone == "+603-9999-0000"
        assert v.notes == "Updated notes"

    def test_update_vendor_not_found(self, vm):
        """Should return None for unknown vendor ID."""
        assert vm.update_vendor("VND-999", notes="test") is None


class TestVendorStats:
    """Tests for vendor statistics."""

    def test_total_vendors(self, vm):
        """Should return correct count."""
        assert vm.get_total_vendors() == 5

    def test_total_spend(self, vm):
        """Should return sum of all vendor amounts."""
        spend = vm.get_total_spend()
        assert spend > 0
        # Should match sum of default vendors
        expected = sum(v["total_amount"] for v in VendorManager.DEFAULT_VENDORS)
        assert spend == round(expected, 2)

    def test_top_vendors(self, vm):
        """Should return vendors sorted by spend."""
        top = vm.get_top_vendors(3)
        assert len(top) == 3
        # Should be descending
        assert top[0].total_amount >= top[1].total_amount >= top[2].total_amount

    def test_top_vendors_all(self, vm):
        """Should handle requesting more than available."""
        top = vm.get_top_vendors(100)
        assert len(top) == 5

    def test_vendors_by_category(self, vm):
        """Should filter by category code."""
        it_vendors = vm.get_vendors_by_category("IT")
        assert len(it_vendors) == 1
        assert it_vendors[0].name == "Tech Supplies Sdn Bhd"

    def test_vendors_by_category_empty(self, vm):
        """Should return empty list for unknown category."""
        assert vm.get_vendors_by_category("NONEXIST") == []


class TestVendorModel:
    """Tests for the VendorInfo model."""

    def test_to_summary(self):
        """Should format a one-line summary."""
        v = VendorInfo(
            vendor_id="VND-001",
            name="Test Vendor",
            payment_terms_days=30,
            total_invoices=5,
            total_amount=10000.00,
        )
        summary = v.to_summary()
        assert "VND-001" in summary
        assert "Test Vendor" in summary
        assert "30d" in summary
        assert "5 invoices" in summary

    def test_to_summary_new_vendor(self):
        """Should show [NEW] flag for new vendors."""
        v = VendorInfo(
            vendor_id="VND-002",
            name="New Vendor",
            is_new_vendor=True,
        )
        assert "[NEW]" in v.to_summary()

    def test_amount_rounding(self):
        """Should round amount to 2 decimal places."""
        v = VendorInfo(
            vendor_id="VND-001",
            name="Test",
            total_amount=100.015,
        )
        assert v.total_amount == 100.02

    def test_negative_amount_rejected(self):
        """Should reject negative total_amount."""
        with pytest.raises(Exception):
            VendorInfo(
                vendor_id="VND-001",
                name="Test",
                total_amount=-100.00,
            )


class TestVendorPersistence:
    """Tests for saving and loading vendor data."""

    def test_save_creates_file(self, tmp_path):
        """Should create a JSON file when saving."""
        path = tmp_path / "vendors.json"
        vm = VendorManager(data_path=path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "vendors" in data

    def test_load_existing_file(self, tmp_path):
        """Should load vendors from existing file."""
        path = tmp_path / "vendors.json"
        # Create first manager (seeds defaults)
        vm1 = VendorManager(data_path=path)
        vm1.add_or_update_vendor("Extra Vendor", invoice_amount=500.00)

        # Create second manager (should load from file)
        vm2 = VendorManager(data_path=path)
        assert vm2.get_vendor_by_name("Extra Vendor") is not None
        assert vm2.get_total_vendors() == vm1.get_total_vendors()

    def test_format_summary(self, vm):
        """Should format a readable summary."""
        output = vm.format_summary()
        assert "VENDOR DATABASE" in output
        assert str(vm.get_total_vendors()) in output
        assert "RM" in output
