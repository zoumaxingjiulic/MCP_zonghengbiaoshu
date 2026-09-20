import json

import pytest

from zongheng_mcp.schemas import ListData, ManufacturerSummary, PageData
from zongheng_mcp.tools.qualifications import definitions, execute

EXPECTED_NAMES = [
    "zongheng_search_internal_certificates",
    "zongheng_search_external_certifications",
    "zongheng_list_expiring_certificates",
    "zongheng_list_manufacturers",
    "zongheng_get_qualification_overview",
    "zongheng_get_expiry_month_statistics",
]


class FakeService:
    def search_internal(self, query):
        return PageData(total=0, returned=0, page=query.page, page_size=query.page_size, items=[])

    def search_external(self, query):
        return PageData(total=0, returned=0, page=query.page, page_size=query.page_size, items=[])

    def list_expiring(self, query):
        return ListData(total=0, returned=0, items=[])

    def list_manufacturers(self, query):
        return ListData(
            total=1,
            returned=1,
            items=[ManufacturerSummary(name="示例厂家", qualification_count=2)],
        )

    def get_overview(self, query):
        raise AssertionError("not used in this test")

    def get_monthly_statistics(self, query):
        return ListData(total=0, returned=0, items=[])


def test_definitions_are_six_strict_read_only_tools():
    tools = definitions()
    assert [tool.name for tool in tools] == EXPECTED_NAMES
    assert all(tool.annotations.read_only_hint for tool in tools)
    assert all(tool.annotations.destructive_hint is False for tool in tools)
    assert all(tool.annotations.open_world_hint is False for tool in tools)
    assert all(tool.input_schema["additionalProperties"] is False for tool in tools)
    assert all(tool.output_schema for tool in tools)


@pytest.mark.asyncio
async def test_invalid_tool_arguments_return_stable_error_without_calling_service():
    result = await execute(
        FakeService(), "zongheng_search_internal_certificates", {"page_size": 101}
    )
    assert result.is_error
    assert result.structured_content["error"]["code"] == "INVALID_ARGUMENT"
    assert "page_size" not in result.content[0].text


@pytest.mark.asyncio
async def test_success_returns_matching_text_and_structured_content():
    result = await execute(FakeService(), "zongheng_list_manufacturers", {})
    assert not result.is_error
    assert json.loads(result.content[0].text) == result.structured_content
    assert result.structured_content["data"]["items"][0]["name"] == "示例厂家"


@pytest.mark.asyncio
async def test_unexpected_error_does_not_leak_details():
    result = await execute(FakeService(), "zongheng_get_qualification_overview", {})
    assert result.is_error
    assert result.structured_content["error"]["code"] == "INTERNAL_ERROR"
    assert "not used" not in result.content[0].text

