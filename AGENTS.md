# AGENTS.md

> 本文件是 Grok / AI 编码助手在本仓库的**执行入口**。  
> 全局规范见 `~/.grok/rules/00-ai-coding-standards.md`。

## 项目

- **名称**：Jenkins Build Archive
- **一句话**：独立于 Jenkins 的构建元数据归档服务，解决 Build Record 清理后无法追溯 Git/Docker 信息的问题
- **当前里程碑**：M0–M8 均已完成（含 Commit 详情字段）；后续规划见下方「后续规划」
- **部署假设**：内网使用；读接口默认开放；Jenkins 写用 `API_TOKEN`；Web 管理用 `ADMIN_PASSWORD`

## 必读文档

| 文档 | 内容 |
|------|------|
| [`README.md`](./README.md) | 功能、部署、HTTP API、Jenkins 接入、安全说明 |
| [`jenkins-shared-library/README.md`](./jenkins-shared-library/README.md) | Shared Library 用法 |

架构与模块边界以代码为准：`app/`（服务端）、`tests/`（测试）、`jenkins-shared-library/`（Jenkins 侧）。

## 后续规划

- 读路径可选 Basic Auth / 反向代理示例配置片段
- SQLite FTS5 全文检索（替代多列 LIKE）
- 定时后台 retention（当前：启动时 + 手动 run）
- 游标/keyset 分页（替代深 OFFSET）

## 常用命令

```bash
# 本地依赖（开发）
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 运行（开发）
export API_TOKEN=dev-token-for-local
export ADMIN_PASSWORD=dev-admin
export DATABASE_PATH=./data/build_archive.db
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# 测试
pytest -q

# Docker
cp .env.example .env   # 修改 API_TOKEN 与 ADMIN_PASSWORD
docker compose up -d --build
curl http://127.0.0.1:8080/health
```

## 约定

- 仅实现**当前里程碑**范围；超出部分写入上方「后续规划」。
- 行为或接口变更时，同步更新 `README.md` 与本文件。
- 禁止提交密钥；示例使用环境变量占位。
- 归档失败不得影响 Jenkins 原始构建结果（Shared Library 必须 catch 错误）。
- 写接口：`API_TOKEN` 未配置或为默认占位时 **fail-closed（503）**。
- Web 管理：`ADMIN_PASSWORD` 未配置或为默认占位时 **fail-closed（503）**。

## 本项目禁止

- 不引入公网多租户 / OAuth / 复杂权限体系（超出内网定位）。
- 不主动查询 Docker Registry（Digest 由 Jenkins 侧传入）。
- 不把 `API_TOKEN` 暴露到浏览器前端或静态资源。
- 不在文档中写入真实内网地址、token、账号。

## 文档同步

代码变更后检查：里程碑状态、设计偏差、README 用户说明与安全说明是否仍准确。
