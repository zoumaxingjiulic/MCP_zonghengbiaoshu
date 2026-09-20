# 纵横标书资质查询 MCP

面向企业智能体平台的只读 MCP 服务。它直接连接纵横标书业务库，将两张资质表封装成 6 个边界清晰、参数受控的业务工具，不向大模型开放任意 SQL。

## 架构与数据范围

```text
企业智能体 / MCP Client
          │  Streamable HTTP + Bearer Token
          ▼
纵横资质 MCP（参数校验、业务口径、错误隔离、审计日志）
          │  SQLAlchemy + PyMySQL + 参数化固定 SQL
          ▼
MySQL 只读账号
  ├─ custom_table_97   本公司产品安标证书
  └─ custom_table_103  外购件产品资质
```

所有查询强制排除 `logic_del != 0` 的记录。数据库账号只需要 `SELECT` 权限；服务本身没有新增、修改或删除工具。

## MCP 工具

| 工具 | 用途 |
| --- | --- |
| `zongheng_search_internal_certificates` | 分页查询本公司安标证书 |
| `zongheng_search_external_certifications` | 分页查询外购件资质 |
| `zongheng_list_expiring_certificates` | 查询未来指定天数内到期的资质 |
| `zongheng_list_manufacturers` | 查询厂家及其资质数量 |
| `zongheng_get_qualification_overview` | 获取有效、临期、过期、长期有效等统计概览 |
| `zongheng_get_expiry_month_statistics` | 按月份统计资质到期数量 |

每个工具都声明为只读、幂等、非破坏性工具。响应统一包含 `success`、`trace_id`、`data` 或安全错误信息；数据库异常不会直接暴露给调用方。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（本地运行与开发）
- Docker Engine + Docker Compose v2（容器部署）
- 可访问目标 MySQL 的网络

## 配置

复制示例配置并填写实际值：

```bash
cp .env.example .env
chmod 600 .env
```

关键配置：

- `ZONGHENG_DB_*`：只读数据库连接信息。
- `ZONGHENG_DB_PASSWORD`：填写数据库的原始密码。例如密码里真实字符是 `@`，这里必须写 `@`，不要写成 `%40`。
- `MCP_ACCESS_TOKEN`：MCP HTTP 接口使用的 Bearer Token，建议用下列命令生成：

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

- `MCP_ALLOWED_HOSTS`：允许访问的 Host，多个值用英文逗号分隔。
- `MCP_ALLOWED_ORIGINS`：需要浏览器跨域调用时填写允许的 Origin；服务端调用可留空。
- `MCP_BIND_IP`：默认 `127.0.0.1`，仅本机可访问。确需局域网直连时改为服务器内网 IP，并同步收紧防火墙和 `MCP_ALLOWED_HOSTS`。

`.env` 已被 Git 忽略，不要提交任何真实密码或 Token。

## 本地运行

安装依赖：

```bash
uv sync --dev
```

以 stdio 模式启动：

```bash
uv run zongheng-mcp --env-file .env --transport stdio
```

以 Streamable HTTP 模式启动：

```bash
uv run zongheng-mcp --env-file .env --transport streamable-http --host 127.0.0.1 --port 18002
```

服务地址为 `http://127.0.0.1:18002/mcp`，存活检查为：

```bash
curl http://127.0.0.1:18002/healthz
```

## Docker Compose 部署

```bash
docker compose --env-file .env up -d --build --wait --wait-timeout 120
docker compose --env-file .env ps
curl http://127.0.0.1:18002/healthz
```

查看日志：

```bash
docker compose --env-file .env logs -f --tail=200 zongheng-mcp
```

更新代码后的重建：

```bash
docker compose --env-file .env up -d --build --force-recreate --wait --wait-timeout 120
```

容器采用只读根文件系统、丢弃 Linux capabilities、禁止权限提升，并限制日志文件大小。生产环境仍应通过防火墙或反向代理限制访问来源；跨网络访问建议在反向代理处配置 HTTPS。

## 接入企业智能体平台

在平台的 MCP 连接配置中填写：

- 传输方式：`Streamable HTTP`
- 服务地址：`http://<服务器地址>:18002/mcp`
- 鉴权：`Authorization: Bearer <MCP_ACCESS_TOKEN>`

智能体只应绑定它需要使用的工具。工具描述和 JSON Schema 会告诉模型何时调用及参数范围，但部门权限、可见范围等平台级权限仍应由企业智能体平台控制。

## 验证

单元与协议测试：

```bash
uv run pytest -q
uv run ruff check .
```

真实数据库只读测试默认跳过。仅在明确需要时，在当前终端临时设置数据库环境变量并执行：

```bash
RUN_LIVE_DB_TESTS=1 uv run pytest tests/test_live_database.py -v
```

已部署服务的全工具冒烟测试：

```bash
export SMOKE_MCP_URL=http://127.0.0.1:18002/mcp
export SMOKE_MCP_ACCESS_TOKEN='<MCP_ACCESS_TOKEN>'
uv run zongheng-mcp-smoke
```

冒烟脚本依次发现并调用全部 6 个工具，只输出成功状态、数量、追踪 ID 和错误码，不打印业务记录。

构建发布包：

```bash
uv build
```

## 安全约束

- 不提供任意 SQL、表名、字段名或排序表达式输入。
- 所有查询均为预定义参数化 SQL，并对分页、日期范围、枚举和返回条数设限。
- 查询层只允许白名单表，并统一过滤逻辑删除记录。
- HTTP 使用 Bearer Token、Host/Origin 校验、请求体限制、会话数限制与闲置超时。
- 审计日志只记录工具名、追踪 ID、耗时和结果状态，不记录数据库密码和业务明细。
- 数据库账号应由 DBA 保持最小权限，并定期轮换密码。

## 目录结构

```text
src/zongheng_mcp/
├─ config.py        配置校验
├─ database.py      数据库连接池
├─ repositories/    固定只读 SQL
├─ services/        业务口径与状态归一化
├─ tools/           MCP 工具定义与安全错误边界
├─ http.py          HTTP 鉴权与健康检查
├─ server.py        stdio / Streamable HTTP 服务入口
└─ smoke.py         部署后冒烟验证
tests/              单元、协议和可选真实数据库测试
```

设计说明与逐任务实施记录位于 `docs/superpowers/`。
