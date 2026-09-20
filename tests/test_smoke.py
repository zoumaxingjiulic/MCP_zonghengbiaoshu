from types import SimpleNamespace

from zongheng_mcp.smoke import summarize_result


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
