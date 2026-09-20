from dataclasses import dataclass, field

from zongheng_mcp.repositories.qualifications import QualificationRepository
from zongheng_mcp.schemas import (
    ExpiringQuery,
    ExternalSearch,
    InternalSearch,
    ManufacturerQuery,
    MonthlyStatsQuery,
    OverviewQuery,
)


@dataclass
class RecordingDatabase:
    calls: list[tuple[str, str, dict]] = field(default_factory=list)
    scalar_values: list[int] = field(default_factory=lambda: [0])
    row_values: list[list[dict]] = field(default_factory=lambda: [[]])

    def scalar(self, statement, params):
        self.calls.append(("scalar", str(statement), dict(params)))
        return self.scalar_values.pop(0) if self.scalar_values else 0

    def rows(self, statement, params):
        self.calls.append(("rows", str(statement), dict(params)))
        return self.row_values.pop(0) if self.row_values else []


def normalized_sql(sql: str) -> str:
    return " ".join(sql.split())


def test_internal_search_is_bound_explicit_and_filters_deleted():
    database = RecordingDatabase(scalar_values=[7], row_values=[[{"id": 1}]])
    result = QualificationRepository(database).search_internal(
        InternalSearch(keyword="%煤机_", category="安标", page=2, page_size=20)
    )
    assert result.total == 7
    assert result.rows == [{"id": 1}]
    for _, sql, _ in database.calls:
        assert "custom_table_97" in sql
        assert "logic_del = 0" in sql
        assert "%煤机_" not in sql
    data_sql = normalized_sql(database.calls[1][1])
    assert "SELECT *" not in data_sql.upper()
    assert "column_427 AS cert_no" in data_sql
    params = database.calls[1][2]
    assert params["keyword"] == "%\\%煤机\\_%"
    assert params["category"] == "安标"
    assert params["limit"] == 20
    assert params["offset"] == 20


def test_external_search_uses_all_filters_as_parameters():
    database = RecordingDatabase(scalar_values=[1], row_values=[[{"id": 2}]])
    QualificationRepository(database).search_external(
        ExternalSearch(
            keyword="采煤机",
            item_code="001-A",
            manufacturer="示例厂",
            category="防爆",
            expiry_status="valid",
        )
    )
    sql = normalized_sql(database.calls[1][1])
    params = database.calls[1][2]
    assert "custom_table_103" in sql
    assert "logic_del = 0" in sql
    assert "DATEDIFF(column_425, CURDATE()) > :warning_days" in sql
    assert "001-A" not in sql and "示例厂" not in sql
    assert params["item_code"] == "001-A"
    assert params["manufacturer"] == "%示例厂%"
    assert params["category"] == "%防爆%"


def test_all_repository_paths_filter_deleted_and_only_use_whitelist_tables():
    database = RecordingDatabase(
        scalar_values=[0, 0],
        row_values=[[], [], [], [], [], [], [], [], []],
    )
    repository = QualificationRepository(database)
    repository.list_expiring(ExpiringQuery())
    repository.list_manufacturers(ManufacturerQuery())
    repository.get_overview(OverviewQuery())
    repository.get_monthly_counts(
        MonthlyStatsQuery(source="internal", start_month="2026-01", end_month="2026-03")
    )
    assert database.calls
    for _, sql, _ in database.calls:
        assert "logic_del = 0" in sql
        assert "SELECT *" not in sql.upper()
        lowered = sql.lower()
        assert "custom_table_97" in lowered or "custom_table_103" in lowered
        assert "basic_table_" not in lowered and "sys_" not in lowered


def test_monthly_statistics_uses_whitelisted_table_and_bounded_dates():
    database = RecordingDatabase(row_values=[[]])
    QualificationRepository(database).get_monthly_counts(
        MonthlyStatsQuery(source="external", start_month="2026-01", end_month="2026-03")
    )
    _, sql, params = database.calls[0]
    assert "custom_table_103" in sql
    assert "column_425" in sql
    assert params == {"start_date": "2026-01-01", "end_date": "2026-04-01"}

