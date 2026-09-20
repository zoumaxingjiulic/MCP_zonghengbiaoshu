# 纵横标书资质查询 MCP 设计规格

日期：2026-09-20

## 1. 目标与边界

在 `D:\vscodework\MCP_zonghengbiaoshu` 建立独立、只读的 MCP 服务，供企业智能体平台查询纵横标书系统中的资质数据。服务直接连接远程 MySQL，仅访问：

- `custom_table_97`：本公司产品安标证书。
- `custom_table_103`：外购件产品资质。

所有查询强制过滤 `logic_del = 0`。数据库账号必须保持只读权限；当前账号已验证只有目标库的 `SELECT` 权限。

第一版不实现任意 SQL、Text-to-SQL、写操作、其他业务表查询，以及原资质系统的登录、聊天、通知、企业微信和前端功能。服务不调用大模型。

## 2. 技术方案

采用 Python 独立 MCP，主体参考 `MCP_U9` 的官方 Python SDK、Pydantic、ASGI/Uvicorn、Bearer Token 和协议测试，同时吸收 `MCP_OA` 的健康检查、请求限制和安全容器配置。不采用 Node.js 重写，也不通过原 FastAPI 转发。

```text
MCP Client
  -> Streamable HTTP / stdio
  -> MCP Tools
  -> QualificationService
  -> QualificationRepository
  -> SQLAlchemy connection pool
  -> read-only MySQL
```

目录：

```text
src/zongheng_mcp/
├── server.py
├── config.py
├── database.py
├── schemas.py
├── errors.py
├── repositories/qualifications.py
├── services/qualifications.py
└── tools/qualifications.py
tests/
docs/
pyproject.toml
uv.lock
Dockerfile
compose.yaml
.env.example
.gitignore
README.md
```

- 配置层校验数据库和传输配置，不打印秘密。
- Database 层管理连接池、超时、存活检查和关闭。
- Repository 层只含固定的参数化 SELECT。
- Service 层负责状态、分页、日期范围及数据归一化。
- Tool 层负责 MCP 定义、输入输出与异常边界。
- Server 负责工具注册、生命周期及两种传输。

## 3. 数据映射

本公司安标：`id`、`uid`、`column_427` 安标编号、`column_428` 产品名称、`column_429` 产品型号、`column_430` 开始日期、`column_431` 到期日期、`column_432` 产品类型、`column_433` 类别。

外购件资质：`id`、`uid`、`column_1022` 料号、`column_419` 产品名称、`column_420` 规格型号、`column_421` 厂家、`column_422` 类别、`column_424` 颁发日期、`column_425` 到期日期。

SQL 显式选择字段，不使用 `SELECT *`，不返回创建人、更新人等内部字段。

## 4. 统一业务规则

- 所有列表和统计强制 `logic_del = 0`，调用者不能关闭。
- `long_term`：到期日期为空。
- `expired`：到期日期早于数据库当前日期。
- `expiring`：剩余天数为 `0..warning_days`。
- `valid`：剩余天数大于 `warning_days`。
- `warning_days` 默认 90，范围 1–3650；返回 `days_remaining`，长期有效为 `null`。
- `page` 默认 1；`page_size` 默认 20、最大 100。
- 文本去除首尾空白；空字符串按未提供处理。
- 所有业务文本以绑定参数传入，不解释为 SQL 语法。
- 表名和字段名只能由代码内枚举选择。

## 5. MCP 工具

工具统一带 `zongheng_` 前缀，并标记只读、非破坏、幂等和封闭世界。

1. `zongheng_search_internal_certificates`
   - 输入：关键词、类别、到期状态、预警天数、页码和页大小。
   - 输出：安标编号、产品名称、型号、产品类型、类别、日期、状态和剩余天数。
2. `zongheng_search_external_certifications`
   - 输入：关键词、准确料号、厂家、类别、到期状态、预警天数和分页。
   - 输出：料号、产品、型号、厂家、类别、日期、状态和剩余天数。
3. `zongheng_list_expiring_certificates`
   - 输入：来源 `all|internal|external`、未来天数和上限。
   - 输出：按剩余天数升序的统一列表，明确数据来源。
4. `zongheng_list_manufacturers`
   - 输入：可选厂家关键词和上限。
   - 输出：厂家及未逻辑删除的资质记录数量。
5. `zongheng_get_qualification_overview`
   - 输入：预警天数。
   - 输出：两类资质的总量、有效、临期、过期、长期有效、类别分布、厂家数及合计。
6. `zongheng_get_expiry_month_statistics`
   - 输入：来源 `internal|external`、开始月、结束月；格式 `YYYY-MM`，最长 60 个月。
   - 输出：区间逐月数量，无数据月份补零。

## 6. 返回与错误

统一返回结构化内容和文本 JSON：

```json
{"trace_id":"uuid","success":true,"data":{},"error":null}
```

错误码：`INVALID_ARGUMENT`、`DATABASE_UNAVAILABLE`、`DATABASE_TIMEOUT`、`INTERNAL_ERROR`。最后协议边界捕获异常，不泄露 SQL、密码、驱动异常或内部配置。审计日志只记录工具名、追踪 ID、耗时、返回数量和错误码。

## 7. 传输、安全与配置

- 支持 stdio 和 Streamable HTTP。
- HTTP 路径 `/mcp`，存活检查 `/healthz`；健康检查不访问数据库。
- 容器内部端口 8000，Compose 默认映射宿主机 18002。
- 除 `/healthz` 外全部要求 32–512 位 Bearer Token。
- 启用 Host 白名单、DNS Rebinding 防护、Origin 白名单、请求体上限、最大会话数和会话空闲时间。
- 数据库配置包括主机、端口、用户、密码、库名、连接/读取超时和连接池大小。
- 密码使用 `SecretStr`；`.env` 不进入 Git，`.env.example` 仅放占位值。
- Docker 使用非 root 用户、只读文件系统、临时 `/tmp`、删除 capabilities、禁止提权和日志轮转。

## 8. 测试与验收

按 TDD 实现：每项生产行为先写失败测试并确认失败原因。

测试覆盖：

- 配置必填、秘密隐藏、Token、Host、端口和超时边界。
- 输入模型、额外字段、分页与日期范围。
- 到期状态边界和月份补零。
- 字段映射、正常结果、空结果、排序和数据库异常。
- 所有查询过滤 `logic_del=0`、只访问两张白名单表并使用参数绑定。
- stdio 初始化、工具发现和调用。
- HTTP 健康检查、认证、错误 Host、请求限制及六个工具调用。
- 真实只读数据库冒烟测试，不执行任何修改语句。

验收要求：

1. 容器健康，`/healthz` 不泄露配置。
2. 未认证 `/mcp` 返回 401，正确 Token 列出六个工具。
3. 六个工具返回符合输出模型的数据。
4. 所有数量以 `logic_del=0` 为口径。
5. 日志无密码、Token、原始 SQL 异常或完整业务结果。
6. `pytest`、Ruff、构建和 Docker 冒烟测试通过。

