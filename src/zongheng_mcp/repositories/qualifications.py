from dataclasses import dataclass
from datetime import date

from sqlalchemy import text

from ..database import Database
from ..schemas import (
    ExpiringQuery,
    ExpiryStatus,
    ExternalSearch,
    InternalSearch,
    ManufacturerQuery,
    MonthlyStatsQuery,
    OverviewQuery,
    QualificationSource,
    QuerySource,
)


@dataclass(frozen=True)
class RepositoryPage:
    total: int
    rows: list[dict]


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like(value: str) -> str:
    return f"%{escape_like(value)}%"


def _expiry_condition(column: str, status: ExpiryStatus) -> str:
    conditions = {
        ExpiryStatus.VALID: f"{column} IS NOT NULL AND DATEDIFF({column}, CURDATE()) > :warning_days",
        ExpiryStatus.EXPIRING: (
            f"{column} IS NOT NULL AND DATEDIFF({column}, CURDATE()) BETWEEN 0 AND :warning_days"
        ),
        ExpiryStatus.EXPIRED: f"{column} IS NOT NULL AND {column} < CURDATE()",
        ExpiryStatus.LONG_TERM: f"{column} IS NULL",
    }
    return conditions[status]


class QualificationRepository:
    def __init__(self, database: Database):
        self.database = database

    def search_internal(self, query: InternalSearch) -> RepositoryPage:
        conditions = ["logic_del = 0"]
        params: dict = {}
        if query.keyword:
            conditions.append(
                "(column_428 LIKE :keyword ESCAPE '\\\\' OR column_427 LIKE :keyword ESCAPE '\\\\')"
            )
            params["keyword"] = _like(query.keyword)
        if query.category:
            conditions.append("column_433 = :category")
            params["category"] = query.category
        if query.expiry_status:
            conditions.append(_expiry_condition("column_431", query.expiry_status))
            params["warning_days"] = query.warning_days
        where = " AND ".join(conditions)
        total = self.database.scalar(
            text(f"SELECT COUNT(*) FROM custom_table_97 WHERE {where}"), params
        ) or 0
        page_params = {
            **params,
            "limit": query.page_size,
            "offset": (query.page - 1) * query.page_size,
        }
        rows = self.database.rows(
            text(
                "SELECT id, uid, column_427 AS cert_no, column_428 AS product_name, "
                "column_429 AS product_model, column_430 AS start_date, column_431 AS expire_date, "
                "column_432 AS product_type, column_433 AS category "
                f"FROM custom_table_97 WHERE {where} "
                "ORDER BY column_431 IS NULL, column_431 ASC, id ASC LIMIT :limit OFFSET :offset"
            ),
            page_params,
        )
        return RepositoryPage(total=int(total), rows=rows)

    def search_external(self, query: ExternalSearch) -> RepositoryPage:
        conditions = ["logic_del = 0"]
        params: dict = {}
        if query.keyword:
            conditions.append(
                "(column_1022 LIKE :keyword ESCAPE '\\\\' OR column_419 LIKE :keyword ESCAPE '\\\\' "
                "OR column_420 LIKE :keyword ESCAPE '\\\\' OR column_421 LIKE :keyword ESCAPE '\\\\')"
            )
            params["keyword"] = _like(query.keyword)
        if query.item_code:
            conditions.append("column_1022 = :item_code")
            params["item_code"] = query.item_code
        if query.manufacturer:
            conditions.append("column_421 LIKE :manufacturer ESCAPE '\\\\'")
            params["manufacturer"] = _like(query.manufacturer)
        if query.category:
            conditions.append("column_422 LIKE :category ESCAPE '\\\\'")
            params["category"] = _like(query.category)
        if query.expiry_status:
            conditions.append(_expiry_condition("column_425", query.expiry_status))
            params["warning_days"] = query.warning_days
        where = " AND ".join(conditions)
        total = self.database.scalar(
            text(f"SELECT COUNT(*) FROM custom_table_103 WHERE {where}"), params
        ) or 0
        page_params = {
            **params,
            "limit": query.page_size,
            "offset": (query.page - 1) * query.page_size,
        }
        rows = self.database.rows(
            text(
                "SELECT id, uid, column_1022 AS item_code, column_419 AS product_name, "
                "column_420 AS product_model, column_421 AS manufacturer, column_422 AS category, "
                "column_424 AS start_date, column_425 AS expire_date "
                f"FROM custom_table_103 WHERE {where} "
                "ORDER BY column_425 IS NULL, column_425 ASC, id ASC LIMIT :limit OFFSET :offset"
            ),
            page_params,
        )
        return RepositoryPage(total=int(total), rows=rows)

    def list_expiring(self, query: ExpiringQuery) -> list[dict]:
        internal = (
            "SELECT 'internal' AS source, id, uid, column_427 AS cert_no, NULL AS item_code, "
            "column_428 AS product_name, column_429 AS product_model, NULL AS manufacturer, "
            "column_433 AS category, column_430 AS start_date, column_431 AS expire_date, "
            "DATEDIFF(column_431, CURDATE()) AS days_remaining FROM custom_table_97 "
            "WHERE logic_del = 0 AND column_431 IS NOT NULL "
            "AND DATEDIFF(column_431, CURDATE()) BETWEEN 0 AND :days"
        )
        external = (
            "SELECT 'external' AS source, id, uid, NULL AS cert_no, column_1022 AS item_code, "
            "column_419 AS product_name, column_420 AS product_model, column_421 AS manufacturer, "
            "column_422 AS category, column_424 AS start_date, column_425 AS expire_date, "
            "DATEDIFF(column_425, CURDATE()) AS days_remaining FROM custom_table_103 "
            "WHERE logic_del = 0 AND column_425 IS NOT NULL "
            "AND DATEDIFF(column_425, CURDATE()) BETWEEN 0 AND :days"
        )
        if query.source == QuerySource.INTERNAL:
            body = internal
        elif query.source == QuerySource.EXTERNAL:
            body = external
        else:
            body = f"{internal} UNION ALL {external}"
        return self.database.rows(
            text(
                "SELECT source, id, uid, cert_no, item_code, product_name, product_model, "
                "manufacturer, category, start_date, expire_date, days_remaining "
                f"FROM ({body}) AS active_expiring ORDER BY days_remaining, id LIMIT :limit"
            ),
            {"days": query.days, "limit": query.limit},
        )

    def list_manufacturers(self, query: ManufacturerQuery) -> list[dict]:
        conditions = ["logic_del = 0", "column_421 IS NOT NULL", "column_421 != ''"]
        params: dict = {"limit": query.limit}
        if query.keyword:
            conditions.append("column_421 LIKE :keyword ESCAPE '\\\\'")
            params["keyword"] = _like(query.keyword)
        return self.database.rows(
            text(
                "SELECT TRIM(column_421) AS name, COUNT(*) AS qualification_count "
                f"FROM custom_table_103 WHERE {' AND '.join(conditions)} "
                "GROUP BY TRIM(column_421) ORDER BY qualification_count DESC, name ASC LIMIT :limit"
            ),
            params,
        )

    def get_overview(self, query: OverviewQuery) -> dict:
        internal = self._status_counts("custom_table_97", "column_431", query.warning_days)
        external = self._status_counts("custom_table_103", "column_425", query.warning_days)
        internal_categories = self._category_counts("custom_table_97", "column_433")
        external_categories = self._category_counts("custom_table_103", "column_422")
        manufacturer_count = self.database.scalar(
            text(
                "SELECT COUNT(DISTINCT TRIM(column_421)) FROM custom_table_103 "
                "WHERE logic_del = 0 AND column_421 IS NOT NULL AND column_421 != ''"
            ),
            {},
        ) or 0
        return {
            "internal": internal,
            "external": external,
            "internal_categories": internal_categories,
            "external_categories": external_categories,
            "manufacturer_count": int(manufacturer_count),
        }

    def get_monthly_counts(self, query: MonthlyStatsQuery) -> list[dict]:
        if query.source == QualificationSource.INTERNAL:
            table_name, expiry_column = "custom_table_97", "column_431"
        else:
            table_name, expiry_column = "custom_table_103", "column_425"
        start_date = f"{query.start_month}-01"
        year, month = map(int, query.end_month.split("-"))
        end_date = date(year + (month == 12), 1 if month == 12 else month + 1, 1).isoformat()
        return self.database.rows(
            text(
                f"SELECT DATE_FORMAT({expiry_column}, '%Y-%m') AS month, COUNT(*) AS count "
                f"FROM {table_name} WHERE logic_del = 0 AND {expiry_column} >= :start_date "
                f"AND {expiry_column} < :end_date GROUP BY DATE_FORMAT({expiry_column}, '%Y-%m') "
                "ORDER BY month"
            ),
            {"start_date": start_date, "end_date": end_date},
        )

    def _status_counts(self, table_name: str, expiry_column: str, warning_days: int) -> dict:
        rows = self.database.rows(
            text(
                "SELECT COUNT(*) AS total, "
                f"COALESCE(SUM(CASE WHEN {expiry_column} IS NULL THEN 1 ELSE 0 END), 0) AS long_term, "
                f"COALESCE(SUM(CASE WHEN {expiry_column} < CURDATE() THEN 1 ELSE 0 END), 0) AS expired, "
                f"COALESCE(SUM(CASE WHEN DATEDIFF({expiry_column}, CURDATE()) BETWEEN 0 "
                "AND :warning_days THEN 1 ELSE 0 END), 0) AS expiring, "
                f"COALESCE(SUM(CASE WHEN DATEDIFF({expiry_column}, CURDATE()) > :warning_days "
                f"THEN 1 ELSE 0 END), 0) AS valid FROM {table_name} WHERE logic_del = 0"
            ),
            {"warning_days": warning_days},
        )
        return rows[0] if rows else {"total": 0, "valid": 0, "expiring": 0, "expired": 0, "long_term": 0}

    def _category_counts(self, table_name: str, category_column: str) -> list[dict]:
        return self.database.rows(
            text(
                f"SELECT TRIM({category_column}) AS category, COUNT(*) AS count FROM {table_name} "
                f"WHERE logic_del = 0 AND {category_column} IS NOT NULL AND {category_column} != '' "
                f"GROUP BY TRIM({category_column}) ORDER BY count DESC, category ASC"
            ),
            {},
        )
