# 00 — 项目目标

## 一句话

独立于 Jenkins 的构建历史元数据归档：在 Build Record 被清理后，仍可追溯 Job、Git 分支/Commit（含 message/author/files）、Docker Image Tag/Digest。

## 目标

- 接收 Jenkins 推送的构建元数据并持久化（SQLite）
- `(jobName, buildId)` 幂等写入
- Web UI + REST 查询、筛选、分页、详情（含 Commit 详情）
- 管理端删除（单条/批量）与可配置保留策略
- 列表默认按当日过滤，支持全部历史
- Docker Compose 一键内网部署
- Shared Library 调用失败不影响 Jenkins 构建结果

## 非目标

- 替代 Jenkins 本身或存完整构建日志/产物
- 公网多租户、细粒度 RBAC、SSO
- 主动拉取 Registry 解析 Digest
- 高可用集群 / 多副本写（当前单机 SQLite）

## 术语

| 术语 | 含义 |
|------|------|
| Build Record | 一条构建元数据行，唯一键 `(job_name, build_id)` |
| 写接口 | `POST /api/v1/builds` 及管理类 DELETE/retention（API Token） |
| 读接口 | 列表/详情/stats 与 Web UI |
| 管理操作 | Web 删除 / 批量删除 / 保留策略（`ADMIN_PASSWORD`） |
| 保留策略 | 按天数 / 每 Job 最大条数自动清理 |
| Commit 详情 | `commitMsg` / `commitAuthor` / `commitId` / `commitFiles`（Jenkins 推送） |

## Agent 硬约束

1. 先读 `AGENTS.md` 与本文件、`MILESTONES.md`，再改代码。
2. 只做当前里程碑；管理删除与保留策略变更必须同步安全文档。
3. 密钥仅环境变量；默认 token/密码占位必须 fail-closed。
4. Shared Library：归档失败只告警，不改 `currentBuild.result`。
5. 新归档字段：同步 `schemas`、DB 迁移、`row_to_dict`、详情模板、Shared Library、README、测试。
