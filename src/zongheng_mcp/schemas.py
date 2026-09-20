from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpiryStatus(StrEnum):
    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    LONG_TERM = "long_term"


class QuerySource(StrEnum):
    ALL = "all"
    INTERNAL = "internal"
    EXTERNAL = "external"


class QualificationSource(StrEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class SearchBase(StrictModel):
    expiry_status: ExpiryStatus | None = None
    warning_days: int = Field(default=90, ge=1, le=3650)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class InternalSearch(SearchBase):
    keyword: str | None = None
    category: str | None = None

    @field_validator("keyword", "category", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)


class ExternalSearch(SearchBase):
    keyword: str | None = None
    item_code: str | None = None
    manufacturer: str | None = None
    category: str | None = None

    @field_validator("keyword", "item_code", "manufacturer", "category", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)


class ExpiringQuery(StrictModel):
    source: QuerySource = QuerySource.ALL
    days: int = Field(default=90, ge=1, le=3650)
    limit: int = Field(default=100, ge=1, le=200)


class ManufacturerQuery(StrictModel):
    keyword: str | None = None
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("keyword", mode="before")
    @classmethod
    def clean_optional_text(cls, value):
        return _clean_optional_text(value)


class OverviewQuery(StrictModel):
    warning_days: int = Field(default=90, ge=1, le=3650)


class MonthlyStatsQuery(StrictModel):
    source: QualificationSource
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    @model_validator(mode="after")
    def valid_range(self):
        start_year, start_month = map(int, self.start_month.split("-"))
        end_year, end_month = map(int, self.end_month.split("-"))
        span = (end_year - start_year) * 12 + end_month - start_month + 1
        if span < 1:
            raise ValueError("结束月份不能早于开始月份")
        if span > 60:
            raise ValueError("月份区间不能超过 60 个月")
        return self


class InternalCertificate(StrictModel):
    id: int
    uid: str | None = None
    cert_no: str | None = None
    product_name: str | None = None
    product_model: str | None = None
    start_date: date | None = None
    expire_date: date | None = None
    product_type: str | None = None
    category: str | None = None
    expiry_status: ExpiryStatus
    days_remaining: int | None = None


class ExternalCertification(StrictModel):
    id: int
    uid: str | None = None
    item_code: str | None = None
    product_name: str | None = None
    product_model: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    start_date: date | None = None
    expire_date: date | None = None
    expiry_status: ExpiryStatus
    days_remaining: int | None = None


class ExpiringCertificate(StrictModel):
    source: QualificationSource
    id: int
    uid: str | None = None
    cert_no: str | None = None
    item_code: str | None = None
    product_name: str | None = None
    product_model: str | None = None
    manufacturer: str | None = None
    category: str | None = None
    start_date: date | None = None
    expire_date: date
    days_remaining: int


class ManufacturerSummary(StrictModel):
    name: str
    qualification_count: int = Field(ge=0)


class CategoryCount(StrictModel):
    category: str
    count: int = Field(ge=0)


class StatusSummary(StrictModel):
    total: int = Field(ge=0)
    valid: int = Field(ge=0)
    expiring: int = Field(ge=0)
    expired: int = Field(ge=0)
    long_term: int = Field(ge=0)


class QualificationOverview(StrictModel):
    internal: StatusSummary
    external: StatusSummary
    internal_categories: list[CategoryCount]
    external_categories: list[CategoryCount]
    manufacturer_count: int = Field(ge=0)
    total_expiring: int = Field(ge=0)
    total_expired: int = Field(ge=0)


class MonthCount(StrictModel):
    month: str
    count: int = Field(ge=0)


class PageData[ItemT](StrictModel):
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    items: list[ItemT]


class ListData[ItemT](StrictModel):
    total: int = Field(ge=0)
    returned: int = Field(ge=0)
    items: list[ItemT]


class ErrorInfo(StrictModel):
    code: str
    message: str
    retryable: bool = False


class ToolResult[DataT](StrictModel):
    trace_id: str
    success: bool
    data: DataT | None = None
    error: ErrorInfo | None = None
    created_at: datetime | None = None


def _clean_optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    return cleaned or None
