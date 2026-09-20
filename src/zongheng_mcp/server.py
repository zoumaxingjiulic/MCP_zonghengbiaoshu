import argparse
import asyncio
import logging
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from .config import DbSettings, load_db_settings
from .database import Database
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Zongheng qualification read-only MCP server")
    parser.add_argument("--env-file", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    logging.getLogger("zongheng_mcp.audit").setLevel(logging.INFO)
    try:
        settings = load_db_settings(args.env_file)
    except (ValidationError, OSError, ValueError):
        print("CONFIG_ERROR: 请检查私密配置文件及数据库环境变量。", file=sys.stderr)
        raise SystemExit(2) from None
    try:
        asyncio.run(serve_stdio(settings))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

