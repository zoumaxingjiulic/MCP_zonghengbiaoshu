from datetime import UTC, date, datetime

import pytest

from zongheng_mcp.errors import BusinessError
from zongheng_mcp.repositories.qualifications import RepositoryPage
from zongheng_mcp.schemas import (
    ExpiringQuery,
    ExternalSearch,
    InternalSearch,
    ManufacturerQuery,
    MonthlyStatsQuery,
    OverviewQuery,
)
from zongheng_mcp.services.qualifications import QualificationService, classify_expiry


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


class FakeQualificationRepository:
    def search_internal(self, query):
        return RepositoryPage(
            total=1,
            rows=[
                {
                    "id": 1,
                    "uid": "int-1",
                    "cert_no": "MA001",
                    "product_name": "采煤机",
                    "product_model": "M1",
                    "start_date": datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                    "expire_date": datetime(2027, 1, 1, 0, 0, tzinfo=UTC),
                    "product_type": "设备",
                    "category": "安标",
                }
            ],
        )

    def search_external(self, query):
        return RepositoryPage(
            total=1,
            rows=[
                {
                    "id": 2,
                    "uid": "ext-1",
                    "item_code": "001-A",
                    "product_name": "电机",
                    "product_model": "E1",
                    "manufacturer": " 示例厂家 ",
                    "category": "防爆",
                    "start_date": date(2025, 9, 30),
                    "expire_date": date(2026, 9, 30),
                }
            ],
        )

    def list_expiring(self, query):
        return [
            {
                "source": "external",
                "id": 3,
                "uid": "ext-2",
                "cert_no": None,
                "item_code": "002-B",
                "product_name": "开关",
                "product_model": "S1",
                "manufacturer": "厂家乙",
                "category": "3C",
                "start_date": date(2025, 1, 1),
                "expire_date": date(2026, 9, 25),
                "days_remaining": 5,
            },
            {
                "source": "internal",
                "id": 1,
                "uid": "int-1",
                "cert_no": "MA001",
                "item_code": None,
                "product_name": "采煤机",
                "product_model": "M1",
                "manufacturer": None,
                "category": "安标",
                "start_date": date(2025, 1, 1),
                "expire_date": date(2026, 9, 22),
                "days_remaining": 2,
            },
        ]

    def list_manufacturers(self, query):
        return [{"name": " 示例厂家 ", "qualification_count": 3}]

    def get_overview(self, query):
        return {
            "internal": {"total": 10, "valid": 4, "expiring": 2, "expired": 3, "long_term": 1},
            "external": {"total": 20, "valid": 10, "expiring": 4, "expired": 5, "long_term": 1},
            "internal_categories": [{"category": "安标", "count": 10}],
            "external_categories": [{"category": "防爆", "count": 12}],
            "manufacturer_count": 6,
        }

    def get_monthly_counts(self, query):
        return [{"month": "2026-01", "count": 2}, {"month": "2026-03", "count": 1}]


def service():
    return QualificationService(
        FakeQualificationRepository(), today=lambda: date(2026, 9, 20)
    )


def test_searches_normalize_dates_text_and_expiry():
    internal = service().search_internal(InternalSearch())
    external = service().search_external(ExternalSearch())
    assert internal.items[0].start_date == date(2026, 1, 1)
    assert internal.items[0].expiry_status == "valid"
    assert external.items[0].manufacturer == "示例厂家"
    assert external.items[0].expiry_status == "expiring"
    assert external.items[0].days_remaining == 10


def test_expiring_items_are_sorted_by_days_remaining():
    result = service().list_expiring(ExpiringQuery())
    assert [item.days_remaining for item in result.items] == [2, 5]
    assert result.items[0].source == "internal"


def test_manufacturers_are_trimmed():
    result = service().list_manufacturers(ManufacturerQuery())
    assert result.items[0].name == "示例厂家"
    assert result.items[0].qualification_count == 3


def test_overview_calculates_cross_source_totals():
    result = service().get_overview(OverviewQuery())
    assert result.total_expiring == 6
    assert result.total_expired == 8
    assert result.external_categories[0].category == "防爆"


def test_monthly_statistics_fills_missing_months():
    result = service().get_monthly_statistics(
        MonthlyStatsQuery(source="internal", start_month="2026-01", end_month="2026-03")
    )
    assert [(row.month, row.count) for row in result.items] == [
        ("2026-01", 2),
        ("2026-02", 0),
        ("2026-03", 1),
    ]


def test_database_timeout_becomes_retryable_business_error():
    class TimeoutRepository(FakeQualificationRepository):
        def search_internal(self, query):
            raise TimeoutError("driver details must not escape")

    query_service = QualificationService(TimeoutRepository())
    with pytest.raises(BusinessError) as exc:
        query_service.search_internal(InternalSearch())
    assert exc.value.code == "DATABASE_TIMEOUT"
    assert exc.value.retryable
    assert "driver details" not in exc.value.message
