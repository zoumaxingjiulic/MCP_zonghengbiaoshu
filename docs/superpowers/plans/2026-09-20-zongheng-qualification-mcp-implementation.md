# 纵横标书资质查询 MCP 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 构建一个独立、只读、可通过 stdio 和 Streamable HTTP 调用的纵横标书资质查询 MCP，提供六个固定业务工具。

**架构：** MCP Tool 层只处理协议与输入输出，QualificationService 执行业务规则，QualificationRepository 执行固定参数化 SQL，Database 管理 SQLAlchemy/PyMySQL 连接池。HTTP 端点使用 Bearer Token、Host/Origin 白名单及资源限制；所有查询只访问 `custom_table_97`、`custom_table_103` 并强制 `logic_del=0`。

**技术栈：** Python 3.12+、mcp 2.2.0、Pydantic 2.13.5、SQLAlchemy 2.0.30、PyMySQL 1.1.1、python-dotenv 1.2.3、Uvicorn 0.52.4、pytest 9.1.1、pytest-asyncio 1.4.0、Ruff 0.16.6、Docker Compose。

**规格：** `docs/superpowers/specs/2026-09-20-zongheng-qualification-mcp-design.md`

## 全局约束

- 第一版只提供六个已确认的资质查询工具，不调用大模型，不接受任意 SQL。
- 所有数据路径强制过滤 `logic_del=0`，调用者不能关闭。
- 数据库账号必须只有 `SELECT` 权限；真实密码和 MCP Token 不得进入 Git。
- SQL 显式选择业务字段，所有业务值使用绑定参数，表名和字段名只从代码枚举选择。
- HTTP MCP 路径为 `/mcp`，健康检查为 `/healthz`，Compose 默认宿主机端口为 18002。
- 分页 `page>=1`，`1<=page_size<=100`；预警天数为 1–3650；月份区间最长 60 个月。
- 所有生产行为遵循红—绿—重构；每个任务结束时运行针对性测试、完整测试与 Ruff，再提交。

## 文件结构与职责

- `pyproject.toml`：固定运行时/开发依赖、入口命令及 pytest/Ruff 配置。
- `src/zongheng_mcp/config.py`：数据库和 HTTP 配置校验。
- `src/zongheng_mcp/database.py`：同步 SQLAlchemy 连接池和只读查询接口。
- `src/zongheng_mcp/schemas.py`：工具输入、领域结果和统一错误模型。
- `src/zongheng_mcp/errors.py`：稳定业务错误类型。
- `src/zongheng_mcp/repositories/qualifications.py`：固定参数化 SQL。
- `src/zongheng_mcp/services/qualifications.py`：状态、分页、月份补零和聚合业务逻辑。
- `src/zongheng_mcp/tools/qualifications.py`：六个 MCP Tool 定义与执行边界。
- `src/zongheng_mcp/http.py`：Bearer Token 中间件和健康检查。
- `src/zongheng_mcp/server.py`：SDK Server、生命周期、stdio/HTTP 入口。
- `tests/`：按模块对应的单元、协议、HTTP 和真实数据库可选冒烟测试。
- `Dockerfile`、`compose.yaml`：非 root、只读容器部署。
- `.env.example`、`README.md`：无秘密配置模板和使用说明。

---

### 任务 1：项目骨架与安全配置

**文件：**
- 创建：`pyproject.toml`
- 创建：`.gitignore`
- 创建：`.env.example`
- 创建：`src/zongheng_mcp/__init__.py`
- 创建：`src/zongheng_mcp/config.py`
- 创建：`tests/test_config.py`

- [ ] **步骤 1：编写配置失败测试**

```python
def test_database_password_is_required_and_hidden():
    with pytest.raises(ValidationError) as exc:
        DbSettings.model_validate({"host": "db", "port": 3306, "user": "reader", "password": "", "name": "biz"})
    assert "secret-value" not in str(exc.value)

def test_http_token_and_hosts_are_restricted():
    settings = HttpSettings.model_validate({"access_token": "x" * 32, "allowed_hosts": ["127.0.0.1:*"]})
    assert settings.max_request_body_size == 1_048_576
    with pytest.raises(ValidationError):
        HttpSettings.model_validate({"access_token": "short", "allowed_hosts": []})
```

- [ ] **步骤 2：运行测试并确认因模块不存在而失败**

运行：`uv run pytest tests/test_config.py -v`

预期：FAIL，包含 `ModuleNotFoundError: No module named 'zongheng_mcp'`。

