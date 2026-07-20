"""Google Drive upload and build-folder retention logic."""

from __future__ import annotations

import os
import re
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.http import MediaFileUpload

_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Chunk size for resumable uploads (10 MB).  The Google API client
# library requires multiples of 256 KB.  10 MB strikes a good balance
# between retry cost and request overhead for ~500 MB APKs.
_CHUNK_SIZE = 10 * 1024 * 1024

# Regex to extract the build number from folder names like "Build #42 · dev"
_BUILD_FOLDER_RE = re.compile(r"^Build #(\d+)\s*·")


# ── Authentication ──────────────────────────────────────────────────────


def authenticate(key_path: str) -> Resource:
    """Return an authorised Google Drive API service instance."""
    creds = Credentials.from_service_account_file(key_path, scopes=_SCOPES)
    return build("drive", "v3", credentials=creds)


# ── Folder operations ───────────────────────────────────────────────────


def create_build_folder(
    service: Resource, *, parent_id: str, name: str
) -> tuple[str, str]:
    """Create a subfolder under *parent_id* and return *(folder_id, web_link)*."""
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = (
        service.files()
        .create(body=metadata, fields="id, webViewLink")
        .execute()
    )
    return folder["id"], folder["webViewLink"]


# ── File upload ─────────────────────────────────────────────────────────


def upload_file(
    service: Resource, *, folder_id: str, filepath: str
) -> tuple[str, str]:
    """Upload a single file using resumable upload. Returns *(file_id, web_link)*."""
    filename = Path(filepath).name
    file_size = os.path.getsize(filepath)

    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaFileUpload(
        filepath,
        mimetype="application/vnd.android.package-archive",
        chunksize=_CHUNK_SIZE,
        resumable=True,
    )

    request = service.files().create(
        body=metadata, media_body=media, fields="id, webViewLink"
    )

    # Resumable upload loop — prints progress for large files.
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            uploaded_mb = status.resumable_progress / (1024 * 1024)
            total_mb = file_size / (1024 * 1024)
            print(f"    {filename}: {pct}% ({uploaded_mb:.0f}/{total_mb:.0f} MB)")

    return response["id"], response["webViewLink"]


# ── Sharing ─────────────────────────────────────────────────────────────


def set_anyone_can_view(service: Resource, file_id: str) -> None:
    """Grant 'anyone with the link can view' permission."""
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
        fields="id",
    ).execute()


# ── Build retention ─────────────────────────────────────────────────────


def cleanup_old_builds(
    service: Resource, *, parent_id: str, max_builds: int
) -> None:
    """Delete the oldest build folders beyond *max_builds*.

    Only folders whose names match ``Build #<N> · <env>`` are considered.
    Folders are sorted by build number (descending); those beyond the
    limit are permanently deleted (including all contents).
    """
    if max_builds <= 0:
        return

    # List all subfolders in the root folder.
    query = (
        f"'{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    results = (
        service.files()
        .list(q=query, fields="files(id, name)", pageSize=1000)
        .execute()
    )
    folders = results.get("files", [])

    # Filter to build folders and parse their build numbers.
    build_folders: list[tuple[int, str, str]] = []  # (build_num, id, name)
    for folder in folders:
        match = _BUILD_FOLDER_RE.match(folder["name"])
        if match:
            build_num = int(match.group(1))
            build_folders.append((build_num, folder["id"], folder["name"]))

    # Sort by build number descending — keep the newest.
    build_folders.sort(key=lambda x: x[0], reverse=True)

    # Delete folders beyond the limit.
    to_delete = build_folders[max_builds:]
    for build_num, folder_id, folder_name in to_delete:
        service.files().delete(fileId=folder_id).execute()
        print(f"  Deleted old build folder: {folder_name}")

    if to_delete:
        print(f"  Retained {min(len(build_folders), max_builds)} build(s), deleted {len(to_delete)}")
