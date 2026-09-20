from sqlalchemy.engine import URL

from zongheng_mcp.config import DbSettings
from zongheng_mcp.database import build_database_url


def test_database_url_escapes_raw_special_password():
    settings = DbSettings(
        host="db.internal",
        port=3306,
        user="reader",
        password="p@ss:%",
        name="business",
    )
    url = build_database_url(settings)
    assert isinstance(url, URL)
    assert url.password == "p@ss:%"
    rendered = url.render_as_string(hide_password=False)
    assert "p%40ss%3A%25" in rendered
    assert "charset=utf8mb4" in rendered

