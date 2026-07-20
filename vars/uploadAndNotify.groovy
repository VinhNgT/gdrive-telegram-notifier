/**
 * uploadAndNotify — Jenkins Shared Library DSL step.
 *
 * Thin Groovy wrapper that handles Jenkins-specific plumbing (credentials,
 * Docker, parameter passing) and delegates all real work to the Python
 * CLI tool {@code upload-and-notify}.
 *
 * Usage in a Jenkinsfile:
 * <pre>
 * {@literal @}Library('gdrive-telegram-notifier') _
 *
 * uploadAndNotify(
 *     files:                  'path/to/artifacts/*.apk',
 *     gdriveCredentialsId:    'gdrive-service-account-key',
 *     gdriveFolderId:         env.GDRIVE_FOLDER_ID,
 *     telegramCredentialsId:  'telegram-bot-token',
 *     telegramChatId:         env.TELEGRAM_CHAT_ID,
 *     buildEnv:               params.BUILD_ENV,
 *     branch:                 params.BRANCH,
 *     commit:                 'abc1234',
 *     maxBuilds:              10,              // optional
 * )
 * </pre>
 */
def call(Map config) {
    // Validate required params
    def required = ['files', 'gdriveCredentialsId', 'gdriveFolderId',
                    'telegramCredentialsId', 'telegramChatId',
                    'buildEnv', 'branch', 'commit']
    required.each { key ->
        if (!config.containsKey(key)) {
            error "uploadAndNotify: missing required parameter '${key}'"
        }
    }

    def libPath = library.gdrive-telegram-notifier.path

    // Optional: max builds to keep on Google Drive (mirrors Jenkins' logRotator)
    def maxBuildsArg = config.maxBuilds ? "--max-builds ${config.maxBuilds}" : ''

    docker.image('python:3.12-slim').inside('-u 0:0') {
        // Install the project and its dependencies from pyproject.toml
        sh "pip install --no-cache-dir -q ${libPath}"

        withCredentials([
            file(credentialsId: config.gdriveCredentialsId, variable: 'GDRIVE_SA_KEY'),
            string(credentialsId: config.telegramCredentialsId, variable: 'TELEGRAM_TOKEN')
        ]) {
            sh """
                upload-and-notify \\
                    --files '${config.files}' \\
                    --gdrive-key "\$GDRIVE_SA_KEY" \\
                    --gdrive-folder-id '${config.gdriveFolderId}' \\
                    --telegram-token "\$TELEGRAM_TOKEN" \\
                    --telegram-chat-id '${config.telegramChatId}' \\
                    --build-env '${config.buildEnv}' \\
                    --build-number "\${BUILD_NUMBER}" \\
                    --build-url "\${BUILD_URL}" \\
                    --branch '${config.branch}' \\
                    --commit '${config.commit}' \\
                    ${maxBuildsArg}
            """
        }
    }
}
