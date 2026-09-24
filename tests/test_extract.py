"""Tests of the EXTRACT step.

Extraction has a single job: accept what conforms, refuse the rest. So these
tests mostly check that it fails CORRECTLY - with the right exception and a
message you can act on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.extract.extract import extract_all, extract_dataset
from src.utils.datasets import CUSTOMERS
from src.utils.exceptions import (
    EmptySourceError,
    MissingSourceFileError,
    SchemaValidationError,
)


class TestFilePresence:
    """Is the source file there?"""

    def test_reads_an_existing_valid_file(self, raw_dir: Path, valid_customers_csv: Path):
        frame = extract_dataset(CUSTOMERS, source_dir=raw_dir)

        assert len(frame) == 2
        assert list(frame.columns) == list(CUSTOMERS.required_columns)

    def test_raises_when_file_is_missing(self, raw_dir: Path):
        with pytest.raises(MissingSourceFileError) as error:
            extract_dataset(CUSTOMERS, source_dir=raw_dir)

        # The message must help fix things, not just report the breakage.
        assert "customers.csv" in str(error.value)
        assert "make seed" in str(error.value)

    def test_raises_when_directory_does_not_exist(self, tmp_path: Path):
        with pytest.raises(MissingSourceFileError):
            extract_dataset(CUSTOMERS, source_dir=tmp_path / "does-not-exist")


class TestSchemaValidation:
    """Does the file honour the column contract?"""

    def test_raises_when_a_required_column_is_missing(self, raw_dir: Path):
        # `country` is missing from the file
        (raw_dir / "customers.csv").write_text(
            "customer_id,first_name,last_name,email,created_at\n"
            "1,Amadou,Diallo,a@example.com,2025-01-15\n",
            encoding="utf-8",
        )

        with pytest.raises(SchemaValidationError) as error:
            extract_dataset(CUSTOMERS, source_dir=raw_dir)

        assert "country" in str(error.value)

    def test_accepts_extra_columns(self, raw_dir: Path):
        """An extra column must not break the pipeline.

        A source enriching its export is a normal event; refusing the file
        would make the pipeline needlessly fragile.
        """
        (raw_dir / "customers.csv").write_text(
            "customer_id,first_name,last_name,email,country,created_at,loyalty_tier\n"
            "1,Amadou,Diallo,a@example.com,Senegal,2025-01-15,gold\n",
            encoding="utf-8",
        )

        frame = extract_dataset(CUSTOMERS, source_dir=raw_dir)

        assert "loyalty_tier" in frame.columns
        assert len(frame) == 1


class TestEmptyFiles:
    """Does the file hold any data?"""

    def test_raises_when_file_has_header_but_no_rows(self, raw_dir: Path):
        (raw_dir / "customers.csv").write_text(
            "customer_id,first_name,last_name,email,country,created_at\n",
            encoding="utf-8",
        )

        with pytest.raises(EmptySourceError):
            extract_dataset(CUSTOMERS, source_dir=raw_dir)

    def test_raises_when_file_is_completely_empty(self, raw_dir: Path):
        (raw_dir / "customers.csv").write_text("", encoding="utf-8")

        with pytest.raises(EmptySourceError):
            extract_dataset(CUSTOMERS, source_dir=raw_dir)


class TestValueFidelity:
    """Extraction must interpret NOTHING."""

    def test_keeps_everything_as_text(self, raw_dir: Path, valid_customers_csv: Path):
        """Identifiers stay text until the transformation.

        If pandas typed them itself, an identifier "007" would become 7 and the
        match with the source system would be lost.
        """
        frame = extract_dataset(CUSTOMERS, source_dir=raw_dir)

        assert frame["customer_id"].dtype == object
        assert frame["customer_id"].iloc[0] == "1"

    def test_does_not_convert_na_strings_to_null(self, raw_dir: Path):
        """The text "NA" is a value, not the absence of one."""
        (raw_dir / "customers.csv").write_text(
            "customer_id,first_name,last_name,email,country,created_at\n"
            "1,Amadou,NA,a@example.com,Senegal,2025-01-15\n",
            encoding="utf-8",
        )

        frame = extract_dataset(CUSTOMERS, source_dir=raw_dir)

        assert frame["last_name"].iloc[0] == "NA"


class TestExtractAll:
    """Extraction of the three datasets."""

    def test_fails_if_any_source_is_missing(self, raw_dir: Path, valid_customers_csv: Path):
        """A partial set is more dangerous than no load at all."""
        with pytest.raises(MissingSourceFileError):
            extract_all(source_dir=raw_dir)
