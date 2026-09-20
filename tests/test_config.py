from pathlib import Path

import pytest
from pydantic import ValidationError

from zongheng_mcp.config import DbSettings, HttpSettings, load_db_settings


def valid_db_values(**overrides):
    values = {
        "host": "db.internal",
        "port": 3306,
        "user": "reader",
        "password": "secret-value",
        "name": "business",
    }
    values.update(overrides)
    return values


def test_database_password_is_required_and_hidden():
    with pytest.raises(ValidationError) as exc:
        DbSettings.model_validate(valid_db_values(password=""))
    assert "secret-value" not in str(exc.value)


def test_database_port_and_pool_bounds_are_enforced():
    with pytest.raises(ValidationError):
        DbSettings.model_validate(valid_db_values(port=0))
    with pytest.raises(ValidationError):
        DbSettings.model_validate(valid_db_values(pool_size=51))


def test_http_token_and_hosts_are_restricted():
    settings = HttpSettings.model_validate(
        {"access_token": "x" * 32, "allowed_hosts": ["127.0.0.1:*"]}
    )
    assert settings.max_request_body_size == 1_048_576
    with pytest.raises(ValidationError):
        HttpSettings.model_validate({"access_token": "short", "allowed_hosts": []})


def test_env_file_is_explicit_and_raw_special_password_is_preserved(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ZONGHENG_DB_HOST=192.0.2.10\n"
        "ZONGHENG_DB_PORT=3306\n"
        "ZONGHENG_DB_USER=reader\n"
        "ZONGHENG_DB_PASSWORD=p@ss:%\n"
        "ZONGHENG_DB_NAME=business\n",
        encoding="utf-8",
    )
    settings = load_db_settings(env_file, environ={})
    assert settings.password.get_secret_value() == "p@ss:%"
