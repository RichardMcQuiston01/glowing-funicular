#!/usr/bin/env python3
"""
sync_folders.py

Reads subfolder names from a source directory and creates any missing
counterparts in a destination directory.

Configuration is loaded from a .env file in the same directory as this
script.  Required keys:

    SYNC_SRC_DIR   Path to the source folder  (e.g. D:\\3D_Printing\\F2_Jigs)
    SYNC_DEST_DIR  Path to the destination folder (e.g. D:\\Laser\\F2_Jigs)

Usage:
    python sync_folders.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
import os


# ---------------------------------------------------------------------------
# Configuration  (loaded from .env)
# ---------------------------------------------------------------------------

load_dotenv()

_src_raw: str | None = os.getenv("SYNC_SRC_DIR")
_dest_raw: str | None = os.getenv("SYNC_DEST_DIR")

if not _src_raw:
    print("Error: SYNC_SRC_DIR is not set in .env or environment.", file=sys.stderr)
    sys.exit(1)

if not _dest_raw:
    print("Error: SYNC_DEST_DIR is not set in .env or environment.", file=sys.stderr)
    sys.exit(1)

SRC_DIR: Path = Path(_src_raw)
DEST_DIR: Path = Path(_dest_raw)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def sync_folders(src: Path, dest: Path) -> None:
    if not src.is_dir():
        print(f"Error: Source directory not found: {src}", file=sys.stderr)
        sys.exit(1)

    if not dest.is_dir():
        print(f"Error: Destination directory not found: {dest}", file=sys.stderr)
        sys.exit(1)

    src_folders: list[str] = [
        entry.name for entry in src.iterdir() if entry.is_dir()
    ]

    if not src_folders:
        print(f"No subfolders found in source: {src}")
        return

    created_count: int = 0
    skipped_count: int = 0

    for folder_name in sorted(src_folders):
        target = dest / folder_name
        if target.exists():
            print(f"  [skip]   {folder_name}")
            skipped_count += 1
        else:
            try:
                target.mkdir(parents=False, exist_ok=False)
                print(f"  [create] {folder_name}")
                created_count += 1
            except OSError as e:
                print(
                    f"Error: Failed to create '{target}': {e}",
                    file=sys.stderr,
                )

    print(f"\nDone — {created_count} created, {skipped_count} already existed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Source : {SRC_DIR}")
    print(f"Dest   : {DEST_DIR}")
    print()
    sync_folders(SRC_DIR, DEST_DIR)


if __name__ == "__main__":
    main()
