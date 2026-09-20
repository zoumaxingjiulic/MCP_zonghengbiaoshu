from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.exc import SQLAlchemyError

from ..errors import BusinessError
from ..schemas import (
    CategoryCount,
    ExpiringCertificate,
    ExpiringQuery,
    ExpiryStatus,
    ExternalCertification,
    ExternalSearch,
    InternalCertificate,
    InternalSearch,
    ListData,
    ManufacturerQuery,
    ManufacturerSummary,
    MonthCount,
    MonthlyStatsQuery,
    OverviewQuery,
    PageData,
    QualificationOverview,
    StatusSummary,
)


@dataclass(frozen=True)
class ExpiryInfo:
    status: ExpiryStatus
    days_remaining: int | None


def classify_expiry(expiry: date | None, *, today: date, warning_days: int) -> ExpiryInfo:
    if expiry is None:
        return ExpiryInfo(ExpiryStatus.LONG_TERM, None)
    days = (expiry - today).days
    if days < 0:
        return ExpiryInfo(ExpiryStatus.EXPIRED, days)
    if days <= warning_days:
        return ExpiryInfo(ExpiryStatus.EXPIRING, days)
    return ExpiryInfo(ExpiryStatus.VALID, days)


class QualificationService:
    def __init__(self, repository, *, today: Callable[[], date] = date.today):
        self.repository = repository
        self.today = today

    def search_internal(self, query: InternalSearch) -> PageData[InternalCertificate]:
        page = self._run(lambda: self.repository.search_internal(query))
        items = [self._internal_item(row, query.warning_days) for row in page.rows]
        return PageData(
            total=page.total,
            returned=len(items),
            page=query.page,
            page_size=query.page_size,
            items=items,
        )

    def search_external(self, query: ExternalSearch) -> PageData[ExternalCertification]:
        page = self._run(lambda: self.repository.search_external(query))
        items = [self._external_item(row, query.warning_days) for row in page.rows]
        return PageData(
            total=page.total,
            returned=len(items),
            page=query.page,
            page_size=query.page_size,
            items=items,
        )

    def list_expiring(self, query: ExpiringQuery) -> ListData[ExpiringCertificate]:
        rows = self._run(lambda: self.repository.list_expiring(query))
        items = [
            ExpiringCertificate(
                **{
                    **row,
                    "start_date": _as_date(row.get("start_date")),
                    "expire_date": _as_date(row["expire_date"]),
                }
            )
            for row in rows
        ]
        items.sort(key=lambda item: (item.days_remaining, item.id))
        return ListData(total=len(items), returned=len(items), items=items)

    def list_manufacturers(self, query: ManufacturerQuery) -> ListData[ManufacturerSummary]:
        rows = self._run(lambda: self.repository.list_manufacturers(query))
        items = [
            ManufacturerSummary(
                name=row["name"].strip(), qualification_count=row["qualification_count"]
            )
            for row in rows
            if row.get("name") and row["name"].strip()
        ]
        return ListData(total=len(items), returned=len(items), items=items)

    def get_overview(self, query: OverviewQuery) -> QualificationOverview:
        raw = self._run(lambda: self.repository.get_overview(query))
        internal = StatusSummary.model_validate(raw["internal"])
        external = StatusSummary.model_validate(raw["external"])
        return QualificationOverview(
            internal=internal,
            external=external,
            internal_categories=[CategoryCount.model_validate(row) for row in raw["internal_categories"]],
            external_categories=[CategoryCount.model_validate(row) for row in raw["external_categories"]],
            manufacturer_count=raw["manufacturer_count"],
            total_expiring=internal.expiring + external.expiring,
            total_expired=internal.expired + external.expired,
        )

    def get_monthly_statistics(self, query: MonthlyStatsQuery) -> ListData[MonthCount]:
        rows = self._run(lambda: self.repository.get_monthly_counts(query))
        counts = {row["month"]: int(row["count"]) for row in rows}
        months = _months(query.start_month, query.end_month)
        items = [MonthCount(month=month, count=counts.get(month, 0)) for month in months]
        return ListData(total=len(items), returned=len(items), items=items)

    def _internal_item(self, row: dict, warning_days: int) -> InternalCertificate:
        expire_date = _as_date(row.get("expire_date"))
        expiry = classify_expiry(expire_date, today=self.today(), warning_days=warning_days)
        return InternalCertificate(
            **{
                **row,
                "start_date": _as_date(row.get("start_date")),
                "expire_date": expire_date,
                "expiry_status": expiry.status,
                "days_remaining": expiry.days_remaining,
            }
        )

    def _external_item(self, row: dict, warning_days: int) -> ExternalCertification:
        expire_date = _as_date(row.get("expire_date"))
        expiry = classify_expiry(expire_date, today=self.today(), warning_days=warning_days)
        return ExternalCertification(
            **{
                **row,
                "manufacturer": _strip(row.get("manufacturer")),
                "start_date": _as_date(row.get("start_date")),
                "expire_date": expire_date,
                "expiry_status": expiry.status,
                "days_remaining": expiry.days_remaining,
            }
        )

    @staticmethod
    def _run(operation):
        try:
            return operation()
        except BusinessError:
            raise
        except TimeoutError:
            raise BusinessError(
                "DATABASE_TIMEOUT", "数据库查询超时，请稍后重试。", retryable=True
            ) from None
        except SQLAlchemyError:
            raise BusinessError(
                "DATABASE_UNAVAILABLE", "业务数据库暂时不可用，请稍后重试。", retryable=True
            ) from None


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _months(start: str, end: str) -> list[str]:
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    result = []
    while (year, month) <= (end_year, end_month):
        result.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return result