- [ ] **步骤 3：创建最小项目配置与 Pydantic 配置模型**

在 `pyproject.toml` 固定头部所列依赖，定义命令：

```toml
[project.scripts]
zongheng-mcp = "zongheng_mcp.server:main"
```

`config.py` 提供：

```python
class DbSettings(BaseModel):
    host: str
    port: int = Field(ge=1, le=65535)
    user: str
    password: SecretStr
    name: str
    connect_timeout: int = Field(default=10, ge=1, le=60)
    read_timeout: int = Field(default=30, ge=1, le=300)
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=10, ge=0, le=100)

class HttpSettings(BaseModel):
    access_token: SecretStr
    allowed_hosts: list[str]
    allowed_origins: list[str] = Field(default_factory=list)
    max_request_body_size: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    max_sessions: int = Field(default=64, ge=1, le=1_024)
    session_idle_timeout: float = Field(default=300, ge=10, le=3_600)
```

实现 `load_db_settings(env_file=None)` 和 `load_http_settings(env_file=None)`，环境变量使用 `ZONGHENG_DB_*`、`MCP_*`。所有模型设置 `extra="forbid"`、`frozen=True`、`hide_input_in_errors=True`。

- [ ] **步骤 4：运行配置测试与 Ruff**

运行：`uv lock && uv sync --dev && uv run pytest tests/test_config.py -v && uv run ruff check .`

预期：全部 PASS，Ruff 无错误。

- [ ] **步骤 5：提交**

```bash
git add pyproject.toml uv.lock .gitignore .env.example src/zongheng_mcp tests/test_config.py
git commit -m "feat: scaffold secure MCP configuration"
```

### 任务 2：领域模型和到期状态规则

**文件：**
- 创建：`src/zongheng_mcp/schemas.py`
- 创建：`src/zongheng_mcp/errors.py`
- 创建：`src/zongheng_mcp/services/__init__.py`
- 创建：`src/zongheng_mcp/services/qualifications.py`
- 创建：`tests/test_schemas.py`
- 创建：`tests/test_qualification_service.py`

- [ ] **步骤 1：编写输入边界和状态失败测试**

```python
def test_search_input_rejects_extra_fields_and_large_page():
    with pytest.raises(ValidationError):
        InternalSearch.model_validate({"page": 0, "unknown": "x"})
    with pytest.raises(ValidationError):
        InternalSearch(page_size=101)

@pytest.mark.parametrize(("expiry", "expected"), [
    (None, "long_term"),
    (date(2026, 9, 19), "expired"),
    (date(2026, 9, 20), "expiring"),
    (date(2026, 12, 19), "expiring"),
    (date(2026, 12, 20), "valid"),
])
def test_classify_expiry_boundaries(expiry, expected):
    assert classify_expiry(expiry, today=date(2026, 9, 20), warning_days=90).status == expected
```

- [ ] **步骤 2：运行测试并确认缺少模型和函数**

运行：`uv run pytest tests/test_schemas.py tests/test_qualification_service.py -v`

预期：FAIL，导入 `InternalSearch` 或 `classify_expiry` 失败。

- [ ] **步骤 3：实现严格输入和统一输出模型**

定义 `ExpiryStatus`、`Source`、`InternalSearch`、`ExternalSearch`、`ExpiringQuery`、`ManufacturerQuery`、`OverviewQuery`、`MonthlyStatsQuery`、`ErrorInfo`、`ToolResult`。文本字段通过验证器 `.strip()`，空字符串转 `None`；月份使用正则并在模型级验证结束月及 60 个月上限。

实现：

```python
@dataclass(frozen=True)
class ExpiryInfo:
    status: ExpiryStatus
    days_remaining: int | None

def classify_expiry(expiry: date | None, *, today: date, warning_days: int) -> ExpiryInfo:
    if expiry is None:
        return ExpiryInfo(ExpiryStatus.LONG_TERM, None)
    days = (expiry - today).days
    if days < 0:
        return ExpiryInfo(ExpiryStatus.EXPIRED, days)
    if days <= warning_days:
        return ExpiryInfo(ExpiryStatus.EXPIRING, days)
    return ExpiryInfo(ExpiryStatus.VALID, days)
```

- [ ] **步骤 4：验证测试与静态检查**

