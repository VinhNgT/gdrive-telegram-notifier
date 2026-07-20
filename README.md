# gdrive-telegram-notifier

Jenkins Shared Library that uploads build artifacts to Google Drive and sends a
Telegram notification with download links.

## Architecture

This repo is consumed as a **Jenkins Shared Library**. The pipeline orchestration
is a thin Groovy wrapper (`vars/uploadAndNotify.groovy`); all upload and
notification logic is implemented in Python.

```
vars/
  uploadAndNotify.groovy      ← Jenkins DSL step (credentials, Docker, params)
src/
  gdrive_telegram_notifier/
    cli.py                    ← CLI entry point (argparse)
    gdrive.py                 ← Google Drive: resumable upload + retention
    telegram.py               ← Telegram Bot API notification
```

## Pipeline Usage

```groovy
@Library('gdrive-telegram-notifier') _

pipeline {
    // ...
    post {
        success {
            uploadAndNotify(
                files:                  'path/to/artifacts/*.apk',
                gdriveCredentialsId:    'gdrive-service-account-key',
                gdriveFolderId:         env.GDRIVE_FOLDER_ID,
                telegramCredentialsId:  'telegram-bot-token',
                telegramChatId:         env.TELEGRAM_CHAT_ID,
                buildEnv:               params.BUILD_ENV,
                branch:                 params.BRANCH,
                commit:                 'abc1234',
                maxBuilds:              10,    // optional – sync with logRotator
                upload:                 true,  // optional (default: true)
                notify:                 true,  // optional (default: true)
            )
        }
    }
}
```

## Parameters

| Parameter              | Required           | Description                                              |
|------------------------|--------------------|----------------------------------------------------------|
| `upload`               | ❌ (default: `true`) | Upload artifacts to Google Drive                        |
| `notify`               | ❌ (default: `true`) | Send Telegram notification                              |
| `files`                | when `upload`      | Glob pattern for artifact files                           |
| `gdriveCredentialsId`  | when `upload`      | Jenkins credentials ID for the GDrive service account key |
| `gdriveFolderId`       | when `upload`      | Google Drive folder ID (root folder for uploads)          |
| `telegramCredentialsId`| when `notify`      | Jenkins credentials ID for the Telegram bot token         |
| `telegramChatId`       | when `notify`      | Telegram chat ID (negative for groups)                    |
| `buildEnv`             | ✅                 | Build environment (dev/qa/stg/preprod/prod)               |
| `branch`               | ✅                 | Git branch name                                           |
| `commit`               | ✅                 | Git commit hash (short)                                   |
| `maxBuilds`            | ❌                 | Max build folders to keep on Drive; oldest are deleted    |

## Local Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management:

```bash
uv sync                          # Install dependencies
uv run upload-and-notify --help  # Run the CLI
```

## Setup Guide

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Name it something like `jenkins-ci-uploads`
4. Click **Create**

### Step 2: Enable the Google Drive API

1. In your new project, go to **APIs & Services** → **Library**
2. Search for **"Google Drive API"**
3. Click it → click **Enable**

### Step 3: Create a Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **+ Create Credentials** → **Service Account**
3. Name: `jenkins-drive-uploader`
4. Click **Create and Continue**
5. Skip the optional role/access steps → click **Done**
6. Click on the newly created service account email
7. Go to the **Keys** tab → **Add Key** → **Create new key** → **JSON**
8. A `.json` file downloads — **this is your service account key**. Keep it safe.

### Step 4: Set Up the Google Drive Folder

1. In Google Drive, create a folder: `Tendoo Mall Builds`
2. Right-click → **Share**
3. Paste the service account email (e.g. `jenkins-drive-uploader@jenkins-ci-uploads.iam.gserviceaccount.com`) — you'll find this on the service account details page
4. Set permission to **Editor**
5. Click **Send**
6. Open the folder — the folder ID is the last part of the URL:
   ```
   https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXXXXXXXXXX
                                          ↑ this is the folder ID
   ```

