"""Typed contracts for the India-only synthetic VendorFlow AI prototype."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Status(str, Enum):
    APPROVED = "APPROVED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"  # only manual administrative decisions


class CheckState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class VendorSubmission(BaseModel):
    """Do not overvalidate: missing fields must become actionable PENDING checks."""

    legal_name: str = ""
    business_state: str = ""
    contact_name: str = ""
    contact_email: str = ""
    pan: str = ""
    gstin: str = ""
    bank_holder: str = ""
    account_number: str = ""
    ifsc: str = ""


class GSTExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    legal_name: str | None = Field(description="Legal business name printed on GST certificate; not trade name")
    gstin: str | None = Field(description="15-character GST registration number printed in certificate")
    state: str | None = Field(description="Indian state or UT explicitly printed on GST document")
    address: str | None = Field(description="Business address if printed, otherwise null")


class BankExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    holder_name: str | None = Field(description="Account holder name explicitly printed on bank proof")
    account_number: str | None = Field(description="Account number as text including leading zeroes")
    ifsc: str | None = Field(description="11-character IFSC explicitly printed on bank proof")


class ExtractedDocuments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gst: GSTExtraction
    bank: BankExtraction

    @classmethod
    def empty(cls) -> "ExtractedDocuments":
        return cls(
            gst=GSTExtraction(legal_name=None, gstin=None, state=None, address=None),
            bank=BankExtraction(holder_name=None, account_number=None, ifsc=None),
        )


class CheckResult(BaseModel):
    rule_id: str
    state: CheckState
    code: str
    label: str
    vendor_message: str
    admin_detail: str = ""
    next_action: str = ""


class StageEvent(BaseModel):
    stage_id: str
    label: str
    event: Literal["STARTED", "COMPLETED", "FAILED", "SKIPPED"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str = ""


class WorkflowResult(BaseModel):
    application_id: str
    run_id: str
    trigger: Literal["submission", "resubmission"]
    status: Status
    decision_source: Literal["AUTOMATED"] = "AUTOMATED"
    reasons: list[str]
    all_reasons: list[str]
    next_action: str
    checks: list[CheckResult]
    extracted: ExtractedDocuments
    stage_events: list[StageEvent]
    started_at: datetime
    finished_at: datetime
    elapsed_ms: int
    persisted: bool = False
    extraction_error: bool = False