运行：`uv run pytest tests/test_schemas.py tests/test_qualification_service.py -v && uv run ruff check .`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add src/zongheng_mcp/schemas.py src/zongheng_mcp/errors.py src/zongheng_mcp/services tests/test_schemas.py tests/test_qualification_service.py
git commit -m "feat: define qualification query contracts"
```

### 任务 3：只读数据库与固定查询仓库

**文件：**
- 创建：`src/zongheng_mcp/database.py`
- 创建：`src/zongheng_mcp/repositories/__init__.py`
- 创建：`src/zongheng_mcp/repositories/qualifications.py`
- 创建：`tests/test_database.py`
- 创建：`tests/test_qualification_repository.py`

- [ ] **步骤 1：编写连接配置与 SQL 安全失败测试**

```python
def test_database_url_escapes_password():
    url = build_database_url(db_settings(password="p@ss:%"))
    assert url.password == "p@ss:%"
    assert "p%40ss%3A%25" in url.render_as_string(hide_password=False)

def test_internal_search_is_bound_and_filters_deleted(recording_db):
    repo = QualificationRepository(recording_db)
    repo.search_internal(InternalSearch(keyword="%煤机_", page=1, page_size=20))
    sql, params = recording_db.calls[-1]
    assert "custom_table_97" in sql
    assert "logic_del = 0" in sql
    assert "%煤机_" not in sql
    assert params["keyword"] == "%\\%煤机\\_%"
```

同时为外购件查询、厂家、临期、概览和月份统计断言：只出现白名单表；无 `SELECT *`；业务输入不进入 SQL 文本。

- [ ] **步骤 2：运行测试并确认 Repository 缺失**

运行：`uv run pytest tests/test_database.py tests/test_qualification_repository.py -v`

预期：FAIL，导入 `Database` 或 `QualificationRepository` 失败。

- [ ] **步骤 3：实现 Database 和 Repository**

`Database` 使用 `URL.create()` 构造安全 URL，创建 SQLAlchemy Engine：

```python
create_engine(
    url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
    connect_args={
        "connect_timeout": settings.connect_timeout,
        "read_timeout": settings.read_timeout,
        "write_timeout": settings.read_timeout,
        "charset": "utf8mb4",
    },
)
```

Repository 暴露 `search_internal`、`search_external`、`list_expiring`、`list_manufacturers`、`get_overview_counts`、`get_monthly_counts`。LIKE 值使用 `escape_like()` 转义 `\\`、`%`、`_` 并配合 `ESCAPE '\\\\'`；到期状态只从预定义 SQL 片段字典选择。

- [ ] **步骤 4：运行 Repository 测试和完整测试**

运行：`uv run pytest tests/test_database.py tests/test_qualification_repository.py -v && uv run pytest -q && uv run ruff check .`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add src/zongheng_mcp/database.py src/zongheng_mcp/repositories tests/test_database.py tests/test_qualification_repository.py
git commit -m "feat: add read-only qualification repository"
```

### 任务 4：六项业务服务能力

**文件：**
- 修改：`src/zongheng_mcp/services/qualifications.py`
- 修改：`tests/test_qualification_service.py`

- [ ] **步骤 1：编写服务行为失败测试**

使用 `FakeQualificationRepository` 返回固定行，分别验证：

```python
def test_search_external_normalizes_dates_and_expiry(fake_repo):
    service = QualificationService(fake_repo, today=lambda: date(2026, 9, 20))
    result = service.search_external(ExternalSearch(page=1, page_size=20))
    assert result.items[0].manufacturer == "示例厂家"
    assert result.items[0].expiry_status == "expiring"
    assert result.items[0].days_remaining == 10

def test_monthly_statistics_fills_missing_months(fake_repo):
    result = QualificationService(fake_repo).get_monthly_statistics(
        MonthlyStatsQuery(source="internal", start_month="2026-01", end_month="2026-03")
    )
    assert [(row.month, row.count) for row in result.items] == [
        ("2026-01", 2), ("2026-02", 0), ("2026-03", 1)
    ]
```

另测本公司搜索、临期合并排序、厂家去空白、概览状态合计和 Repository 异常映射。

- [ ] **步骤 2：运行测试并确认服务方法缺失**

运行：`uv run pytest tests/test_qualification_service.py -v`

预期：FAIL，缺少相应服务方法或返回模型。

- [ ] **步骤 3：实现最少服务逻辑**

实现六个同名服务方法；通过构造函数注入 Repository 和 `today: Callable[[], date]`。Repository 的连接/超时异常映射成 `BusinessError("DATABASE_UNAVAILABLE"|"DATABASE_TIMEOUT", retryable=True)`，其余异常不在 Service 吞掉。

