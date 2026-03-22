from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OwnerSummaryRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    owner: str
    accounts: list[str] = Field(default_factory=list)
    full_name: str | None = None
    email: str | None = None
    has_transactions_artifact: bool = False

    @field_validator("owner")
    @classmethod
    def _clean_owner(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("owner is required")
        return cleaned

    @field_validator("accounts", mode="before")
    @classmethod
    def _normalise_accounts(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("accounts must be a list")
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                continue
            account = item.strip()
            if not account:
                continue
            key = account.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(account)
        return cleaned


class PersonMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    owner: str | None = None
    full_name: str | None = None
    display_name: str | None = None
    preferred_name: str | None = None
    dob: str | None = None
    email: str | None = None
    holdings: list[Any] = Field(default_factory=list)
    viewers: list[str] = Field(default_factory=list)

    @field_validator(
        "owner",
        "full_name",
        "display_name",
        "preferred_name",
        "email",
        mode="before",
    )
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("expected string")
        cleaned = value.strip()
        return cleaned or None

    @field_validator("dob", mode="before")
    @classmethod
    def _normalise_dob(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        if not isinstance(value, str):
            raise ValueError("expected string")
        cleaned = value.strip()
        return cleaned or None

    @field_validator("holdings", mode="before")
    @classmethod
    def _normalise_holdings(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("holdings must be a list")
        return value

    @field_validator("viewers", mode="before")
    @classmethod
    def _normalise_viewers(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, tuple | set):
            value = list(value)
        if not isinstance(value, list):
            raise ValueError("viewers must be a list")
        viewers: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            viewers.append(cleaned)
        return viewers


class AccountRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    account_type: str | None = None
    account: str | None = None
    currency: str | None = None
    last_updated: str | None = None
    holdings: list[Any] = Field(default_factory=list)
    approvals: list[Any] = Field(default_factory=list)

    @field_validator("account_type", "account", "currency", "last_updated", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("expected string")
        cleaned = value.strip()
        return cleaned or None

    @field_validator("holdings", "approvals", mode="before")
    @classmethod
    def _ensure_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("expected list")
        return value
