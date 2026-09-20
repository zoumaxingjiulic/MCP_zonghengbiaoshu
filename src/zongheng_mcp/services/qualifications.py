from dataclasses import dataclass
from datetime import date

from ..schemas import ExpiryStatus


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

