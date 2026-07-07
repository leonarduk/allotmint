import pytest
from pydantic import ValidationError

from backend.common.account_models import AccountRecord, OwnerSummaryRecord, PersonMetadata


class TestOwnerSummaryRecord:
    def test_missing_owner_raises(self) -> None:
        with pytest.raises(ValidationError):
            OwnerSummaryRecord.model_validate({})

    def test_blank_owner_raises(self) -> None:
        with pytest.raises(ValidationError):
            OwnerSummaryRecord.model_validate({"owner": "   "})

    def test_none_owner_raises(self) -> None:
        with pytest.raises(ValidationError):
            OwnerSummaryRecord.model_validate({"owner": None})

    def test_defaults_when_optional_fields_missing(self) -> None:
        record = OwnerSummaryRecord.model_validate({"owner": "alice"})

        assert record.accounts == []
        assert record.full_name is None
        assert record.email is None
        assert record.has_transactions_artifact is False

    def test_non_string_account_items_are_dropped(self) -> None:
        record = OwnerSummaryRecord.model_validate(
            {"owner": "alice", "accounts": ["isa", 1, None, {"slug": "sipp"}, "  "]}
        )

        assert record.accounts == ["isa"]

    def test_accounts_must_be_a_list(self) -> None:
        with pytest.raises(ValidationError):
            OwnerSummaryRecord.model_validate({"owner": "alice", "accounts": "isa"})

    def test_duplicate_accounts_are_deduped_case_insensitively(self) -> None:
        record = OwnerSummaryRecord.model_validate(
            {"owner": "alice", "accounts": ["isa", "ISA", "Isa", "sipp"]}
        )

        assert record.accounts == ["isa", "sipp"]

    def test_unknown_extra_fields_are_ignored(self) -> None:
        record = OwnerSummaryRecord.model_validate({"owner": "alice", "unexpected": "value"})

        assert not hasattr(record, "unexpected")


class TestPersonMetadata:
    def test_all_fields_optional(self) -> None:
        record = PersonMetadata.model_validate({})

        assert record.owner is None
        assert record.full_name is None
        assert record.holdings == []
        assert record.viewers == []

    def test_blank_strings_normalise_to_none(self) -> None:
        record = PersonMetadata.model_validate({"full_name": "   "})

        assert record.full_name is None

    def test_non_string_optional_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            PersonMetadata.model_validate({"email": 123})

    def test_dob_datetime_normalises_to_isoformat(self) -> None:
        import datetime as dt

        record = PersonMetadata.model_validate({"dob": dt.date(1990, 1, 2)})

        assert record.dob == "1990-01-02"

    def test_viewers_deduped_case_insensitively(self) -> None:
        record = PersonMetadata.model_validate({"viewers": ["Bob", "bob", "alice", ""]})

        assert record.viewers == ["Bob", "alice"]

    def test_viewers_must_be_list(self) -> None:
        with pytest.raises(ValidationError):
            PersonMetadata.model_validate({"viewers": "bob"})


class TestAccountRecord:
    def test_defaults_when_fields_missing(self) -> None:
        record = AccountRecord.model_validate({})

        assert record.account_type is None
        assert record.holdings == []
        assert record.approvals == []

    def test_extra_keys_are_preserved(self) -> None:
        record = AccountRecord.model_validate({"account_type": "ISA", "custom_field": "kept"})

        assert record.model_extra["custom_field"] == "kept"

    def test_holdings_must_be_list(self) -> None:
        with pytest.raises(ValidationError):
            AccountRecord.model_validate({"holdings": "not-a-list"})
