"""Tests of the TRANSFORM step.

Each cleaning rule is checked in isolation, on a minimal dataset built for the
occasion. A failing test then points at exactly the rule at fault.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.transform.transform import (
    _normalize_email,
    _parse_dates,
    transform_customers,
    transform_orders,
    transform_products,
)


class TestDeduplication:
    """Duplicate removal."""

    def test_removes_duplicate_primary_keys(self, dirty_customers: pd.DataFrame):
        _, report = transform_customers(dirty_customers)

        # Customer 2 appears twice in the fixture.
        assert report.duplicates_removed == 1

    def test_keeps_first_occurrence(self):
        frame = pd.DataFrame(
            {
                "customer_id": ["1", "1"],
                "first_name": ["First", "Second"],
                "last_name": ["A", "B"],
                "email": ["a@example.com", "b@example.com"],
                "country": ["France", "France"],
                "created_at": ["2025-01-01", "2025-01-02"],
            }
        )

        result, _ = transform_customers(frame)

        assert len(result) == 1
        assert result["first_name"].iloc[0] == "First"


class TestNullHandling:
    """Handling of missing values."""

    def test_counts_nulls_before_cleaning(self, dirty_customers: pd.DataFrame):
        _, report = transform_customers(dirty_customers)

        # empty customer_id + empty last_name
        assert report.nulls_found == 2

    def test_rejects_rows_without_primary_key(self, dirty_customers: pd.DataFrame):
        result, report = transform_customers(dirty_customers)

        assert "customer_id missing" in report.rejected
        assert result["customer_id"].notna().all()

    def test_keeps_rows_with_optional_field_missing(self):
        """A missing last name is no reason to lose the customer."""
        frame = pd.DataFrame(
            {
                "customer_id": ["1"],
                "first_name": ["Awa"],
                "last_name": [""],
                "email": ["awa@example.com"],
                "country": ["Mali"],
                "created_at": ["2025-01-01"],
            }
        )

        result, _ = transform_customers(frame)

        assert len(result) == 1
        assert pd.isna(result["last_name"].iloc[0])


class TestTypeValidation:
    """Type conversion and validation."""

    def test_identifiers_become_nullable_integers(self, dirty_customers: pd.DataFrame):
        result, _ = transform_customers(dirty_customers)

        # Int64 (capitalised), not int64: pandas' NULLABLE integer type.
        assert str(result["customer_id"].dtype) == "Int64"

    def test_dates_become_datetimes(self, dirty_customers: pd.DataFrame):
        result, _ = transform_customers(dirty_customers)

        assert str(result["created_at"].dtype) == "datetime64[ns]"

    def test_prices_become_floats(self, dirty_products: pd.DataFrame):
        result, _ = transform_products(dirty_products)

        assert str(result["price"].dtype) == "float64"


class TestDateNormalization:
    """Normalisation of the date formats."""

    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            ("2025-01-15", "2025-01-15"),
            ("15/01/2025", "2025-01-15"),
            ("2025-01-15 14:30:00", "2025-01-15"),
        ],
    )
    def test_parses_every_supported_format(self, raw_value: str, expected: str):
        result = _parse_dates(pd.Series([raw_value]))

        assert result.iloc[0].strftime("%Y-%m-%d") == expected

    def test_unparsable_date_becomes_nat(self):
        result = _parse_dates(pd.Series(["not-a-date"]))

        assert pd.isna(result.iloc[0])

    def test_rejects_rows_with_unparsable_date(self, dirty_customers: pd.DataFrame):
        _, report = transform_customers(dirty_customers)

        assert "created_at not parsable" in report.rejected


class TestEmailCleaning:
    """Normalisation of the email addresses."""

    @pytest.mark.parametrize(
        ("raw_value", "expected"),
        [
            ("AMADOU@EXAMPLE.COM", "amadou@example.com"),
            ("  marie@example.com  ", "marie@example.com"),
            ("already.clean@example.com", "already.clean@example.com"),
        ],
    )
    def test_normalizes_valid_emails(self, raw_value: str, expected: str):
        assert _normalize_email(pd.Series([raw_value])).iloc[0] == expected

    @pytest.mark.parametrize(
        "invalid", ["no-at-sign", "two@@at-signs.com", "no-domain@", "@no-local-part.com"]
    )
    def test_invalid_email_becomes_null(self, invalid: str):
        assert pd.isna(_normalize_email(pd.Series([invalid])).iloc[0])

    def test_invalid_email_does_not_remove_the_customer(self, dirty_customers: pd.DataFrame):
        """A business choice: we keep the customer and clear their email."""
        result, _ = transform_customers(dirty_customers)

        customer_3 = result[result["customer_id"] == 3]
        assert len(customer_3) == 1
        assert pd.isna(customer_3["email"].iloc[0])


class TestTextNormalization:
    """Cleaning of the text fields."""

    def test_strips_and_titlecases(self, dirty_customers: pd.DataFrame):
        result, _ = transform_customers(dirty_customers)

        assert result["first_name"].iloc[0] == "Amadou"  # "  Amadou " cleaned
        assert set(result["country"]) <= {"Senegal", "France", "Mali"}  # casing unified


class TestPriceValidation:
    """Price validation."""

    def test_rejects_negative_price(self, dirty_products: pd.DataFrame):
        result, report = transform_products(dirty_products)

        assert "price negative" in report.rejected
        assert (result["price"] >= 0).all()

    def test_rejects_missing_price(self, dirty_products: pd.DataFrame):
        _, report = transform_products(dirty_products)

        assert "price missing or not numeric" in report.rejected

    def test_keeps_valid_products(self, dirty_products: pd.DataFrame):
        result, _ = transform_products(dirty_products)

        assert set(result["product_id"]) == {1, 4}


class TestQuantityValidation:
    """Quantity validation."""

    def test_rejects_zero_and_negative(self, dirty_orders: pd.DataFrame):
        result, report = transform_orders(dirty_orders)

        assert "quantity <= 0" in report.rejected
        assert (result["quantity"] > 0).all()

    def test_rejects_missing_quantity(self, dirty_orders: pd.DataFrame):
        _, report = transform_orders(dirty_orders)

        assert "quantity missing" in report.rejected


class TestStatusValidation:
    """Order status validation."""

    def test_normalizes_case_before_judging(self, dirty_orders: pd.DataFrame):
        """ "PAID" is a casing mistake, not an unknown status."""
        result, _ = transform_orders(dirty_orders)

        assert 4 in set(result["order_id"])
        assert result[result["order_id"] == 4]["status"].iloc[0] == "paid"

    def test_rejects_unknown_status(self, dirty_orders: pd.DataFrame):
        result, report = transform_orders(dirty_orders)

        assert "status outside reference list" in report.rejected
        assert 6 not in set(result["order_id"])


class TestTransformReport:
    """Consistency of the transformation report."""

    def test_counters_add_up(self, dirty_orders: pd.DataFrame):
        result, report = transform_orders(dirty_orders)

        assert report.rows_in == len(dirty_orders)
        assert report.rows_out == len(result)
        assert report.rows_removed == report.rows_in - report.rows_out
