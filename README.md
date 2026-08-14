# Jenkins Build Archive

独立于 Jenkins 的构建历史归档服务。用于解决 Jenkins Build Record 按保留策略清理后，无法追溯历史版本 Git 分支、Commit、Docker Image Tag 等信息的问题。

**定位：内网使用。** 读接口与 Web UI 默认无鉴权；Jenkins 写入用 `API_TOKEN`；页面删除/保留策略用较短的 `ADMIN_PASSWORD`。部署前请阅读 [风险说明](#9-内网部署与风险说明) 与 [`.ai/03_SECURITY.md`](./.ai/03_SECURITY.md)。

## Features

- SQLite 持久化
- Docker Compose 一键部署
- Jenkins HTTP API 自动归档
- API Token 鉴权（Jenkins 写入 / API 管理）
- 管理密码鉴权（Web UI 删除、批量删除、保留策略）
- `(JobName, BuildID)` 幂等写入
- Job / Branch / Commit / Docker Tag / Repository 全文模糊搜索
- 时间范围、Job、Result 筛选（`YYYY-MM-DD` 按整天包含）
- 分页
- 构建详情
- Jenkins Build URL 回跳（仅 `http://` / `https://`）
- Docker Image Tag / Digest 追踪
- 可配置保留策略（最长保留天数 / 每 Job 最大条数；支持管理页配置）
- 单条删除 + 列表批量删除
- `/health` 健康检查
- `/api/v1/stats` 基础统计
- Jenkins Shared Library
- Jenkins 归档失败不影响原始构建结果

## 1. 部署

```bash
mkdir -p /opt/jenkins-build-archive
cd /opt/jenkins-build-archive
```

把本项目文件复制到该目录。

创建配置：

```bash
cp .env.example .env
```

编辑 `.env`，至少修改：

```dotenv
API_TOKEN=请替换成一个足够长的随机字符串
ADMIN_PASSWORD=请设置一个管理密码（用于网页删除与保留策略）
TZ=Asia/Shanghai
# 默认保留策略（0=关闭）；也可在网页「管理」中配置，UI 配置优先
RETENTION_DAYS=365
RETENTION_MAX_PER_JOB=0
```

启动：

```bash
docker compose up -d --build
```

检查：

```bash
docker compose ps
docker compose logs -f --tail=100
curl http://127.0.0.1:8080/health
```

浏览器访问：

```text
http://服务器IP:8080
```

建议仅绑定内网地址，或在前面加 Nginx/Caddy 并限制来源 IP。

## 2. 数据持久化

数据库文件：

```text
./data/build_archive.db
```

只要 `data` 目录不删除，容器重建不会丢数据。

建议定期备份：

```bash
cp data/build_archive.db data/build_archive.db.$(date +%Y%m%d-%H%M%S).bak
```

更推荐 SQLite 在线备份：

```bash
docker exec jenkins-build-archive python -c "import sqlite3; s=sqlite3.connect('/data/build_archive.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close(); s.close()"
```

## 3. Jenkins 接入与 Jenkinsfile 编写

目标：在流水线 **结束时**（无论成功/失败）把构建元数据 POST 到归档服务。  
**推荐方式：Shared Library `buildArchive()`**；也支持在 Jenkinsfile 里直接 `curl`。

### 3.1 一次性配置（Jenkins 全局）

**① 全局环境变量**（Manage Jenkins → System → Global properties → Environment variables）：

| 变量 | 示例 | 说明 |
|------|------|------|
| `BUILD_ARCHIVE_URL` | `http://172.27.x.x:8080` | 归档服务根地址，不要带尾部 `/` |
| `BUILD_ARCHIVE_TOKEN` | 与服务端 `.env` 的 `API_TOKEN` **相同** | 写入鉴权；勿写进 Jenkinsfile 明文 |

> 也可用 Credentials 绑定为 `BUILD_ARCHIVE_TOKEN`（Secret text），比全局明文更安全。

**② Shared Library**（Manage Jenkins → System → Global Pipeline Libraries）：

| 项 | 建议值 |
|----|--------|
| Name | `build-archive` |
| Default version | 如 `main` / 标签 |
| Retrieval method | Modern SCM → 指向本仓库或仅 `jenkins-shared-library` 目录所在仓库 |
| 勾选 | Load implicitly（可选；不勾选则 Jenkinsfile 需 `@Library`） |

库代码位置见仓库内 [`jenkins-shared-library/`](./jenkins-shared-library/)（`vars/buildArchive.groovy`）。

Agent 上需有 `curl`（大多数 Linux agent 已有）。

### 3.2 推荐：Declarative Pipeline + Shared Library

最小改动——在现有流水线增加 `post { always { ... } }`：

```groovy
@Library('build-archive') _

pipeline {
    agent any

    options {
        // 可选：去掉过旧构建，归档服务负责长期元数据
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }

    environment {
        // 若未配全局变量，可在 Job 级覆盖（Token 仍建议用 credentials）
        // BUILD_ARCHIVE_URL = 'http://172.27.x.x:8080'
        // BUILD_ARCHIVE_TOKEN = credentials('build-archive-api-token')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                // 你的编译 / 测试步骤
                sh 'echo build...'
            }
        }

        stage('Docker') {
            steps {
                script {
                    // 按实际镜像命名规则赋值，供 buildArchive 读取
                    env.DOCKER_REGISTRY = '172.27.15.33'
                    env.DOCKER_REPOSITORY = 'dev/dp-abcmonitor'
                    env.DOCKER_IMAGE_TAG = "${env.DOCKER_REGISTRY}/${env.DOCKER_REPOSITORY}:${env.BUILD_NUMBER}"
                    // 若 docker push 后拿到 digest，一并写入（强烈建议）
                    // env.DOCKER_IMAGE_DIGEST = 'sha256:....'
                }
                // sh 'docker build -t $DOCKER_IMAGE_TAG .'
                // sh 'docker push $DOCKER_IMAGE_TAG'
            }
        }
    }

    // 关键：无论 SUCCESS / FAILURE / ABORTED 都会尝试归档
    post {
        always {
            buildArchive()
        }
    }
}
```

说明：

- 必须放在 **`post { always { } }`**，不要只放在 `success`，否则失败构建不会入库。
- `buildArchive()` **失败只打 WARNING**，不会改 `currentBuild.result`。
- 未配置 `BUILD_ARCHIVE_URL` / `BUILD_ARCHIVE_TOKEN` 时会 skip，不拖垮流水线。

### 3.3 `buildArchive()` 会采集的字段

| 归档字段 | 来源（按优先级） |
|----------|------------------|
| jobName | `env.JOB_NAME` |
| buildId | `env.BUILD_NUMBER`（须为正整数） |
| buildDate | `env.BUILD_TIMESTAMP`，否则当前时间（Asia/Shanghai） |
| gitRepository | `env.GIT_URL` 或 `env.GIT_REPO` |
| gitBranch | `env.GIT_BRANCH` 或 `env.BRANCH_NAME` |
| gitCommit | `env.GIT_COMMIT` |
| dockerRegistry | `env.DOCKER_REGISTRY` |
| dockerRepository | `env.DOCKER_REPOSITORY` |
| dockerImageTag | `env.DockerImageTag` 或 `env.DOCKER_IMAGE_TAG` |
| dockerImageDigest | `env.DOCKER_IMAGE_DIGEST` |
| buildResult | `currentBuild.currentResult` |
| buildUrl | `env.BUILD_URL` |
| durationMs | `currentBuild.duration` |

Git 多分支流水线通常自带 `GIT_*` / `BRANCH_NAME`。若 checkout 未注入，请在 stage 里自行 `env.GIT_COMMIT = ...`。

### 3.4 带 Docker Digest 的示例片段

```groovy
stage('Push image') {
    steps {
        script {
            def registry = '172.27.15.33'
            def repo = 'dev/my-app'
            def tag = "${registry}/${repo}:${env.BUILD_NUMBER}"
            env.DOCKER_REGISTRY = registry
            env.DOCKER_REPOSITORY = repo
            env.DOCKER_IMAGE_TAG = tag

            sh "docker build -t ${tag} ."
            sh "docker push ${tag}"

            // 推送后解析 digest（按你环境的 docker/inspect 方式调整）
            env.DOCKER_IMAGE_DIGEST = sh(
                script: "docker inspect --format='{{index .RepoDigests 0}}' ${tag} | awk -F@ '{print \$2}'",
                returnStdout: true
            ).trim()
        }
    }
}

post {
    always {
        buildArchive()
    }
}
```

也可调用时显式传地址/Token（一般不推荐写死 Token）：

```groovy
buildArchive(url: 'http://172.27.x.x:8080', token: env.BUILD_ARCHIVE_TOKEN)
```

### 3.5 不使用 Shared Library：Jenkinsfile 内直接 curl

适合暂时无法配 Library 的 Job。注意：**Token 用环境变量**，不要拼进脚本字面量。

```groovy
pipeline {
    agent any

    environment {
        BUILD_ARCHIVE_URL   = 'http://172.27.x.x:8080'
        BUILD_ARCHIVE_TOKEN = credentials('build-archive-api-token')
        DOCKER_IMAGE_TAG    = "172.27.15.33/dev/my-app:${BUILD_NUMBER}"
    }

    stages {
        stage('Build') {
            steps {
                sh 'echo your build here'
            }
        }
    }

    post {
        always {
            script {
                def payload = [
                    jobName          : env.JOB_NAME,
                    buildId          : env.BUILD_NUMBER as Integer,
                    buildDate        : new Date().format("yyyy-MM-dd'T'HH:mm:ssXXX", TimeZone.getTimeZone('Asia/Shanghai')),
                    gitRepository    : env.GIT_URL,
                    gitBranch        : env.GIT_BRANCH ?: env.BRANCH_NAME,
                    gitCommit        : env.GIT_COMMIT,
                    dockerRegistry   : env.DOCKER_REGISTRY,
                    dockerRepository : env.DOCKER_REPOSITORY,
                    dockerImageTag   : env.DOCKER_IMAGE_TAG,
                    dockerImageDigest: env.DOCKER_IMAGE_DIGEST,
                    buildResult      : currentBuild.currentResult ?: 'UNKNOWN',
                    buildUrl         : env.BUILD_URL,
                    durationMs       : currentBuild.duration
                ]
                def json = groovy.json.JsonOutput.toJson(payload)
                def file = "build-archive-${env.BUILD_NUMBER}.json"
                try {
                    writeFile file: file, text: json
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
                    echo "[BuildArchive] ok ${env.JOB_NAME} #${env.BUILD_NUMBER}"
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

### 3.6 用 curl 手工验证（与 Jenkins 无关）

```bash
curl -X POST http://127.0.0.1:8080/api/v1/builds \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{
    "jobName": "dp-abcmonitor",
    "buildId": 1823,
    "buildDate": "2026-08-14T10:32:18+08:00",
    "gitRepository": "https://github.com/example/demo.git",
    "gitBranch": "release/2.3.1",
    "gitCommit": "a8f31c2",
    "dockerRegistry": "172.27.15.33",
    "dockerRepository": "dev/dp-abcmonitor",
    "dockerImageTag": "2.3.1-1823",
    "dockerImageDigest": "sha256:xxx",
    "buildResult": "SUCCESS",
    "buildUrl": "https://jenkins.example.com/job/dp-abcmonitor/1823/",
    "durationMs": 185000
  }'
