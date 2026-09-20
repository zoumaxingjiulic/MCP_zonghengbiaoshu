import os
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters


async def test_real_sdk_stdio_initialization_discovery_and_validation_error():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "zongheng_mcp.server"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env={
            **os.environ,
            "ZONGHENG_DB_HOST": "127.0.0.1",
            "ZONGHENG_DB_PORT": "3306",
            "ZONGHENG_DB_USER": "unused-reader",
            "ZONGHENG_DB_PASSWORD": "unused-secret",
            "ZONGHENG_DB_NAME": "unused-database",
        },
    )
    async with Client(params, read_timeout_seconds=10) as client:
        tools = (await client.list_tools()).tools
        assert len(tools) == 6
        assert tools[0].name == "zongheng_search_internal_certificates"
        result = await client.call_tool(tools[0].name, {"page_size": 101})
        assert result.is_error
        assert result.structured_content["error"]["code"] == "INVALID_ARGUMENT"

