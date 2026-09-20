"""Run a privacy-safe smoke test against a deployed Streamable HTTP MCP server."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


def summarize_result(name: str, result: Any) -> dict[str, Any]:
    """Return operational metadata without logging business records."""
    payload = result.structured_content or {}
    data = payload.get("data") or {}
    count = data.get("returned")
    if count is None:
        count = data.get("total")
    if count is None and name == "zongheng_get_qualification_overview":
        count = sum(
            int((data.get(section) or {}).get("total", 0))
            for section in ("internal", "external")
        )
    error = payload.get("error") or {}
    return {
        "tool": name,
        "success": not bool(result.is_error),
        "count": count,
        "trace_id": payload.get("trace_id"),
        "error_code": error.get("code"),
    }


def smoke_calls() -> list[tuple[str, dict[str, Any]]]:
    year = datetime.now(UTC).year
    return [
        ("zongheng_search_internal_certificates", {"page_size": 1}),
        ("zongheng_search_external_certifications", {"page_size": 1}),
        ("zongheng_list_expiring_certificates", {"days": 90, "limit": 1}),
        ("zongheng_list_manufacturers", {"limit": 1}),
        ("zongheng_get_qualification_overview", {}),
        (
            "zongheng_get_expiry_month_statistics",
            {"year": year, "source": "internal"},
        ),
    ]


async def run() -> int:
    url = os.environ.get("SMOKE_MCP_URL", "http://127.0.0.1:18002/mcp")
    token = os.environ.get("SMOKE_MCP_ACCESS_TOKEN")
    if not token:
        raise SystemExit("SMOKE_MCP_ACCESS_TOKEN is required")

    failed = False
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        trust_env=False,
        timeout=30,
    ) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport, read_timeout_seconds=30) as client:
            available = {tool.name for tool in (await client.list_tools()).tools}
            for name, arguments in smoke_calls():
                if name not in available:
                    summary = {
                        "tool": name,
                        "success": False,
                        "count": None,
                        "trace_id": None,
                        "error_code": "TOOL_NOT_FOUND",
                    }
                else:
                    summary = summarize_result(name, await client.call_tool(name, arguments))
                failed = failed or not summary["success"]
                print(json.dumps(summary, ensure_ascii=False), flush=True)
    return int(failed)


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
