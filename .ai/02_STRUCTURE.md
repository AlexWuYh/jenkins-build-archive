# 02 — 目录结构

```text
.
├── AGENTS.md
├── README.md
├── LICENSE
├── .ai/
│   ├── 00_PROJECT.md
│   ├── 01_DESIGN.md
│   ├── 02_STRUCTURE.md
│   ├── 03_SECURITY.md
│   └── MILESTONES.md
├── app/
│   ├── main.py               # 路由、鉴权、UI、flash cookie
│   ├── db.py                 # SQLite、迁移、app_settings
│   ├── queries.py            # 列表搜索/统计/默认当日
│   ├── schemas.py            # Pydantic（含 commit* 字段）
│   ├── retention.py
│   ├── static/
│   │   ├── app.css
│   │   └── favicon.svg
│   └── templates/            # base / index / detail / admin / _pagination
├── docs/images/              # README 截图等
├── tests/
├── jenkins-shared-library/
│   ├── README.md
│   └── vars/buildArchive.groovy
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

## 模块边界

| 模块 | 职责 | 不负责 |
|------|------|--------|
| `db.py` | 连接、PRAGMA、建表、列迁移 | 业务校验 |
| `schemas.py` | 请求体校验、`commitFiles` 规范化 | 数据库访问 |
| `queries.py` | 筛选、分页、默认当日、统计 | HTTP / 鉴权 |
| `retention.py` | 按配置删除过期/超额记录 | HTTP |
| `main.py` | HTTP、鉴权、模板、flash | Jenkins 侧逻辑 |
| `buildArchive.groovy` | 采集 env/参数并 POST | 服务端存储 |

## 扩展指引

- **新归档字段**：`schemas` → `db` 建表+迁移 → `main` INSERT/upsert + `row_to_dict` → 详情模板 → Shared Library → README 字段表 → 测试
- **新管理操作**：Web 用 `ADMIN_PASSWORD`；API 用 Token；同步 `03_SECURITY.md`
