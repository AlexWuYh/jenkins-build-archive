# 01 — 设计

## 架构

```text
Jenkins Pipeline (Shared Library buildArchive)
        │  POST /api/v1/builds  + Bearer Token
        ▼
   FastAPI (app/main.py)
        │
        ├── 读：Web UI (Jinja) + GET APIs（默认无鉴权，内网）
        ├── 写：POST builds（Token）
        ├── 管：DELETE build / retention run（Token）
        ▼
   SQLite WAL  (DATABASE_PATH)
```

## 数据模型

表 `build_records`：

- 唯一约束：`(job_name, build_id)`
- 写入语义：`INSERT ... ON CONFLICT DO UPDATE`（幂等）
- 时间字段：
  - `build_date`：Jenkins 侧构建时间（ISO 字符串，可能带时区）
  - `created_at` / `updated_at`：服务端 UTC（`...Z`）

## API 一览

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 健康检查 |
| GET | `/api/v1/stats` | 无 | 基础统计 |
| GET | `/api/v1/builds` | 无 | 列表筛选分页 |
| GET | `/api/v1/builds/{id}` | 无 | 详情 |
| POST | `/api/v1/builds` | API Token | 创建/更新 |
| DELETE | `/api/v1/builds/{id}` | API Token | 删除单条（脚本） |
| GET | `/api/v1/admin/retention` | API Token | 当前保留配置 |
| POST | `/api/v1/admin/retention/run` | API Token | 立即执行保留策略 |
| GET | `/` `/build/{id}` | 无 | Web UI |
| POST | `/build/{id}/delete` | 管理密码 + `DELETE` | UI 单条删除 |
| POST | `/builds/batch-delete` | 管理密码 + `DELETE` + `ids` | UI 批量删除 |
| GET/POST | `/admin` `/admin/retention` | 管理密码 | 保留策略配置与立即清理 |

## 查询约定

- 模糊：`q` 匹配 job/branch/commit/tag/repository
- 精确：`job`、`result`
- 分支：`branch` 为 LIKE
- 日期：`dateFrom`/`dateTo` 支持完整 ISO 或 `YYYY-MM-DD`（后者自动扩到日初/日末）

## 保留策略

**最长保留期限**（例：365 天）= 只保留 `build_date` 在「现在 − N 天」之内的记录。

| 来源 | 说明 |
|------|------|
| `app_settings`（UI 保存） | 优先 |
| 环境变量 `RETENTION_DAYS` / `RETENTION_MAX_PER_JOB` | 回退默认；`0` 关闭该维度 |

| 维度 | 含义 |
|------|------|
| days | 删除更早于 N 天的记录 |
| max_per_job | 每个 Job 仅保留最新 N 条 |

执行时机：启动时（若启用）、`/admin`「保存并立即清理」、`POST /api/v1/admin/retention/run`。

## Shared Library

- 配置：`BUILD_ARCHIVE_URL`、`BUILD_ARCHIVE_TOKEN`（或 call 参数）
- 将 payload 写文件，经环境变量传 URL/Token 给 `curl`，避免 shell 字面量注入
- 失败只 `echo` WARNING
