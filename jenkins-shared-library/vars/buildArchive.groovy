/**
 * Jenkins Shared Library: buildArchive()
 *
 * Required global environment variables:
 *   BUILD_ARCHIVE_URL  e.g. http://jenkins-build-archive:8080
 *   BUILD_ARCHIVE_TOKEN
 *
 * Optional:
 *   DOCKER_IMAGE_TAG / DockerImageTag
 *   DOCKER_IMAGE_DIGEST
 *   DOCKER_REGISTRY
 *   DOCKER_REPOSITORY
 *   commitMsg / COMMIT_MSG
 *   commitAuthor / COMMIT_AUTHOR
 *   commitId / COMMIT_ID  (defaults to GIT_COMMIT)
 *   commitFiles / COMMIT_FILES  (List, JSON array string, or newline-separated)
 *
 * Or pass via buildArchive(commitMsg: '...', commitAuthor: '...', commitId: '...', commitFiles: [...])
 *
 * Security: URL/token are passed via env vars to curl; payload via temp file.
 * Archive failure must not change the Jenkins build result.
 */
def call(Map config = [:]) {
    def archiveUrl = config.url ?: env.BUILD_ARCHIVE_URL
    def token = config.token ?: env.BUILD_ARCHIVE_TOKEN

    if (!archiveUrl?.trim()) {
        echo '[BuildArchive] BUILD_ARCHIVE_URL is not configured; skip archive.'
        return
    }
    if (!token?.trim()) {
        echo '[BuildArchive] BUILD_ARCHIVE_TOKEN is not configured; skip archive.'
        return
    }

    def result = currentBuild.currentResult ?: 'UNKNOWN'
    def branch = env.GIT_BRANCH ?: env.BRANCH_NAME
    def imageTag = env.DockerImageTag ?: env.DOCKER_IMAGE_TAG
    def buildNumber = env.BUILD_NUMBER
    if (!buildNumber?.trim() || !(buildNumber ==~ /^[1-9][0-9]*$/)) {
        echo "[BuildArchive] Invalid BUILD_NUMBER='${buildNumber}'; skip archive."
        return
    }

    // Treat "-" / empty placeholders as missing (common when GIT_COMMIT unset).
    def cleanCommit = { v ->
        def s = (v == null) ? '' : v.toString().trim()
        if (!s) {
            return null
        }
        def lower = s.toLowerCase()
        if (lower in ['-', '—', '–', '.', 'n/a', 'na', 'null', 'none', 'unknown', 'undefined']) {
            return null
        }
        return s
    }

    def commitId = cleanCommit(config.commitId ?: env.commitId ?: env.COMMIT_ID ?: env.GIT_COMMIT)
    def gitCommit = cleanCommit(env.GIT_COMMIT) ?: commitId
    def commitMsg = config.commitMsg ?: env.commitMsg ?: env.COMMIT_MSG
    def commitAuthor = config.commitAuthor ?: env.commitAuthor ?: env.COMMIT_AUTHOR
    def commitFiles = config.commitFiles ?: env.commitFiles ?: env.COMMIT_FILES
    // Normalize stringy list env (newline / comma separated) into List when possible
    if (commitFiles instanceof String) {
        def text = commitFiles.trim()
        if (text.startsWith('[')) {
            try {
                commitFiles = new groovy.json.JsonSlurper().parseText(text)
            } catch (ignored) {
                commitFiles = text.readLines().findAll { it?.trim() }
            }
        } else if (text) {
            commitFiles = text.replace(',', '\n').readLines().collect { it.trim() }.findAll { it }
        } else {
            commitFiles = null
        }
    }

    // currentBuild.duration is often null/0 while the build is still running (e.g. post always).
    // Prefer explicit config, then duration, then wall-clock since startTimeInMillis.
    def durationMs = config.durationMs
    if (durationMs == null) {
        durationMs = currentBuild.duration
    }
    if (durationMs == null || (durationMs instanceof Number && durationMs.longValue() <= 0L)) {
        try {
            def start = currentBuild.startTimeInMillis
            if (start) {
                durationMs = System.currentTimeMillis() - start
            }
        } catch (ignored) {
            durationMs = null
        }
    }
    if (durationMs != null) {
        try {
            durationMs = durationMs as Long
            if (durationMs < 0L) {
                durationMs = null
            }
        } catch (ignored) {
            durationMs = null
        }
    }

    def payload = [
        jobName: env.JOB_NAME,
        buildId: buildNumber as Integer,
        buildDate: env.BUILD_TIMESTAMP ?: new Date().format("yyyy-MM-dd'T'HH:mm:ssXXX", TimeZone.getTimeZone('Asia/Shanghai')),
        gitRepository: env.GIT_URL ?: env.GIT_REPO,
        gitBranch: branch,
        gitCommit: gitCommit,
        commitMsg: commitMsg,
        commitAuthor: commitAuthor,
        commitId: commitId ?: gitCommit,
        commitFiles: commitFiles,
        dockerRegistry: env.DOCKER_REGISTRY,
        dockerRepository: env.DOCKER_REPOSITORY,
        dockerImageTag: imageTag,
        dockerImageDigest: env.DOCKER_IMAGE_DIGEST,
        buildResult: result,
        buildUrl: env.BUILD_URL,
        durationMs: durationMs
    ]

    def json = groovy.json.JsonOutput.toJson(payload)
    def safeUrl = archiveUrl.replaceAll('/+$', '') + '/api/v1/builds'
    def payloadFile = "build-archive-payload-${env.BUILD_NUMBER}.json"

    try {
        writeFile file: payloadFile, text: json
        // Pass secrets via env so they are not embedded in the shell script literal.
        withEnv([
            "BUILD_ARCHIVE_POST_URL=${safeUrl}",
            "BUILD_ARCHIVE_POST_TOKEN=${token}",
            "BUILD_ARCHIVE_PAYLOAD_FILE=${payloadFile}",
        ]) {
            sh(
                label: 'Archive Jenkins build metadata',
                script: '''
                    set +x
                    curl --fail --silent --show-error --retry 3 --connect-timeout 5 --max-time 15 \
                      -X POST "${BUILD_ARCHIVE_POST_URL}" \
                      -H "Content-Type: application/json" \
                      -H "Authorization: Bearer ${BUILD_ARCHIVE_POST_TOKEN}" \
                      --data-binary @"${BUILD_ARCHIVE_PAYLOAD_FILE}"
                '''
            )
        }
        echo "[BuildArchive] Archived ${env.JOB_NAME} #${env.BUILD_NUMBER} -> ${safeUrl}"
    } catch (err) {
        echo "[BuildArchive] WARNING: archive failed for ${env.JOB_NAME} #${env.BUILD_NUMBER}: ${err}"
    } finally {
        try {
            sh "rm -f '${payloadFile}'"
        } catch (ignored) {
            // best-effort cleanup
        }
    }
}
