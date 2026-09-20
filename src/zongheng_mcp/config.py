import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class DbSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    host: str
    port: int = Field(default=3306, ge=1, le=65535)
    user: str
    password: SecretStr
    name: str
    connect_timeout: int = Field(default=10, ge=1, le=60)
    read_timeout: int = Field(default=30, ge=1, le=300)
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=10, ge=0, le=100)

    @field_validator("host", "user", "name")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        if not value or value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("数据库配置不能为空或包含首尾空白/控制字符")
        return value

    @field_validator("password")
    @classmethod
    def non_blank_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if not password or password != password.strip() or any(ord(char) < 32 for char in password):
            raise ValueError("数据库密码不能为空或包含首尾空白/控制字符")
        return value


class HttpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    access_token: SecretStr
    allowed_hosts: list[str]
    allowed_origins: list[str] = Field(default_factory=list)
    max_request_body_size: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    max_sessions: int = Field(default=64, ge=1, le=1_024)
    session_idle_timeout: float = Field(default=300, ge=10, le=3_600)

    @field_validator("access_token")
    @classmethod
    def strong_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if not 32 <= len(token) <= 512 or token != token.strip() or any(ord(char) < 33 for char in token):
            raise ValueError("MCP Token 必须为 32–512 个无空白可打印字符")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def hosts_are_required(cls, values: list[str]) -> list[str]:
        if not values or any(not value or "://" in value or "/" in value for value in values):
            raise ValueError("必须配置合法的 Host 白名单")
        return values

    @field_validator("allowed_origins")
    @classmethod
    def origins_are_exact(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.geturl() != value:
                raise ValueError("Origin 必须是精确的 HTTP(S) 来源")
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
                raise ValueError("Origin 不能包含路径、查询、片段或凭据")
        return values


def _source(env_file: Path | None, environ: Mapping[str, str] | None) -> dict[str, str]:
    source = {key: value for key, value in dotenv_values(env_file).items() if value is not None} if env_file else {}
    source.update(dict(os.environ if environ is None else environ))
    return source


def _csv(value: str | None, default: str = "") -> list[str]:
    return [item.strip() for item in (value or default).split(",") if item.strip()]


def load_db_settings(
    env_file: Path | None = None, *, environ: Mapping[str, str] | None = None
) -> DbSettings:
    source = _source(env_file, environ)
    return DbSettings.model_validate(
        {
            "host": source.get("ZONGHENG_DB_HOST", ""),
            "port": source.get("ZONGHENG_DB_PORT", "3306"),
            "user": source.get("ZONGHENG_DB_USER", ""),
            "password": source.get("ZONGHENG_DB_PASSWORD", ""),
            "name": source.get("ZONGHENG_DB_NAME", ""),
            "connect_timeout": source.get("ZONGHENG_DB_CONNECT_TIMEOUT", "10"),
            "read_timeout": source.get("ZONGHENG_DB_READ_TIMEOUT", "30"),
            "pool_size": source.get("ZONGHENG_DB_POOL_SIZE", "5"),
            "max_overflow": source.get("ZONGHENG_DB_MAX_OVERFLOW", "10"),
        }
    )


def load_http_settings(
    env_file: Path | None = None, *, environ: Mapping[str, str] | None = None
) -> HttpSettings:
    source = _source(env_file, environ)
    return HttpSettings.model_validate(
        {
            "access_token": source.get("MCP_ACCESS_TOKEN", ""),
            "allowed_hosts": _csv(
                source.get("MCP_ALLOWED_HOSTS"), "localhost:*,127.0.0.1:*"
            ),
            "allowed_origins": _csv(source.get("MCP_ALLOWED_ORIGINS")),
            "max_request_body_size": source.get("MCP_MAX_REQUEST_BODY_SIZE", "1048576"),
            "max_sessions": source.get("MCP_MAX_SESSIONS", "64"),
            "session_idle_timeout": source.get("MCP_SESSION_IDLE_TIMEOUT", "300"),
        }
    )