```

### 3.7 常见问题

| 现象 | 处理 |
|------|------|
| 日志 `BUILD_ARCHIVE_URL is not configured; skip` | 检查全局/Job 环境变量 |
| 日志 `archive failed` / curl 401 | Token 是否与服务端 `API_TOKEN` 一致 |
| 日志 `Invalid BUILD_NUMBER` | 非 Pipeline 或编号异常，检查 `BUILD_NUMBER` |
| 归档了但没有镜像信息 | 在 `buildArchive()` **之前**设置 `DOCKER_*` 环境变量 |
| 分支显示 `origin/xxx` | 来自 `GIT_BRANCH` 原始值；可在归档前 `env.GIT_BRANCH = env.GIT_BRANCH?.replaceFirst('^origin/', '')` |
| 多分支 Pipeline 找不到 Library | Library 勾选 *Allow default version to be overridden*，或 Job 配置信任该库 |

更短的库配置说明见 [`jenkins-shared-library/README.md`](./jenkins-shared-library/README.md)。

## 4. 关于 Docker Image Digest

Tag 可以被覆盖，因此长期追溯最好同时记录 Digest。当前服务不会主动从 Registry 查询 Digest，Jenkins 在构建/推送镜像时如果已经获得 Digest，可通过 `DOCKER_IMAGE_DIGEST` 传入。

## 5. API

### Health

```text
GET /health
```

### Stats

```text
GET /api/v1/stats
```

### Create / Update

```text
POST /api/v1/builds
```

需要 Token。`(jobName, buildId)` 冲突时更新其余字段。

### List

```text
GET /api/v1/builds?q=2.3.1&page=1&pageSize=20
```

支持：

- `q`
- `job`
- `branch`
- `result`
- `dateFrom` / `dateTo`（完整 ISO，或 `YYYY-MM-DD`；后者按当天 00:00:00～23:59:59.999999 处理）
- `page`（≥1；UI 深分页有上限，大数据请配合筛选）
- `pageSize`（20 / 50 / 100，默认 20）

列表页在数据量大时会提示使用 Job/时间筛选；Job 下拉仅展示最近活跃的 Job，避免选项过多拖慢页面。

**默认日期：** 列表页开始/结束日期**默认填入当天**（`TZ`，默认 `Asia/Shanghai`），并按该范围过滤。需要全部历史请点「全部历史」（`/?all=1`）。API 列表默认不过滤日期。

### Detail

```text
GET /api/v1/builds/{id}
```

### Delete（API，给脚本用）

```text
DELETE /api/v1/builds/{id}
Authorization: Bearer <API_TOKEN>
```

### Web UI 删除（管理密码）

**单条：** 构建详情 →「管理：删除此记录」→ 填写 **管理密码** → 确认框输入 `DELETE`。

```text
POST /build/{id}/delete
password=<ADMIN_PASSWORD>&confirm=DELETE
```

**批量：** 列表页勾选记录 → 底部批量删除区填写管理密码 + `DELETE`。

```text
POST /builds/batch-delete
ids=1&ids=2&password=<ADMIN_PASSWORD>&confirm=DELETE
```

成功后 303 回列表并提示。密码不会写进页面源码。

### 保留策略

**网页配置（推荐）：** 打开 `/admin`，设置「最长保留天数」（如 `365`）与可选的「每 Job 最大条数」，用管理密码保存；可「保存并立即清理」。

配置写入 SQLite `app_settings`，**优先于**环境变量。

环境变量（初始默认 / 未在 UI 保存时生效）：

| 变量 | 含义 | 默认 |
|------|------|------|
| `RETENTION_DAYS` | 最长保留天数；只保留该天数内的数据；`0` 关闭 | `0` |
| `RETENTION_MAX_PER_JOB` | 每个 Job 仅保留最新 N 条；`0` 关闭 | `0` |
| `ADMIN_PASSWORD` | Web 管理密码（删除 / 保留策略） | 须修改 |

API（仍用 `API_TOKEN`）：

```text
GET  /api/v1/admin/retention
POST /api/v1/admin/retention/run
```

启用后：服务启动时若策略有效会执行一次清理；也可在 `/admin` 点「保存并立即清理」。

**注意：** 清理不可恢复（除非有 DB 备份）。例如设为 365 天，会删除 `build_date` 早于「现在 − 365 天」的记录。

## 6. 升级

```bash
git pull
# 或替换项目文件

