import asyncio
import logging
import time
from dataclasses import dataclass
from uuid import uuid4

from mcp import types
from pydantic import BaseModel, ValidationError

from ..errors import BusinessError
from ..schemas import (
    ErrorInfo,
    ExpiringCertificate,
    ExpiringQuery,
    ExternalCertification,
    ExternalSearch,
    InternalCertificate,
    InternalSearch,
    ListData,
    ManufacturerQuery,
    ManufacturerSummary,
    MonthCount,
    MonthlyStatsQuery,
    OverviewQuery,
    PageData,
    QualificationOverview,
    ToolResult,
)

LOG = logging.getLogger("zongheng_mcp.audit")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    service_method: str


SPECS = (
    ToolSpec(
        "zongheng_search_internal_certificates",
        "查询本公司安标证书",
        "按产品名称、安标编号、类别或到期状态查询本公司有效安标证书。"
        "仅返回未逻辑删除记录并分页；不查询外购件资质，不修改数据。",
        InternalSearch,
        ToolResult[PageData[InternalCertificate]],
        "search_internal",
    ),
    ToolSpec(
        "zongheng_search_external_certifications",
        "查询外购件产品资质",
        "按料号、产品、厂家、认证类别或到期状态查询外购件有效资质。"
        "仅返回未逻辑删除记录并分页；不查询本公司安标，不修改数据。",
        ExternalSearch,
        ToolResult[PageData[ExternalCertification]],
        "search_external",
    ),
    ToolSpec(
        "zongheng_list_expiring_certificates",
        "查询即将到期资质",
        "列出未来指定天数内到期的本公司安标和/或外购件资质，按剩余天数升序。"
        "不包含已过期、长期有效或逻辑删除记录。",
        ExpiringQuery,
        ToolResult[ListData[ExpiringCertificate]],
        "list_expiring",
    ),
    ToolSpec(
        "zongheng_list_manufacturers",
        "查询资质厂家",
        "查询外购件资质中的厂家及其未逻辑删除资质记录数量，可按厂家名称模糊搜索。",
        ManufacturerQuery,
        ToolResult[ListData[ManufacturerSummary]],
        "list_manufacturers",
    ),
    ToolSpec(
        "zongheng_get_qualification_overview",
        "获取资质统计概览",
        "统计本公司安标与外购件资质的有效、临期、过期、长期有效数量、类别分布和厂家数。"
        "统计口径仅包含未逻辑删除记录。",
        OverviewQuery,
        ToolResult[QualificationOverview],
        "get_overview",
    ),
    ToolSpec(
        "zongheng_get_expiry_month_statistics",
        "获取资质到期月份统计",
        "按指定月份区间统计本公司或外购件资质到期数量；无数据月份补零。"
        "区间最长 60 个月，仅统计未逻辑删除记录。",
        MonthlyStatsQuery,
        ToolResult[ListData[MonthCount]],
        "get_monthly_statistics",
    ),
)

SPEC_BY_NAME = {spec.name: spec for spec in SPECS}


def definitions() -> list[types.Tool]:
    annotations = types.ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
    return [
        types.Tool(
            name=spec.name,
            title=spec.title,
            description=spec.description,
            input_schema=spec.input_model.model_json_schema(),
            output_schema=spec.output_model.model_json_schema(),
            annotations=annotations,
        )
        for spec in SPECS
    ]


async def execute(service, name: str, arguments: dict) -> types.CallToolResult:
    trace_id = str(uuid4())
    started = time.monotonic()
    spec = SPEC_BY_NAME.get(name)
    if spec is None:
        raise ValueError("Unknown tool")
    try:
        query = spec.input_model.model_validate(arguments)
        async with asyncio.timeout(65):
            data = await asyncio.to_thread(getattr(service, spec.service_method), query)
        output = ToolResult(trace_id=trace_id, success=True, data=data)
    except ValidationError:
        output = ToolResult(
            trace_id=trace_id,
            success=False,
            error=ErrorInfo(
                code="INVALID_ARGUMENT",
                message="工具参数不符合约束，请检查查询条件、分页、枚举或日期范围。",
                retryable=False,
            ),
        )
    except BusinessError as exc:
        output = ToolResult(
            trace_id=trace_id,
            success=False,
            error=ErrorInfo(code=exc.code, message=exc.message, retryable=exc.retryable),
        )
    except TimeoutError:
        output = ToolResult(
            trace_id=trace_id,
            success=False,
            error=ErrorInfo(
                code="DATABASE_TIMEOUT",
                message="数据库查询超时，请稍后重试。",
                retryable=True,
            ),
        )
    except Exception:  # noqa: BLE001 - protocol boundary must not leak database or service errors
        output = ToolResult(
            trace_id=trace_id,
            success=False,
            error=ErrorInfo(
                code="INTERNAL_ERROR",
                message="内部处理失败，请提供追踪 ID 联系维护人员。",
                retryable=False,
            ),
        )
    payload = output.model_dump(mode="json")
    LOG.info(
        "tool=%s trace_id=%s duration_ms=%d status=%s",
        name,
        trace_id,
        (time.monotonic() - started) * 1000,
        "OK" if output.success else output.error.code,
    )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=output.model_dump_json())],
        structured_content=payload,
        is_error=not output.success,
    )
