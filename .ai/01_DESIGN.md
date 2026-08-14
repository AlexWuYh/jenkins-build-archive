# 01 — 设计

## 架构

```text
Jenkins Pipeline (Shared Library buildArchive)
        │  POST /api/v1/builds  + Bearer Token
        ▼
   FastAPI (app/main.py)
        │
        ├── 读：Web UI (Jinja) + GET APIs（默认无鉴权，内网）
        ├── 写：POST builds（API Token）
        ├── 管 API：DELETE / retention（API Token）
        ├── 管 UI：删除 / 批量删除 / 保留策略（ADMIN_PASSWORD）
        └── 闪现提示：Cookie jba_flash（一次性，非 URL notice）
        ▼
   SQLite WAL  (DATABASE_PATH)
```

## 数据模型

表 `build_records`：

| 列 | 说明 |
|----|------|
| `job_name`, `build_id` | 唯一键；幂等 upsert |
| `build_date` | Jenkins 构建时间（ISO，可带时区） |
| `git_repository`, `git_branch`, `git_commit` | 基础 Git；`git_commit` 与 `commit_id` 写入/读出时互相回填 |
| `commit_msg`, `commit_author`, `commit_id` | Commit 元数据（API camelCase）；详情页 SHA 只在 Git 信息展示一次 |
| `commit_files` | TEXT，JSON 数组字符串，如 `["a.py","b.py"]` |
| `docker_*` | Registry / repo / tag / digest |
| `build_result`, `build_url`, `duration_ms` | 构建结果 |
| `created_at`, `updated_at` | 服务端 UTC（`...Z`） |

迁移：`db._ensure_build_record_columns` 对旧库幂等 `ALTER TABLE`。

表 `app_settings`：保留策略等运行时配置（优先于环境变量）。

## API 一览

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 健康检查 |
| GET | `/api/v1/stats` | 无 | 基础统计 |
| GET | `/api/v1/builds` | 无 | 列表筛选分页（默认**不过滤**日期） |
| GET | `/api/v1/builds/{id}` | 无 | 详情（含 commit*） |
| POST | `/api/v1/builds` | API Token | 创建/更新（幂等） |
| DELETE | `/api/v1/builds/{id}` | API Token | 删除单条（脚本） |
| GET | `/api/v1/admin/retention` | API Token | 当前保留配置 |
| POST | `/api/v1/admin/retention/run` | API Token | 立即执行保留策略 |
| GET | `/` | 无 | 列表 UI（默认**当日**日期） |
| GET | `/build/{id}` | 无 | 详情 UI |
| POST | `/build/{id}/delete` | 管理密码 + `DELETE` | UI 单条删除 |
| POST | `/builds/batch-delete` | 管理密码 + `DELETE` + `ids` | UI 批量删除 |
| GET/POST | `/admin` `/admin/retention` | 管理密码 | 保留策略 |

### POST `/api/v1/builds` 正文（camelCase）

必填：`jobName`, `buildId`, `buildDate`  
可选：`gitRepository`, `gitBranch`, `gitCommit`, **`commitMsg`**, **`commitAuthor`**, **`commitId`**, **`commitFiles`**（`string[]` 或换行/JSON 字符串）, `dockerRegistry`, `dockerRepository`, `dockerImageTag`, `dockerImageDigest`, `buildResult`, `buildUrl`（仅 http/https）, `durationMs`

## 查询约定

- 模糊：`q` 匹配 job/branch/commit/tag/repository（LIKE + ESCAPE）
- 精确：`job`、`result`
- 分支：`branch` 为 LIKE
- 日期：`dateFrom`/`dateTo` 支持 ISO 或 `YYYY-MM-DD`（按整天）
- Web 列表：未带日期参数时默认填入本地当日（`TZ`）；`/?all=1` 为全部历史
- 分页：`pageSize` 20/50/100；深分页有上限（见 `queries.MAX_PAGE`）

## 保留策略

| 来源 | 说明 |
|------|------|
| `app_settings`（UI 保存） | 优先 |
| `RETENTION_DAYS` / `RETENTION_MAX_PER_JOB` | 回退；`0` 关闭 |

执行：启动时（若启用）、`/admin`「保存并立即清理」、`POST /api/v1/admin/retention/run`。

## 闪现提示

删除 / 保留策略成功后 **303 到干净 URL**，文案放 Cookie `jba_flash`（httponly，约 60s），下一页读取后删除，避免 URL `notice=` 常驻。

## Shared Library

- 配置：`BUILD_ARCHIVE_URL`、`BUILD_ARCHIVE_TOKEN`
- 可选 env / call 参数：Docker 字段 + commit 字段
- payload 写文件；URL/Token 经 env 传给 curl
- 失败只 WARNING
