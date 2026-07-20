"""CLI entry point for upload-and-notify."""

from __future__ import annotations

import argparse
import glob
import sys

from gdrive_telegram_notifier.gdrive import (
    authenticate,
    cleanup_old_builds,
    create_build_folder,
    set_anyone_can_view,
    upload_file,
)
from gdrive_telegram_notifier.telegram import send_notification


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="upload-and-notify",
        description="Upload build artifacts to Google Drive and send a Telegram notification.",
    )

    # Google Drive
    parser.add_argument("--files", required=True, help="Glob pattern for artifact files")
    parser.add_argument("--gdrive-key", required=True, help="Path to service account JSON key file")
    parser.add_argument("--gdrive-folder-id", required=True, help="Root Google Drive folder ID")

    # Telegram
    parser.add_argument("--telegram-token", required=True, help="Telegram bot token")
    parser.add_argument("--telegram-chat-id", required=True, help="Telegram chat ID")

    # Build metadata
    parser.add_argument("--build-env", required=True, help="Build environment (dev/qa/stg/preprod/prod)")
    parser.add_argument("--build-number", required=True, help="Jenkins build number")
    parser.add_argument("--build-url", required=True, help="Jenkins build URL")
    parser.add_argument("--branch", required=True, help="Git branch name")
    parser.add_argument("--commit", required=True, help="Git commit hash (short)")

    # Retention
    parser.add_argument(
        "--max-builds",
        type=int,
        default=None,
        help="Max build folders to keep on Drive; oldest beyond this limit are deleted",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # ── Resolve artifact files ──────────────────────────────────────────
    files = sorted(glob.glob(args.files))
    if not files:
        print(f"ERROR: No files matched pattern: {args.files}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} artifact(s):")
    for f in files:
        print(f"  • {f}")

    # ── Google Drive: authenticate ──────────────────────────────────────
    service = authenticate(args.gdrive_key)

    # ── Google Drive: create build folder ───────────────────────────────
    folder_name = f"Build #{args.build_number} · {args.build_env}"
    folder_id, folder_link = create_build_folder(
        service, parent_id=args.gdrive_folder_id, name=folder_name
    )
    print(f"\nCreated Drive folder: {folder_name}")
    print(f"  {folder_link}")

    # ── Google Drive: upload each file ──────────────────────────────────
    uploaded_files: list[dict[str, str]] = []
    for filepath in files:
        file_id, file_link = upload_file(service, folder_id=folder_id, filepath=filepath)
        set_anyone_can_view(service, file_id)
        uploaded_files.append({"path": filepath, "id": file_id, "link": file_link})
        print(f"  Uploaded: {filepath}")
        print(f"    {file_link}")

    # Make the folder itself shareable too
    set_anyone_can_view(service, folder_id)

    # ── Google Drive: cleanup old builds ────────────────────────────────
    if args.max_builds is not None:
        cleanup_old_builds(service, parent_id=args.gdrive_folder_id, max_builds=args.max_builds)

    # ── Telegram: send notification ─────────────────────────────────────
    send_notification(
        token=args.telegram_token,
        chat_id=args.telegram_chat_id,
        build_env=args.build_env,
        build_number=args.build_number,
        build_url=args.build_url,
        branch=args.branch,
        commit=args.commit,
        folder_link=folder_link,
        uploaded_files=uploaded_files,
    )
    print("\nTelegram notification sent ✓")
