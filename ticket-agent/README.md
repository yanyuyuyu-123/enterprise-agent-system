# 企业智能工单 Agent 系统

V1：工单状态机、权限与数据范围、通知与日志、Agent 对话、统计与定时任务。
V2：采购/销售/库存/盘点/财务、pgvector 知识库与 RAG、Supervisor 路由与只读分析 Agent。

## 环境

| 组件 | 说明 |
| --- | --- |
| API | FastAPI，默认 `http://127.0.0.1:8000`，文档 `/docs` |
| PostgreSQL | 16 + pgvector，宿主端口 `15432`，库/用户/口令均为 `ticket` |
| Redis | 宿主端口 `16379`，用于 Celery 与令牌黑名单 |
| Python | 3.11，使用仓库内 `.venv` |

## 启动

```powershell
docker compose up -d
uv sync --extra dev
$env:PYTHONUTF8="1"
.venv\Scripts\python.exe -m alembic upgrade head

# 终端 1：API
.venv\Scripts\python.exe -m uvicorn app.main:app --reload

# 终端 2：Celery（document 队列负责知识库解析）
.venv\Scripts\python.exe -m celery -A app.tasks.celery_app.celery_app worker -l info -Q default,document

# 终端 3：定时任务（超时扫描、清理）
.venv\Scripts\python.exe -m app.tasks.scheduler
```

首次启动前复制 `.env.example` 为 `.env`，至少填写：

- `DEEPSEEK_API_KEY`：V1 对话
- `EMBEDDING_API_KEY`：V2 知识库向量化；`EMBEDDING_DIM` 必须与 `knowledge_chunks.embedding` 的 1024 维一致
- `LOG_ENC_KEY`、`BOOTSTRAP_ADMIN_PASSWORD`：日志加密与首个管理员

## 测试

```powershell
$env:PYTHONUTF8="1"
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m pytest -q
```

测试使用独立账号（密码 `Dev@123456`，仅测试环境）：

| 账号 | 岗位 | 账号 | 岗位 |
| --- | --- | --- | --- |
| `V2P01` | 采购员 | `V2C01` | 制单员 |
| `V2S01` | 业务员 | `V2T01` | 理货员 |
| `V2B01` | 业务负责人 | `V2W01` | 仓库负责人 |
| `V2M01` | 业务经理 | `V2A01` | 会计 |
| `V2CA1` | 出纳 | `V2F01` | 财务负责人 |
| `V2K01` | 生产工人 | | |

## V2 接口

- 主数据：`/api/v1/suppliers`、`/customers`、`/products`、`/warehouses`、`/inventory`
- 采购/销售：`/api/v1/purchase-orders`、`/sales-orders`（提交、审核、作废）
- 库存：`/api/v1/stock-movements`（提交、执行、审核）、`/stock-checks`（提交、审核）
- 财务：`/api/v1/finance-records`、`/cash-flows`（录入、审核、作废）
- 知识库：`/api/v1/knowledge/documents`（上传/下载/删除/重处理）、`/knowledge/search`
- 对话：`/api/v1/agent/chat`（V1 工单 Agent，SSE）

知识文档保存在 `storage/knowledge/{document_id}/`，解析成功后写入 `knowledge_chunks`（HNSW 余弦索引）。
