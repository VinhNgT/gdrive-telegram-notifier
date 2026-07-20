"""One-time OAuth2 authorization flow for Google Drive.

Run this locally to generate a credentials file that can be uploaded
to Jenkins as a Secret file credential.

Usage:
    uv run gdrive-auth --client-secrets /path/to/client_secret.json

The client secrets JSON file is downloaded from the Google Cloud Console
after creating an OAuth2 "Desktop app" credential.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_OUTPUT_FILE = "gdrive-credentials.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gdrive-auth",
        description="Authorize with Google Drive and save a credentials file for CI.",
    )
    parser.add_argument(
        "--client-secrets",
        required=True,
        help="Path to the OAuth2 client secrets JSON file (downloaded from Google Cloud Console)",
    )
    parser.add_argument(
        "--output",
        default=_OUTPUT_FILE,
        help=f"Output file for the credentials (default: {_OUTPUT_FILE})",
    )
    args = parser.parse_args()

    if not Path(args.client_secrets).exists():
        print(f"ERROR: File not found: {args.client_secrets}", file=sys.stderr)
        sys.exit(1)

    print("Opening browser for Google authorization...")
    print("Please sign in and grant Google Drive access.\n")

    flow = InstalledAppFlow.from_client_secrets_file(args.client_secrets, scopes=_SCOPES)
    creds = flow.run_local_server(port=0)

    # Save only what's needed for CI: client_id, client_secret, refresh_token
    credentials = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(credentials, indent=2) + "\n")

    print(f"\n✓ Credentials saved to: {output_path.resolve()}")
    print("\nNext steps:")
    print("  1. Upload this file to Jenkins as a 'Secret file' credential")
    print("     • ID: gdrive-oauth-credentials")
    print("  2. Delete the file from your local machine after uploading")
