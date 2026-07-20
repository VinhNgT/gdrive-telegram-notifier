"""Telegram Bot API notification logic."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import requests


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    See: https://core.telegram.org/bots/api#markdownv2-style
    """
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!\\])", r"\\\1", str(text))


def _format_filename(filepath: str) -> str:
    """Extract a human-readable architecture label from the APK filename.

    Example: ``tendoo-mall-dev-arm64-20240101-120000-abc1234.apk`` → ``arm64``
    """
    name = Path(filepath).stem  # drop .apk
    parts = name.split("-")

    # Look for known architecture tokens.
    for arch in ("arm64", "x86_64", "armeabi", "x86"):
        if arch in parts:
            return arch

    # Fallback: return the full filename.
    return name


def _build_message(
    *,
    build_env: str,
    build_number: str,
    build_url: str,
    branch: str,
    commit: str,
    folder_link: str | None = None,
    uploaded_files: list[dict[str, str]] | None = None,
) -> str:
    """Build a MarkdownV2-formatted Telegram message."""
    env = _escape_md(build_env)
    num = _escape_md(build_number)
    br = _escape_md(branch)
    cmt = _escape_md(commit)
    build_url_esc = _escape_md(build_url)

    lines = [
        f"✅ *Tendoo Mall — Build \\#{num}*",
        "",
        f"📋 *Environment:* {env}",
        f"🌿 *Branch:* {br}",
        f"🔖 *Commit:* `{cmt}`",
    ]

    if uploaded_files:
        lines.append("")
        lines.append("📦 *Downloads:*")
        for f in uploaded_files:
            filename = _escape_md(Path(f["path"]).name)
            download_url = _escape_md(f"https://drive.google.com/uc?export=download&id={f['id']}")
            lines.append(f"  • [{filename}]({download_url})")

    if folder_link:
        folder_link_esc = _escape_md(folder_link)
        lines.append(f"📁 Folder — [Open]({folder_link_esc})")

    lines.extend([
        "",
        f"🔗 Jenkins — [Build Page]({build_url_esc})",
    ])

    return "\n".join(lines)


def send_notification(
    *,
    token: str,
    chat_id: str,
    build_env: str,
    build_number: str,
    build_url: str,
    branch: str,
    commit: str,
    folder_link: str | None = None,
    uploaded_files: list[dict[str, str]] | None = None,
) -> None:
    """Send a formatted build notification to a Telegram group chat."""
    text = _build_message(
        build_env=build_env,
        build_number=build_number,
        build_url=build_url,
        branch=branch,
        commit=commit,
        folder_link=folder_link,
        uploaded_files=uploaded_files,
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }

    resp = requests.post(url, json=payload, timeout=30)

    if not resp.ok:
        print(f"ERROR: Telegram API returned {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)