- [ ] **步骤 4：运行服务测试和完整测试**

运行：`uv run pytest tests/test_qualification_service.py -v && uv run pytest -q && uv run ruff check .`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add src/zongheng_mcp/services/qualifications.py tests/test_qualification_service.py
git commit -m "feat: implement qualification business services"
```

### 任务 5：MCP 工具定义、调度与 stdio 协议

**文件：**
- 创建：`src/zongheng_mcp/tools/__init__.py`
- 创建：`src/zongheng_mcp/tools/qualifications.py`
- 创建：`src/zongheng_mcp/server.py`
- 创建：`tests/test_tools.py`
- 创建：`tests/test_mcp_stdio.py`

- [ ] **步骤 1：编写六工具发现和错误边界失败测试**

```python
def test_definitions_are_six_read_only_tools():
    tools = definitions()
    assert [tool.name for tool in tools] == [
        "zongheng_search_internal_certificates",
        "zongheng_search_external_certifications",
        "zongheng_list_expiring_certificates",
        "zongheng_list_manufacturers",
        "zongheng_get_qualification_overview",
        "zongheng_get_expiry_month_statistics",
    ]
    assert all(tool.annotations.read_only_hint for tool in tools)

@pytest.mark.asyncio
async def test_invalid_tool_arguments_return_stable_error(fake_service):
    result = await execute(fake_service, "zongheng_search_internal_certificates", {"page_size": 101})
    assert result.is_error
    assert result.structured_content["error"]["code"] == "INVALID_ARGUMENT"
```

stdio 测试用官方 SDK Client 启动真实子进程，断言初始化、`tools/list` 和一次工具调用成功。

- [ ] **步骤 2：运行测试并确认 MCP 定义缺失**

运行：`uv run pytest tests/test_tools.py tests/test_mcp_stdio.py -v`

预期：FAIL，导入工具定义或入口失败。

- [ ] **步骤 3：实现工具边界与 SDK Server**

每个工具使用对应 Pydantic Schema 的 JSON Schema；`execute()` 生成 UUID trace ID，通过 `asyncio.to_thread()` 调用同步服务并用超时包裹。成功返回 `structured_content`；验证错误、业务错误和最后未分类错误分别映射稳定错误码。`create_server(settings, service_factory=None)` 的 lifespan 默认初始化 Database/Repository/Service，并在关闭时 dispose Engine；测试通过 `service_factory` 注入 Fake Service，不连接真实数据库。

- [ ] **步骤 4：运行协议测试和完整检查**

运行：`uv run pytest tests/test_tools.py tests/test_mcp_stdio.py -v && uv run pytest -q && uv run ruff check .`

预期：全部 PASS；stderr 无秘密和 traceback 泄漏。

- [ ] **步骤 5：提交**

```bash
git add src/zongheng_mcp/tools src/zongheng_mcp/server.py tests/test_tools.py tests/test_mcp_stdio.py
git commit -m "feat: expose six qualification MCP tools"
```

### 任务 6：Streamable HTTP、安全中间件和容器部署

**文件：**
- 创建：`src/zongheng_mcp/http.py`
- 修改：`src/zongheng_mcp/server.py`
- 创建：`tests/test_mcp_http.py`
- 创建：`Dockerfile`
- 创建：`.dockerignore`
- 创建：`compose.yaml`

- [ ] **步骤 1：编写 HTTP 鉴权和协议失败测试**

启动真实临时端口 MCP 子进程，测试：

```python
assert request_status(base_url + "/healthz") == 200
assert request_status(base_url + "/mcp") == 401
assert request_status(base_url + "/mcp", token="wrong-" + "x" * 32) == 401
assert request_status(base_url + "/mcp", token=token, host="evil.example") == 421
```

再调用 `create_http_app(..., service_factory=fake_service_factory)` 启动临时 Uvicorn，使用官方 SDK Streamable HTTP Client 携带正确 Token，断言六工具发现和一个 Fake Service 工具调用成功。

- [ ] **步骤 2：运行 HTTP 测试并确认入口缺失**

运行：`uv run pytest tests/test_mcp_http.py -v`

预期：FAIL，HTTP 应用或命令行参数不存在。

- [ ] **步骤 3：实现 Bearer 中间件和 HTTP 入口**

使用 `secrets.compare_digest` 校验 Token；`/healthz` 绕过认证且只返回 `{"status":"ok"}`。SDK Transport 启用 DNS Rebinding 防护、Allowed Hosts/Origins、请求体上限、最大会话和空闲超时。CLI 参数为：

```text
--env-file PATH
--transport stdio|streamable-http
--host 127.0.0.1
--port 8000
```

- [ ] **步骤 4：创建安全镜像和 Compose**

Dockerfile 采用多阶段 `uv` 构建，运行时使用固定非 root UID/GID 10001。Compose 端口 `${MCP_BIND_IP:-127.0.0.1}:${MCP_PORT:-18002}:8000`，配置 `read_only`、`tmpfs /tmp`、`cap_drop: ALL`、`no-new-privileges`、健康检查和日志轮转。

- [ ] **步骤 5：验证 HTTP、完整测试和 Compose 配置**

运行：

```bash
uv run pytest tests/test_mcp_http.py -v
uv run pytest -q
uv run ruff check .
docker compose --env-file .env.example config
docker build -t zongheng-qualification-mcp:test .
```

预期：测试与 Ruff 全部 PASS；Compose 配置可解析；镜像构建成功。

- [ ] **步骤 6：提交**

```bash
git add src/zongheng_mcp/http.py src/zongheng_mcp/server.py tests/test_mcp_http.py Dockerfile .dockerignore compose.yaml
git commit -m "feat: secure Streamable HTTP deployment"
```

### 任务 7：真实只读冒烟测试、文档和最终验收

**文件：**
- 创建：`tests/test_live_database.py`
- 创建：`scripts/smoke.py`
- 创建：`README.md`
- 修改：`.env.example`

- [ ] **步骤 1：编写显式启用的真实数据库冒烟测试**

```python
@pytest.mark.skipif(os.getenv("RUN_LIVE_DB_TESTS") != "1", reason="live DB test is opt-in")
def test_live_queries_use_active_record_totals(live_repository, live_database):
    result = live_repository.search_internal(InternalSearch(page=1, page_size=5))
    active_total = live_database.scalar(
        text("SELECT COUNT(*) FROM custom_table_97 WHERE logic_del = 0"), {}
    )
    assert result.total == active_total
    assert result.total >= len(result.rows)
