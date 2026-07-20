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

    # Feature flags
    parser.add_argument(
        "--upload", action=argparse.BooleanOptionalAction, default=True,
        help="Upload artifacts to Google Drive (default: on)",
    )
    parser.add_argument(
        "--notify", action=argparse.BooleanOptionalAction, default=True,
        help="Send Telegram notification (default: on)",
    )

    # Artifact files
    parser.add_argument("--files", help="Glob pattern for artifact files (required when --upload)")

    # Google Drive (required when --upload)
    parser.add_argument("--gdrive-credentials", help="Path to OAuth2 credentials JSON file (from gdrive-auth)")
    parser.add_argument("--gdrive-folder-id", help="Root Google Drive folder ID")

    # Telegram (required when --notify)
    parser.add_argument("--telegram-token", help="Telegram bot token")
    parser.add_argument("--telegram-chat-id", help="Telegram chat ID")

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

    args = parser.parse_args(argv)

    # ── Conditional validation ──────────────────────────────────────────
    if args.upload:
        missing = []
        if not args.files:
            missing.append("--files")
        if not args.gdrive_credentials:
            missing.append("--gdrive-credentials")
        if not args.gdrive_folder_id:
            missing.append("--gdrive-folder-id")
        if missing:
            parser.error(f"--upload requires: {', '.join(missing)}")

    if args.notify:
        missing = []
        if not args.telegram_token:
            missing.append("--telegram-token")
        if not args.telegram_chat_id:
            missing.append("--telegram-chat-id")
        if missing:
            parser.error(f"--notify requires: {', '.join(missing)}")

    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # ── Nothing to do ───────────────────────────────────────────────────
    if not args.upload and not args.notify:
        print("Both --no-upload and --no-notify set — nothing to do")
        return

    # ── Resolve artifact files ──────────────────────────────────────────
    files: list[str] = []
    if args.upload:
        files = sorted(glob.glob(args.files))
        if not files:
            print(f"ERROR: No files matched pattern: {args.files}", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(files)} artifact(s):")
        for f in files:
            print(f"  • {f}")

    # ── Google Drive: upload ────────────────────────────────────────────
    folder_link: str | None = None
    uploaded_files: list[dict[str, str]] = []

    if args.upload:
        service = authenticate(args.gdrive_credentials)

        folder_name = f"Build #{args.build_number} · {args.build_env}"
        folder_id, folder_link = create_build_folder(
            service, parent_id=args.gdrive_folder_id, name=folder_name
        )
        print(f"\nCreated Drive folder: {folder_name}")
        print(f"  {folder_link}")

        for filepath in files:
            file_id, file_link = upload_file(service, folder_id=folder_id, filepath=filepath)
            set_anyone_can_view(service, file_id)
            uploaded_files.append({"path": filepath, "id": file_id, "link": file_link})
            print(f"  Uploaded: {filepath}")
            print(f"    {file_link}")

        # Make the folder itself shareable too
        set_anyone_can_view(service, folder_id)

        # Cleanup old builds
        if args.max_builds is not None:
            cleanup_old_builds(service, parent_id=args.gdrive_folder_id, max_builds=args.max_builds)

    # ── Telegram: send notification ─────────────────────────────────────
    if args.notify:
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
