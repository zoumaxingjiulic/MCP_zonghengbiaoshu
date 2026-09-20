import os

import pytest
from sqlalchemy import text

from zongheng_mcp.config import load_db_settings
from zongheng_mcp.database import Database
from zongheng_mcp.repositories.qualifications import QualificationRepository
from zongheng_mcp.schemas import (
    ExpiringQuery,
    ExternalSearch,
    InternalSearch,
    ManufacturerQuery,
    MonthlyStatsQuery,
    OverviewQuery,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_DB_TESTS") != "1", reason="live DB test is opt-in"
)


@pytest.fixture
def live_database():
    database = Database(load_db_settings())
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def live_repository(live_database):
    return QualificationRepository(live_database)


def test_live_search_totals_equal_active_record_totals(live_repository, live_database):
    internal = live_repository.search_internal(InternalSearch(page=1, page_size=5))
    external = live_repository.search_external(ExternalSearch(page=1, page_size=5))
    active_internal = live_database.scalar(
        text("SELECT COUNT(*) FROM custom_table_97 WHERE logic_del = 0"), {}
    )
    active_external = live_database.scalar(
        text("SELECT COUNT(*) FROM custom_table_103 WHERE logic_del = 0"), {}
    )
    assert internal.total == active_internal
    assert external.total == active_external
    assert len(internal.rows) <= 5
    assert len(external.rows) <= 5


def test_live_all_six_repository_capabilities_execute_read_only(live_repository):
    literal_wildcard = "__no_such_literal_%__"
    assert live_repository.search_internal(InternalSearch(keyword=literal_wildcard)).total == 0
    assert live_repository.search_external(ExternalSearch(keyword=literal_wildcard)).total == 0
    assert isinstance(live_repository.list_expiring(ExpiringQuery(days=90, limit=5)), list)
    assert isinstance(live_repository.list_manufacturers(ManufacturerQuery(limit=5)), list)
    overview = live_repository.get_overview(OverviewQuery())
    assert overview["internal"]["total"] >= 0
    assert overview["external"]["total"] >= 0
    monthly = live_repository.get_monthly_counts(
        MonthlyStatsQuery(source="internal", start_month="2026-01", end_month="2026-12")
    )
    assert isinstance(monthly, list)