```

同样核对 `custom_table_103`。Repository 正常输出不暴露 `logic_del`；独立审计查询只比较有效记录总数，不输出业务内容。

- [ ] **步骤 2：运行测试并确认测试夹具尚未实现**

运行：`RUN_LIVE_DB_TESTS=1 uv run pytest tests/test_live_database.py -v`

预期：FAIL，缺少 live 配置/夹具或六项冒烟函数。

- [ ] **步骤 3：实现冒烟脚本和使用文档**

`scripts/smoke.py` 使用官方 MCP Client 依次执行工具发现、概览、两类搜索、临期、厂家和月份统计，只打印工具名、成功状态、数量和 trace ID，不打印完整记录。

README 明确：安装、环境变量、生成 Token、stdio 配置、Streamable HTTP 配置、Docker 启停、健康检查、客户端接入示例、六工具说明、只读边界、测试命令和故障排查。

- [ ] **步骤 4：创建本地私密 `.env` 并执行真实只读测试**

从用户提供的配置生成未跟踪 `.env`；用 `git check-ignore .env` 确认忽略。执行：

```bash
$env:RUN_LIVE_DB_TESTS="1"
uv run pytest tests/test_live_database.py -v
Remove-Item Env:RUN_LIVE_DB_TESTS
```

预期：六项真实只读查询通过，不产生写操作。

- [ ] **步骤 5：执行最终本地和 Docker 验收**

运行：

```bash
uv run pytest -q
uv run ruff check .
uv build
docker compose up -d --build
docker compose ps
uv run python scripts/smoke.py
docker compose logs --no-color --tail=200
```

预期：所有测试通过、Ruff 无错误、包构建成功、容器 healthy、六工具冒烟成功，日志不含数据库密码、MCP Token、完整业务记录或原始 SQL 异常。

- [ ] **步骤 6：核对需求和 Git 状态**

运行：

```bash
git diff --check
git status --short
git check-ignore .env
```

逐项核对规格第 1–8 节与本计划验收项，不提交 `.env`、测试缓存或构建产物。

- [ ] **步骤 7：提交最终文档和冒烟测试**

```bash
git add README.md .env.example tests/test_live_database.py scripts/smoke.py
git commit -m "docs: add deployment and live verification guide"
```
