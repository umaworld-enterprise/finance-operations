"""Clear test TT copies from the 'Sunshine Group TT Copies' Shared Drive (go-live, 2026-07-13).

Companion to go_live_wipe.py: the DB rows referencing these files are already
gone; this moves the orphaned test files to the Drive TRASH (recoverable for
~30 days) — it does NOT permanently delete anything.

Safety: resolves the configured GOOGLE_DRIVE_FOLDER_ID and aborts unless its
name is exactly "Sunshine Group TT Copies". Dry run by default.

Credentials come from the environment (run via `railway run` so the backend
service's GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_DRIVE_FOLDER_ID are injected
without ever being written locally).

Run:  railway run python scripts/clear_tt_drive.py           (list files only)
      railway run python scripts/clear_tt_drive.py --trash   (move files to trash)
"""

import json
import os
import sys

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

EXPECTED_NAME = "Sunshine Group TT Copies"
SCOPES = ["https://www.googleapis.com/auth/drive"]


def main() -> None:
    do_trash = "--trash" in sys.argv
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
    if not raw or "..." in raw:
        sys.exit("GOOGLE_SERVICE_ACCOUNT_JSON not in environment (or placeholder) — "
                 "run via: railway run python scripts/clear_tt_drive.py")
    if not folder_id:
        sys.exit("GOOGLE_DRIVE_FOLDER_ID not in environment.")
    creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds)

    # The configured ID may be a Shared Drive root or a folder inside one.
    try:
        name = drive.drives().get(driveId=folder_id).execute().get("name")
    except Exception:
        name = drive.files().get(
            fileId=folder_id, fields="name", supportsAllDrives=True
        ).execute().get("name")
    if name != EXPECTED_NAME:
        sys.exit(f"ABORT: {folder_id} is named {name!r}, "
                 f"expected {EXPECTED_NAME!r} — not touching it.")
    print(f"Target verified: {name} ({folder_id})\n")

    files, token = [], None
    while True:
        resp = drive.files().list(
            corpora="allDrives",
            includeItemsFromAllDrives=True, supportsAllDrives=True,
            q=f"'{folder_id}' in parents and trashed = false "
              "and mimeType != 'application/vnd.google-apps.folder'",
            fields="nextPageToken, files(id, name, size, createdTime)",
            pageSize=1000, pageToken=token,
        ).execute()
        files.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break

    print(f"Files in folder (excluding subfolders): {len(files)}")
    for f in files:
        print(f"  {f['name']}  ({f.get('size', '?')} bytes, created {f['createdTime']})")

    if not files:
        print("\nNothing to clear.")
        return
    if not do_trash:
        print("\nDry run only (no --trash flag). Nothing moved to trash.")
        return

    print("\nMoving to trash...")
    ok = failed = 0
    for f in files:
        try:
            drive.files().update(
                fileId=f["id"], body={"trashed": True}, supportsAllDrives=True
            ).execute()
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"  FAILED {f['name']}: {exc}")
    print(f"\nDone: {ok} trashed, {failed} failed. "
          "Files stay recoverable in the Shared Drive trash for ~30 days.")


if __name__ == "__main__":
    main()
