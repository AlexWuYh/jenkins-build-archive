# 02 — 目录结构

```text
.
├── AGENTS.md                 # Agent 执行入口
├── README.md                 # 人类部署与使用
├── .ai/                      # AI / 协作者项目知识
│   ├── 00_PROJECT.md
│   ├── 01_DESIGN.md
│   ├── 02_STRUCTURE.md
│   ├── 03_SECURITY.md
│   └── MILESTONES.md
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI 路由、鉴权、UI
│   ├── db.py                 # SQLite、app_settings、PRAGMA/索引
│   ├── queries.py            # 列表搜索/统计（分页、下拉有界）
│   ├── schemas.py            # Pydantic 入参
│   ├── retention.py          # 保留策略读写与执行
│   ├── static/app.css
│   └── templates/            # index（批量删除）/ detail / admin
├── tests/                    # pytest
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
| `db.py` | 连接、PRAGMA、建表 | 业务校验 |
| `schemas.py` | 请求体校验 | 数据库访问 |
| `retention.py` | 按配置删除过期/超额记录 | HTTP |
| `main.py` | HTTP、鉴权、搜索、模板 | Jenkins 侧逻辑 |
| `buildArchive.groovy` | 采集 env 并 POST | 服务端存储 |

## 扩展指引

- 新查询字段：同步 `schemas`、表结构、`search_builds`、模板、测试
- 新管理操作：必须走 `require_token`，并更新 `03_SECURITY.md`
