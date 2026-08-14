# 03 — 安全（内网定位）

## 部署假设

本服务**面向内网**使用，典型部署：

- 与 Jenkins 同一机房 / VPC / 办公网
- 仅运维与研发可访问 UI
- `API_TOKEN` 配置在 Jenkins；`ADMIN_PASSWORD` 仅运维持有

**不是**面向公网的多租户产品。

## 鉴权模型

| 表面 | 鉴权 |
|------|------|
| 写：`POST /api/v1/builds` | `API_TOKEN`（Bearer / X-API-Token） |
| API 删除 / API retention | `API_TOKEN` |
| Web 单条/批量删除、`/admin` 保留策略 | `ADMIN_PASSWORD`（表单字段 `password`） |
| 读：GET API + Web UI | **默认无鉴权** |
| `/health` | 无（供探活） |

未配置或仍为占位 `change-me-please` 时：

- `API_TOKEN`：写/API 管理 **503 fail-closed**
- `ADMIN_PASSWORD`：Web 管理操作 **503 fail-closed**

## 设计取舍

- **API Token**：给 Jenkins 机器使用，宜长随机串。
- **管理密码**：给人类在网页上输入，宜较短可记；**不要**与 API Token 相同（降低浏览器侧暴露面与操作负担）。
- Web 管理**不得**把密码写入 HTML/JS/静态资源；每次操作手工填写。
- 删除需二次确认词 `DELETE`。
- 成功提示使用 Cookie `jba_flash`（httponly、短 TTL、读后删除），**不含**管理密码或 API Token。
- 密码比对使用恒定时间比较（同长度 `secrets.compare_digest`）。

## 风险点（运维必读）

1. **读路径公开** — 能访问端口即可浏览元数据（含 commit 信息）；勿映射公网。
2. **API Token 泄露** — 可伪造构建写入、调用删除 API。
3. **管理密码泄露** — 可网页批量删除、修改保留策略清数据。
4. **保留策略误配置** — 如设 7 天会清掉更早历史；变更前备份。
5. **明文 HTTP** — 同网段可嗅探密钥与元数据。

## 明确不做（本阶段）

- 读接口强制登录
- 细粒度 per-job ACL
- 会话登录态 / SSO
