from datetime import date

import pytest
from pydantic import ValidationError

from zongheng_mcp.schemas import (
    ExternalSearch,
    InternalSearch,
    MonthlyStatsQuery,
)


def test_search_input_rejects_extra_fields_and_invalid_page():
    with pytest.raises(ValidationError):
        InternalSearch.model_validate({"page": 0, "unknown": "x"})
    with pytest.raises(ValidationError):
        InternalSearch(page_size=101)


def test_optional_search_text_is_trimmed_and_blank_becomes_none():
    query = ExternalSearch(keyword="  煤机  ", manufacturer="   ", item_code=" 001-A ")
    assert query.keyword == "煤机"
    assert query.manufacturer is None
    assert query.item_code == "001-A"


def test_month_range_is_validated_and_limited_to_sixty_months():
    valid = MonthlyStatsQuery(source="internal", start_month="2026-01", end_month="2030-12")
    assert valid.start_month == "2026-01"
    with pytest.raises(ValidationError):
        MonthlyStatsQuery(source="internal", start_month="2026-13", end_month="2027-01")
    with pytest.raises(ValidationError):
        MonthlyStatsQuery(source="external", start_month="2027-02", end_month="2027-01")
    with pytest.raises(ValidationError):
        MonthlyStatsQuery(source="internal", start_month="2026-01", end_month="2031-01")


def test_date_fields_serialize_as_iso_dates():
    from zongheng_mcp.schemas import InternalCertificate

    item = InternalCertificate(
        id=1,
        uid="u-1",
        cert_no="MA001",
        product_name="采煤机",
        product_model="M1",
        product_type="设备",
        category="安标",
        start_date=date(2026, 1, 1),
        expire_date=date(2027, 1, 1),
        expiry_status="valid",
        days_remaining=103,
    )
    assert item.model_dump(mode="json")["start_date"] == "2026-01-01"

