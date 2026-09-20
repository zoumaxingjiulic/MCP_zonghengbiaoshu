import asyncio
import socket
import urllib.error
import urllib.request
from threading import Thread

import httpx2
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from zongheng_mcp.config import DbSettings, HttpSettings
from zongheng_mcp.schemas import ListData, ManufacturerSummary
from zongheng_mcp.server import create_http_app


class FakeService:
    def list_manufacturers(self, query):
        return ListData(
            total=1,
            returned=1,
            items=[ManufacturerSummary(name="示例厂家", qualification_count=2)],
        )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request_status(url: str, *, token: str | None = None, host: str | None = None) -> int:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if host:
        headers["Host"] = host
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


async def wait_ready(url: str) -> None:
    for _ in range(100):
        try:
            if await asyncio.to_thread(request_status, url) == 200:
                return
        except OSError:
            pass
        await asyncio.sleep(0.05)
    raise AssertionError("HTTP MCP server did not become ready")


async def test_streamable_http_auth_host_discovery_and_tool_call():
    port = free_port()
    token = "synthetic-mcp-token-" + "t" * 32
    db_settings = DbSettings(
        host="127.0.0.1",
        user="unused",
        password="unused-secret",
        name="unused",
    )
    http_settings = HttpSettings(
        access_token=token,
        allowed_hosts=["127.0.0.1:*"],
        max_request_body_size=1024,
        max_sessions=4,
        session_idle_timeout=30,
    )
    app = create_http_app(db_settings, http_settings, service_factory=FakeService)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="error")
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        await wait_ready(base_url + "/healthz")
        assert await asyncio.to_thread(request_status, base_url + "/mcp") == 401
        assert (
            await asyncio.to_thread(request_status, base_url + "/mcp", token="wrong-" + "x" * 32)
            == 401
        )
        assert (
            await asyncio.to_thread(
                request_status, base_url + "/mcp", token=token, host="evil.example"
            )
            == 421
        )
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, trust_env=False
        ) as http_client:
            transport = streamable_http_client(base_url + "/mcp", http_client=http_client)
            async with Client(transport, read_timeout_seconds=10) as client:
                tools = (await client.list_tools()).tools
                assert len(tools) == 6
                result = await client.call_tool("zongheng_list_manufacturers", {})
                assert not result.is_error
                assert result.structured_content["data"]["items"][0]["name"] == "示例厂家"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()

