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
 *     upload:                 true,            // optional (default: true)
 *     notify:                 true,            // optional (default: true)
 * )
 * </pre>
 */
def call(Map config) {
    def doUpload = config.upload != false  // default true
    def doNotify = config.notify != false  // default true

    if (!doUpload && !doNotify) {
        echo 'uploadAndNotify: both upload and notify are disabled — nothing to do'
        return
    }

    // Validate required params based on flags
    def required = ['buildEnv', 'branch', 'commit']
    if (doUpload) {
        required += ['files', 'gdriveCredentialsId', 'gdriveFolderId']
    }
    if (doNotify) {
        required += ['telegramCredentialsId', 'telegramChatId']
    }
    required.each { key ->
        if (!config.containsKey(key)) {
            error "uploadAndNotify: parameter '${key}' is required when ${doUpload ? 'upload' : ''}${doUpload && doNotify ? ' and ' : ''}${doNotify ? 'notify' : ''} is enabled"
        }
    }

    // The shared library is checked out on the Jenkins controller, not the
    // agent.  To get the Python package onto the agent we pip-install
    // directly from the GitHub tarball URL (no git binary needed).
    def repoUrl = config.repoUrl ?: 'https://github.com/VinhNgT/gdrive-telegram-notifier'
    def repoBranch = config.repoBranch ?: 'main'

    // Build optional CLI flags
    def maxBuildsArg = config.maxBuilds ? "--max-builds ${config.maxBuilds}" : ''
    def uploadFlag   = doUpload ? '--upload' : '--no-upload'
    def notifyFlag   = doNotify ? '--notify' : '--no-notify'
    def filesArg     = config.files ? "--files '${config.files}'" : ''

    docker.image('python:3.12-slim').inside('-u 0:0') {
        // Install the Python package + dependencies from the GitHub tarball
        sh "pip install --no-cache-dir -q '${repoUrl}/archive/${repoBranch}.tar.gz'"

        // Build the credentials bindings list based on flags
        def credBindings = []
        if (doUpload) {
            credBindings << file(credentialsId: config.gdriveCredentialsId, variable: 'GDRIVE_SA_KEY')
        }
        if (doNotify) {
            credBindings << string(credentialsId: config.telegramCredentialsId, variable: 'TELEGRAM_TOKEN')
        }

        withCredentials(credBindings) {
            // Build the CLI command dynamically
            def gdriveArgs = doUpload ? """\\
                    --gdrive-key "\$GDRIVE_SA_KEY" \\
                    --gdrive-folder-id '${config.gdriveFolderId}'""" : ''
            def telegramArgs = doNotify ? """\\
                    --telegram-token "\$TELEGRAM_TOKEN" \\
                    --telegram-chat-id '${config.telegramChatId}'""" : ''

            sh """
                upload-and-notify \\
                    ${uploadFlag} ${notifyFlag} \\
                    ${filesArg} \\
                    ${gdriveArgs} \\
                    ${telegramArgs} \\
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