### Step 5: Create a Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts — pick a name and username
4. BotFather gives you the **bot token** (looks like `123456789:ABCdef...`)
5. **Add the bot to your group chat**
6. Send a test message in the group (any message)
7. Open this URL in your browser (replace `<TOKEN>` with your bot token):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
8. Find the `"chat"` object → copy the `"id"` value (it's negative for groups, like `-1001234567890`). **This is your chat ID.**

### Step 6: Store Credentials in Jenkins

1. Go to **Jenkins** → **Manage Jenkins** → **Credentials** → **(global)** → **Add Credentials**

2. **Google Drive Service Account Key:**
   - Kind: **Secret file**
   - File: Upload the `.json` key from Step 3
   - ID: `gdrive-service-account-key`
   - Description: `Google Drive Service Account Key`

3. **Telegram Bot Token:**
   - Kind: **Secret text**
   - Secret: Paste the bot token from Step 5
   - ID: `telegram-bot-token`
   - Description: `Telegram Bot Token`

### Step 7: Register the Shared Library in Jenkins

1. Go to **Jenkins** → **Manage Jenkins** → **System** (or **Configure System**)
2. Scroll to **Global Pipeline Libraries**
3. Click **Add**:
   - **Name:** `gdrive-telegram-notifier`
   - **Default version:** `main` (or a tag like `v1.0` for stability)
   - **Allow default version to be overridden:** ✅
   - **Retrieval method:** **Modern SCM** → **Git**
   - **Project Repository:** `<URL of this repo>`
   - **Credentials:** (add if the repo is private)
4. Click **Save**

### Step 8: Update the Pipeline

Add three things to your existing Jenkins pipeline script:

**1. Library import** at the very top (before `pipeline {`):

```diff
+@Library('gdrive-telegram-notifier') _
+
 // Jenkins Pipeline Script — Flutter APK Build
 // ...
 pipeline {
```

**2. `environment` and `options` blocks** inside `pipeline {}`, before `parameters {`.
`MAX_BUILDS_TO_KEEP` is the single source of truth — it drives both Jenkins' `logRotator` and the Drive cleanup:

```diff
 pipeline {
     agent { label 'build' }
 
+    environment {
+        GDRIVE_FOLDER_ID    = '<your-folder-id>'  // from Step 4
+        TELEGRAM_CHAT_ID    = '<your-chat-id>'    // from Step 5
+        MAX_BUILDS_TO_KEEP  = '10'                // single source of truth
+    }
+
+    options {
+        buildDiscarder(logRotator(numToKeepStr: env.MAX_BUILDS_TO_KEEP))
+    }
+
     parameters {
```

**3. `uploadAndNotify()` in the existing `post { success {} }` block:**

```diff
     post {
         success {
             archiveArtifacts artifacts: 'tendoo_mall/build/app/outputs/flutter-apk/tendoo-mall-*.apk',
                              fingerprint: true
+
+            uploadAndNotify(
+                files:                  'tendoo_mall/build/app/outputs/flutter-apk/tendoo-mall-*.apk',
+                gdriveCredentialsId:    'gdrive-service-account-key',
+                gdriveFolderId:         env.GDRIVE_FOLDER_ID,
+                telegramCredentialsId:  'telegram-bot-token',
+                telegramChatId:         env.TELEGRAM_CHAT_ID,
+                buildEnv:               params.BUILD_ENV,
+                branch:                 params.MALL_BRANCH,
+                commit:                 sh(script: 'git -C tendoo_mall rev-parse --short HEAD', returnStdout: true).trim(),
+                maxBuilds:              env.MAX_BUILDS_TO_KEEP.toInteger()
+            )
         }
     }
```

Replace `<your-folder-id>` with the folder ID from Step 4 and `<your-chat-id>` with the chat ID from Step 5.