docker compose up -d --build
```

数据库会自动执行幂等初始化，不需要手工建表。

## 7. 开发与测试

需要 Python 3.12+（与 Docker 镜像一致；系统默认若为 3.14，请显式使用 3.12）：

```bash
/opt/homebrew/bin/python3.12 -m venv .venv   # 或其它 3.12 路径
source .venv/bin/activate
pip install -r requirements-dev.txt
export API_TOKEN=dev-token-for-local
export DATABASE_PATH=./data/build_archive.db
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
pytest -q
```

AI / 协作者文档见 [`AGENTS.md`](./AGENTS.md) 与 [`.ai/`](./.ai/)。

## 8. 内网部署与风险说明

本服务假设部署在**内网**，与 Jenkins 同网段或经 VPN 访问。

| 风险点 | 说明 | 建议 |
|--------|------|------|
| 读路径默认开放 | 任意能访问端口的人可浏览 Job/分支/Commit/镜像信息 | 防火墙、安全组、反代限制来源；勿把端口映射公网 |
| API Token 泄露 | 可写入伪造记录或调用删除 API | 长随机 Token，仅 Jenkins 配置，定期轮换 |
| 管理密码泄露 | 可通过网页删除数据、改保留策略 | 仅运维知晓；勿与 API Token 混用；勿写进前端 |
| 未修改默认密钥 | `API_TOKEN` / `ADMIN_PASSWORD` 为占位时相关操作 503 | 部署检查必须改掉 |
| 明文 HTTP | 同网段可嗅探密钥与元数据 | 生产前加 HTTPS 反代 |
| 保留策略过激 | 历史被清且默认不可恢复 | 变更前备份；最长保留天数先偏大后收紧 |
| SQLite 文件 | `./data` 含全量元数据 | 按机密数据做权限与备份 |

完整威胁模型见 [`.ai/03_SECURITY.md`](./.ai/03_SECURITY.md)。

**生产建议：**

1. 前面加现有 Nginx/Caddy，启用 HTTPS，限制来源 IP。
2. `API_TOKEN` 只给 Jenkins；`ADMIN_PASSWORD` 只给运维网页操作。
3. 定期备份 `data/build_archive.db`。
4. 按合规需要设置最长保留（例如 365 天），可在 `/admin` 配置。
