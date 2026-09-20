from datetime import date

import pytest

from zongheng_mcp.services.qualifications import classify_expiry


@pytest.mark.parametrize(
    ("expiry", "expected_status", "expected_days"),
    [
        (None, "long_term", None),
        (date(2026, 9, 19), "expired", -1),
        (date(2026, 9, 20), "expiring", 0),
        (date(2026, 12, 19), "expiring", 90),
        (date(2026, 12, 20), "valid", 91),
    ],
)
def test_classify_expiry_boundaries(expiry, expected_status, expected_days):
    result = classify_expiry(expiry, today=date(2026, 9, 20), warning_days=90)
    assert result.status == expected_status
    assert result.days_remaining == expected_days

