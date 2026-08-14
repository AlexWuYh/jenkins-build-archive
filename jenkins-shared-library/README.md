# Jenkins Shared Library

完整的 Jenkinsfile 示例、字段说明与排错见仓库根目录 [README.md §3](../README.md#3-jenkins-接入与-jenkinsfile-编写)。

## 1. Configure global variables

Jenkins → Manage Jenkins → System → Global properties → Environment variables:

- `BUILD_ARCHIVE_URL=http://jenkins-build-archive:8080`（或内网 IP/反代地址）
- `BUILD_ARCHIVE_TOKEN=<same as service API_TOKEN>`

Prefer **Credentials** (Secret text) for the token when possible.

## 2. Configure Shared Library

Jenkins → Manage Jenkins → System → Global Pipeline Libraries

| Field | Value |
|-------|--------|
| Name | `build-archive` |
| Source | this repo / path containing `vars/buildArchive.groovy` |

## 3. Minimal Jenkinsfile

```groovy
@Library('build-archive') _

pipeline {
    agent any

    stages {
        // your stages; set DOCKER_* before post if you need image metadata
    }

    post {
        always {
            buildArchive()
        }
    }
}
```

Optional env (set in stages before `post`):

- `DOCKER_REGISTRY` / `DOCKER_REPOSITORY`
- `DOCKER_IMAGE_TAG` or `DockerImageTag`
- `DOCKER_IMAGE_DIGEST`
- `commitMsg` / `COMMIT_MSG`, `commitAuthor` / `COMMIT_AUTHOR`
- `commitId` / `COMMIT_ID` (defaults to `GIT_COMMIT`)
- `commitFiles` / `COMMIT_FILES` (list, JSON array string, or newline-separated paths)

Archive failure only logs a warning; it does **not** change the build result.

## 4. Security notes

- Do not hardcode tokens in Jenkinsfiles.
- Payload is written to a temp file; URL/token are passed via env into `curl`.
- Invalid `BUILD_NUMBER` skips archive (no `buildId=0` posts).
