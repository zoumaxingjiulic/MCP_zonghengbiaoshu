from types import SimpleNamespace

import pytest

from zongheng_mcp.smoke import smoke_calls, summarize_result
from zongheng_mcp.tools.qualifications import SPEC_BY_NAME


@pytest.mark.parametrize("name,arguments", smoke_calls())
def test_smoke_call_arguments_match_tool_contract(name, arguments):
    SPEC_BY_NAME[name].input_model.model_validate(arguments)


def test_smoke_summary_never_contains_business_items():
    result = SimpleNamespace(
        is_error=False,
        structured_content={
            "trace_id": "trace-1",
            "success": True,
            "data": {"total": 1, "returned": 1, "items": [{"name": "敏感厂家"}]},
            "error": None,
        },
    )
    summary = summarize_result("zongheng_list_manufacturers", result)
    assert summary == {
        "tool": "zongheng_list_manufacturers",
        "success": True,
        "count": 1,
        "trace_id": "trace-1",
        "error_code": None,
    }
    assert "敏感厂家" not in str(summary)
