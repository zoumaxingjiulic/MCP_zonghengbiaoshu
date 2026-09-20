import argparse
import asyncio
import logging
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError
from starlette.routing import Route

from .config import DbSettings, HttpSettings, load_db_settings, load_http_settings
from .database import Database
from .http import BearerTokenMiddleware, health
from .repositories.qualifications import QualificationRepository
from .services.qualifications import QualificationService
from .tools.qualifications import definitions, execute


def create_server(
    settings: DbSettings, *, service_factory: Callable[[], object] | None = None
) -> Server:
    @asynccontextmanager
    async def lifespan(server):
        if service_factory is not None:
            yield service_factory()
            return
        database = Database(settings)
        try:
            yield QualificationService(QualificationRepository(database))
        finally:
            database.dispose()

    async def list_tools(context, params):
        return types.ListToolsResult(tools=definitions())

    async def call_tool(context, params):
        if params.name not in {tool.name for tool in definitions()}:
            raise MCPError(code=-32602, message="Unknown tool")
        return await execute(context.lifespan_context, params.name, params.arguments or {})

    return Server(
        "zongheng-qualification-mcp",
        version="0.1.0",
        lifespan=lifespan,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve_stdio(settings: DbSettings) -> None:
    server = create_server(settings)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def create_http_app(
    settings: DbSettings,
    http_settings: HttpSettings,
    *,
    service_factory: Callable[[], object] | None = None,
):
    server = create_server(settings, service_factory=service_factory)
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=False,
        max_request_body_size=http_settings.max_request_body_size,
        session_idle_timeout=http_settings.session_idle_timeout,
        max_sessions=http_settings.max_sessions,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=http_settings.allowed_hosts,
            allowed_origins=http_settings.allowed_origins,
        ),
        custom_starlette_routes=[Route("/healthz", health, methods=["GET"])],
    )
    return BearerTokenMiddleware(app, http_settings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zongheng qualification read-only MCP server")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    logging.getLogger("zongheng_mcp.audit").setLevel(logging.INFO)
    try:
        settings = load_db_settings(args.env_file)
        http_settings = load_http_settings(args.env_file) if args.transport == "streamable-http" else None
    except (ValidationError, OSError, ValueError):
        print("CONFIG_ERROR: 请检查私密配置文件及数据库环境变量。", file=sys.stderr)
        raise SystemExit(2) from None
    try:
        if args.transport == "stdio":
            asyncio.run(serve_stdio(settings))
        else:
            assert http_settings is not None
            uvicorn.run(
                create_http_app(settings, http_settings),
                host=args.host,
                port=args.port,
                access_log=False,
                proxy_headers=False,
                server_header=False,
            )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
