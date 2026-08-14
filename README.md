# Jenkins Build Archive

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](./Dockerfile)
[![GitHub](https://img.shields.io/badge/GitHub-AlexWuYh%2Fjenkins-build-archive-181717?logo=github)](https://github.com/AlexWuYh/jenkins-build-archive)

独立于 Jenkins 的**构建元数据归档服务**。在 Build Record 被清理后，仍可追溯 Git 分支 / Commit、Docker Image Tag / Digest 等信息。

| | |
|---|---|
| **作者** | [AlexWuYh](https://github.com/AlexWuYh) |
| **仓库** | https://github.com/AlexWuYh/jenkins-build-archive |
| **许可** | [MIT](./LICENSE) |
| **定位** | 内网使用；写接口 `API_TOKEN`，Web 管理 `ADMIN_PASSWORD` |

---

## 目录

1. [功能特性](#功能特性)
2. [快速开始](#快速开始)
3. [数据与备份](#数据与备份)
4. [Jenkins 接入与 Jenkinsfile](#jenkins-接入与-jenkinsfile)
5. [Docker Image Digest](#docker-image-digest)
6. [HTTP API](#http-api)
7. [Web 管理与保留策略](#web-管理与保留策略)
8. [升级](#升级)
9. [开发与测试](#开发与测试)
10. [安全说明](#安全说明)
11. [License](#license)

---

## 功能特性

- **归档写入**：Jenkins HTTP API / Shared Library；`(jobName, buildId)` 幂等
- **查询展示**：Web UI + REST；Job / 分支 / Commit / Tag 搜索与筛选
- **默认当日**：列表页日期默认当天（`TZ`）；支持「全部历史」
- **管理能力**：管理密码删除 / 批量删除；最长保留天数等策略
- **运维友好**：Docker Compose、健康检查、归档失败不影响 Jenkins 结果

---

## 快速开始

### 1. 准备配置

```bash
mkdir -p /opt/jenkins-build-archive && cd /opt/jenkins-build-archive
# 克隆或复制本仓库文件
cp .env.example .env
```

编辑 `.env`：

```dotenv
API_TOKEN=请替换成足够长的随机字符串
ADMIN_PASSWORD=请设置管理密码
TZ=Asia/Shanghai
RETENTION_DAYS=365
RETENTION_MAX_PER_JOB=0
```

### 2. 启动

```bash
docker compose up -d --build
curl http://127.0.0.1:8080/health
```

浏览器访问：`http://服务器IP:8080`（建议仅内网或经反代）。

---

## 数据与备份

| 路径 | 说明 |
|------|------|
| `./data/build_archive.db` | SQLite 主库（volume 挂载） |

```bash
# 简单拷贝
cp data/build_archive.db data/build_archive.db.$(date +%Y%m%d-%H%M%S).bak

# 在线备份（推荐）
docker exec jenkins-build-archive python -c \
  "import sqlite3; s=sqlite3.connect('/data/build_archive.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close(); s.close()"
```

---

## Jenkins 接入与 Jenkinsfile

流水线**结束时**（成功/失败均）将元数据 `POST` 到归档服务。  
**推荐 Shared Library `buildArchive()`**；也可在 Jenkinsfile 内直接 `curl`。

### 一次性配置

**全局环境变量**（Manage Jenkins → System → Global properties）：

| 变量 | 示例 | 说明 |
|------|------|------|
| `BUILD_ARCHIVE_URL` | `http://172.27.x.x:8080` | 服务根地址，无尾部 `/` |
| `BUILD_ARCHIVE_TOKEN` | 与 `.env` 的 `API_TOKEN` 相同 | 建议用 Credentials（Secret text） |

**Shared Library**（Global Pipeline Libraries）：

| 项 | 值 |
|----|-----|
| Name | `build-archive` |
| Source | 本仓库（含 `vars/buildArchive.groovy`） |

Agent 需有 `curl`。细节见 [`jenkins-shared-library/README.md`](./jenkins-shared-library/README.md)。

### 推荐 Jenkinsfile（Declarative）

```groovy
@Library('build-archive') _

pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }

    environment {
        // 可选覆盖；Token 建议 credentials('build-archive-api-token')
        // BUILD_ARCHIVE_URL = 'http://172.27.x.x:8080'
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }
        stage('Build') {
            steps { sh 'echo build...' }
        }
        stage('Docker') {
            steps {
                script {
                    env.DOCKER_REGISTRY = '172.27.15.33'
                    env.DOCKER_REPOSITORY = 'dev/dp-abcmonitor'
                    env.DOCKER_IMAGE_TAG = "${env.DOCKER_REGISTRY}/${env.DOCKER_REPOSITORY}:${env.BUILD_NUMBER}"
                    // env.DOCKER_IMAGE_DIGEST = 'sha256:....'
                }
            }
        }
    }

    post {
        always {
            buildArchive()   // 必须 always，失败构建也会入库
        }
    }
}
```

### 字段映射

| 归档字段 | Jenkins 来源 |
|----------|----------------|
| jobName | `JOB_NAME` |
| buildId | `BUILD_NUMBER`（正整数） |
| buildDate | `BUILD_TIMESTAMP` 或当前时间（上海时区） |
| gitRepository | `GIT_URL` / `GIT_REPO` |
| gitBranch | `GIT_BRANCH` / `BRANCH_NAME` |
| gitCommit | `GIT_COMMIT` |
| dockerRegistry / Repository / Tag / Digest | `DOCKER_*` 或 `DockerImageTag` |
| buildResult | `currentBuild.currentResult` |
| buildUrl | `BUILD_URL` |
| durationMs | `currentBuild.duration` |

### 推送镜像并写入 Digest

```groovy
stage('Push image') {
    steps {
        script {
            def tag = "172.27.15.33/dev/my-app:${env.BUILD_NUMBER}"
            env.DOCKER_IMAGE_TAG = tag
            sh "docker build -t ${tag} . && docker push ${tag}"
            env.DOCKER_IMAGE_DIGEST = sh(
                script: "docker inspect --format='{{index .RepoDigests 0}}' ${tag} | awk -F@ '{print \$2}'",
                returnStdout: true
            ).trim()
        }
    }
}
post { always { buildArchive() } }
```

### 不使用 Shared Library（curl）

```groovy
pipeline {
    agent any
    environment {
        BUILD_ARCHIVE_URL   = 'http://172.27.x.x:8080'
        BUILD_ARCHIVE_TOKEN = credentials('build-archive-api-token')
    }
    stages {
        stage('Build') { steps { sh 'echo build' } }
    }
    post {
        always {
            script {
                def payload = [
                    jobName: env.JOB_NAME,
                    buildId: env.BUILD_NUMBER as Integer,
                    buildDate: new Date().format("yyyy-MM-dd'T'HH:mm:ssXXX", TimeZone.getTimeZone('Asia/Shanghai')),
                    gitRepository: env.GIT_URL,
                    gitBranch: env.GIT_BRANCH ?: env.BRANCH_NAME,
                    gitCommit: env.GIT_COMMIT,
                    dockerImageTag: env.DOCKER_IMAGE_TAG,
                    dockerImageDigest: env.DOCKER_IMAGE_DIGEST,
                    buildResult: currentBuild.currentResult ?: 'UNKNOWN',
                    buildUrl: env.BUILD_URL,
                    durationMs: currentBuild.duration
                ]
                def file = "build-archive-${env.BUILD_NUMBER}.json"
                try {
                    writeFile file: file, text: groovy.json.JsonOutput.toJson(payload)
                    withEnv([
                        "BUILD_ARCHIVE_POST_URL=${env.BUILD_ARCHIVE_URL.replaceAll('/+$', '')}/api/v1/builds",
                        "BUILD_ARCHIVE_POST_TOKEN=${env.BUILD_ARCHIVE_TOKEN}",
                        "BUILD_ARCHIVE_PAYLOAD_FILE=${file}",
                    ]) {
                        sh '''
                            set +x
                            curl --fail --silent --show-error --retry 3 --connect-timeout 5 --max-time 15 \
                              -X POST "${BUILD_ARCHIVE_POST_URL}" \
                              -H "Content-Type: application/json" \
                              -H "Authorization: Bearer ${BUILD_ARCHIVE_POST_TOKEN}" \
                              --data-binary @"${BUILD_ARCHIVE_PAYLOAD_FILE}"
                        '''
                    }
                } catch (err) {
                    echo "[BuildArchive] WARNING: ${err}"
                } finally {
                    sh "rm -f '${file}' || true"
                }
            }
        }
    }
}
```

### 手工验证

```bash
curl -X POST http://127.0.0.1:8080/api/v1/builds \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{"jobName":"demo","buildId":1,"buildDate":"2026-08-14T10:00:00+08:00","buildResult":"SUCCESS","buildUrl":"https://jenkins.example/job/demo/1/"}'
```

### 常见问题

| 现象 | 处理 |
|------|------|
| `BUILD_ARCHIVE_URL is not configured; skip` | 检查全局/Job 环境变量 |
| curl 401 | Token 与服务端 `API_TOKEN` 不一致 |
| `Invalid BUILD_NUMBER` | 检查 `BUILD_NUMBER` 是否为正整数 |
| 无镜像信息 | 在 `buildArchive()` 前设置 `DOCKER_*` |
| 分支带 `origin/` | 归档前去掉前缀，或接受原始值 |

---

## Docker Image Digest

Tag 可被覆盖，长期追溯请同时记录 Digest。服务**不会**主动查 Registry；由 Jenkins 通过 `DOCKER_IMAGE_DIGEST` 传入。

---

## HTTP API

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/health` | 无 | 健康检查 |
| GET | `/api/v1/stats` | 无 | 统计 |
| GET | `/api/v1/builds` | 无 | 列表（`q/job/branch/result/dateFrom/dateTo/page/pageSize`） |
| GET | `/api/v1/builds/{id}` | 无 | 详情 |
| POST | `/api/v1/builds` | Bearer Token | 创建/更新（幂等） |
| DELETE | `/api/v1/builds/{id}` | Bearer Token | 删除 |
| GET | `/api/v1/admin/retention` | Bearer Token | 保留配置 |
| POST | `/api/v1/admin/retention/run` | Bearer Token | 执行清理 |

- `dateFrom` / `dateTo`：ISO 或 `YYYY-MM-DD`（按整天）
- `pageSize`：1–100（UI 常用 20/50/100）
- **API 列表默认不过滤日期**；Web 列表默认当天（`/?all=1` 看全部）

---

## Web 管理与保留策略

| 能力 | 入口 | 鉴权 |
|------|------|------|
| 单条删除 | 详情页 | `ADMIN_PASSWORD` + 确认词 `DELETE` |
| 批量删除 | 列表勾选 | 同上 |
| 保留策略 | `/admin` | 同上 |

环境变量（UI 保存后写入 DB，**优先于** env）：

| 变量 | 含义 |
|------|------|
| `RETENTION_DAYS` | 最长保留天数；`0` 关闭 |
| `RETENTION_MAX_PER_JOB` | 每 Job 最多保留条数；`0` 关闭 |
| `ADMIN_PASSWORD` | Web 管理密码 |

清理不可恢复，变更前请备份数据库。

---

## 升级

```bash
git pull
docker compose up -d --build
```

表结构幂等初始化，无需手工建表。

---

## 开发与测试

需要 **Python 3.12+**（与 Docker 镜像一致）：

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export API_TOKEN=dev-token-for-local ADMIN_PASSWORD=dev-admin
export DATABASE_PATH=./data/build_archive.db TZ=Asia/Shanghai
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
pytest -q
```

协作约定见 [`AGENTS.md`](./AGENTS.md) 与 [`.ai/`](./.ai/)。

---

## 安全说明

面向**内网**。读路径默认开放；写与管理操作 fail-closed。

| 风险 | 建议 |
|------|------|
| 读路径暴露 | 勿映射公网；反代限制来源 |
| Token / 管理密码泄露 | 分用途保管；定期轮换 |
| 默认占位密钥 | 部署前必须修改 |
| 保留策略过激 | 先备份再收紧 |

详见 [`.ai/03_SECURITY.md`](./.ai/03_SECURITY.md)。

---

## License

本项目采用 [MIT License](./LICENSE)。

```
Copyright (c) 2026 AlexWuYh
```

- **Author:** [AlexWuYh](https://github.com/AlexWuYh)
- **Repository:** https://github.com/AlexWuYh/jenkins-build-archive
