# 里程碑

## 当前阶段

**M8 — Commit 详情字段**：done  

下一阶段见「后续（planned）」。

---

## M0 — 文档与 Agent 骨架

- **状态**：done
- **目标**：建立 `AGENTS.md` + `.ai/`，固化目标与安全假设
- **范围**：项目说明、设计、结构、安全、里程碑
- **非目标**：业务代码
- **验收**：
  - [x] `AGENTS.md` 可执行（命令、阶段、禁止项）
  - [x] `.ai/00_PROJECT.md` / `01_DESIGN` / `02_STRUCTURE` / `03_SECURITY` / `MILESTONES`

---

## M1 — P0 正确性与 Jenkins 侧安全传参

- **状态**：done
- **目标**：修复日期筛选边界；Shared Library 避免 shell 拼接 token
- **范围**：
  - `dateFrom`/`dateTo` 对 `YYYY-MM-DD` 规范化
  - `buildArchive.groovy` 用环境变量 + 文件传 payload
- **非目标**：保留策略、鉴权模型变更
- **验收**：
  - [x] `dateTo=当天` 能包含当天构建
  - [x] token 不直接拼进 shell 字符串字面量

---

## M2 — 内网风险文档与输入校验

- **状态**：done
- **目标**：文档写清读开放/写鉴权；加固 URL 与分页
- **范围**：
  - `.ai/03_SECURITY.md` + README 风险说明
  - `buildUrl` 仅允许 `http://` / `https://`
  - HTML 列表 `page` 下限校验
- **非目标**：读接口强制鉴权
- **验收**：
  - [x] 安全文档含威胁模型与运维建议
  - [x] 非法 `buildUrl` 被拒绝
  - [x] `page < 1` 返回 422

---

## M3 — 保留策略与管理端删除

- **状态**：done
- **目标**：可配置清理 + 鉴权删除 API
- **范围**：
  - `DELETE /api/v1/builds/{id}`
  - `GET/POST /api/v1/admin/retention*`
  - 环境变量 `RETENTION_DAYS` / `RETENTION_MAX_PER_JOB`
  - 启动时若启用则执行一次保留策略
- **非目标**：复杂定时调度 UI、按用户 ACL 删除
- **验收**：
  - [x] 无 token 无法删除
  - [x] 保留策略可按天 / 每 Job 上限清理
  - [x] README / 设计文档已说明配置项

---

## M4 — 工程化测试

- **状态**：done
- **目标**：核心路径自动化测试
- **范围**：pytest + TestClient；auth、upsert、date 边界、delete、retention
- **非目标**：E2E 浏览器、Jenkins 真机
- **验收**：
  - [x] `pytest -q` 通过（18 tests）
  - [x] `requirements-dev.txt` 存在
  - [x] AGENTS.md 命令可用

---

## M5 — 管理 UI 删除

- **状态**：done
- **目标**：详情页可删除单条记录，Token 由操作者提交、不嵌入页面
- **范围**：
  - 详情页删除表单（Token + 确认词 `DELETE`）
  - `POST /build/{id}/delete` → 成功 303 回列表并提示
  - 列表页 flash 提示
- **非目标**：列表批量删除、会话登录态、管理 UI 跑 retention
- **验收**：
  - [x] 错误 Token / 未确认 不删除
  - [x] 成功删除后记录消失且列表有提示
  - [x] 页面 HTML 不含 API Token 明文
  - [x] 测试覆盖 UI 删除路径

---

## M6 — 管理密码、批量删除、保留策略配置

- **状态**：done
- **目标**：UI 用管理密码（非长 Token）；支持批量删除；可配置最长保留天数
- **范围**：
  - `ADMIN_PASSWORD` 用于 Web 删除 / 批量删除 / `/admin` 保留策略
  - 列表勾选批量删除
  - 保留策略写入 `app_settings`，支持如 365 天最长保留
- **验收**：
  - [x] 单条/批量删除使用管理密码
  - [x] 页面不嵌入密码
  - [x] 管理页可保存 365 天策略并立即清理
  - [x] pytest 通过

---

## M7 — 大数据量列表性能与展示

- **状态**：done
- **目标**：数据量增大时列表仍可用：查询合并、分页可控、下拉有界
- **范围**：
  - 列表查询模块 `app/queries.py`；统计一次扫描
  - pageSize 20/50/100；深分页上限；Job 下拉最近 300
  - LIKE 转义；补充索引与 SQLite PRAGMA
  - 大数据量筛选提示
- **验收**：
  - [x] pageSize 生效
  - [x] 特殊字符搜索不报错
  - [x] pytest 通过

---

## M8 — Commit 详情字段

- **状态**：done
- **目标**：归档并展示 Jenkins 推送的 commitMsg / commitAuthor / commitId / commitFiles
- **范围**：
  - DB 列 + 幂等迁移；API camelCase 入参
  - 详情页「Commit 详情」卡片（Author / Message / Files）
  - Git 信息 Commit 与 `commitId` 互相回填，详情页 SHA 只显示一次（避免重复/空值）
  - Shared Library 采集 env / call 参数
  - README / `.ai` 文档同步
- **验收**：
  - [x] POST 可写入并 GET 回读
  - [x] 详情页展示 message/author/files；SHA 在 Git 信息（可回退 commitId）
  - [x] 列表兼容旧库无列（迁移后可用）
  - [x] pytest 覆盖（含仅 commitId 时 Git 卡片有值）

### 同期已落地（文档对齐，不单列里程碑）

- Web 列表默认当日；`/?all=1` 全部历史
- 删除/保留策略成功提示用 Cookie 闪现（非 URL notice）
- 页脚作者/GitHub/MIT；favicon；README 截图

---

## 后续（planned，未实现）

- 读路径可选 Basic Auth / 反向代理示例配置片段
- SQLite FTS5 全文检索（替代多列 LIKE）
- 定时后台 retention（当前：启动时 + 手动 run）
- 游标/keyset 分页（替代深 OFFSET）
