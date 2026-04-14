#!/usr/bin/env python3
"""
sync_digital_addin_files.py

Copies thank-you PDF(s) from the digital download add-in folder to every
subfolder (or a specific subfolder) in the 3D-printing and/or laser jig
directories prior to zipping for Etsy.

Configuration is loaded from a .env file in the same directory as this
script.  Required keys:

    ADDIN_SOURCE_DIR     Path to the folder containing the thank-you PDF(s)
    JIGS_3DPRINT_DIR     Path to the 3D-printing jigs root
    JIGS_LASER_DIR       Path to the laser jigs root

Usage:
    # Interactive mode (prompts for all inputs)
    python sync_digital_addin_files.py

    # Fully specified via CLI
    python sync_digital_addin_files.py --jig-type 3DPRINT_JIGS
    python sync_digital_addin_files.py --jig-type LASER_JIGS --folder "Bamboo Pen"
    python sync_digital_addin_files.py --jig-type BOTH_JIGS
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Configuration  (loaded from .env)
# ---------------------------------------------------------------------------

load_dotenv()


def _require_env(key: str) -> str:
    """Return the value of *key* from the environment, or exit with an error."""
    value: str | None = os.getenv(key)
    if not value:
        print(
            f"Error: {key} is not set in .env or environment.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


ADDIN_SOURCE_DIR: Path = Path(_require_env("ADDIN_SOURCE_DIR"))

JIG_DIRS: dict[str, Path] = {
    "3DPRINT_JIGS": Path(_require_env("JIGS_3DPRINT_DIR")),
    "LASER_JIGS":   Path(_require_env("JIGS_LASER_DIR")),
}

VALID_JIG_TYPES: list[str] = ["3DPRINT_JIGS", "LASER_JIGS", "BOTH_JIGS"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def collect_pdfs(source_dir: Path) -> list[Path]:
    """Return all PDF files found in *source_dir* (non-recursive)."""
    if not source_dir.is_dir():
        print(
            f"Error: Digital download source directory not found: {source_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    pdfs = sorted(source_dir.glob("*.pdf"))
    if not pdfs:
        print(f"Error: No PDF files found in: {source_dir}", file=sys.stderr)
        sys.exit(1)

    return pdfs


def resolve_target_dirs(jig_type: str, specific_folder: str | None) -> list[Path]:
    """
    Return the list of target directories to copy PDFs into.

    - If *specific_folder* is given, return only that subfolder inside each
      resolved jig root.
    - Otherwise, return every immediate subdirectory of each jig root.
    """
    jig_keys: list[str] = (
        list(JIG_DIRS.keys()) if jig_type == "BOTH_JIGS" else [jig_type]
    )

    target_dirs: list[Path] = []

    for key in jig_keys:
        root = JIG_DIRS[key]

        if not root.is_dir():
            print(
                f"Error: Jig root directory not found: {root}",
                file=sys.stderr,
            )
            sys.exit(1)

        if specific_folder:
            target = root / specific_folder
            if not target.is_dir():
                print(
                    f"Error: Specified folder does not exist: {target}",
                    file=sys.stderr,
                )
                sys.exit(1)
            target_dirs.append(target)
        else:
            subfolders = sorted(
                entry for entry in root.iterdir() if entry.is_dir()
            )
            if not subfolders:
                print(f"Warning: No subfolders found in: {root}")
            target_dirs.extend(subfolders)

    return target_dirs


def copy_pdfs_to_dir(pdfs: list[Path], target_dir: Path) -> tuple[int, int]:
    """
    Copy each PDF into *target_dir*.

    Returns:
        (copied_count, updated_count) — updated means the file already existed
        and was overwritten to ensure the latest version is always present.
    """
    copied: int = 0
    updated: int = 0

    for pdf in pdfs:
        destination = target_dir / pdf.name
        already_exists = destination.exists()

        try:
            shutil.copy2(pdf, destination)
            if already_exists:
                print(f"    [update] {pdf.name}")
                updated += 1
            else:
                print(f"    [copy]   {pdf.name}")
                copied += 1
        except OSError as e:
            print(
                f"Error: Failed to copy '{pdf.name}' to '{target_dir}': {e}",
                file=sys.stderr,
            )

    return copied, updated


# ---------------------------------------------------------------------------
# CLI / interactive input
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy digital add-in PDFs to jig folders for Etsy zipping."
    )
    parser.add_argument(
        "--jig-type",
        choices=VALID_JIG_TYPES,
        help="Which jig folder(s) to target: 3DPRINT_JIGS, LASER_JIGS, or BOTH_JIGS.",
    )
    parser.add_argument(
        "--folder",
        metavar="FOLDER_NAME",
        help=(
            "Optional: specific subfolder name to target (e.g. 'Bamboo Pen'). "
            "If omitted, all subfolders are targeted."
        ),
    )
    return parser.parse_args()


def prompt_jig_type() -> str:
    """Interactively prompt the user to choose a jig type."""
    options = ", ".join(VALID_JIG_TYPES)
    while True:
        raw = input(f"Jig type [{options}]: ").strip().upper()
        if raw in VALID_JIG_TYPES:
            return raw
        print(f"  Invalid choice. Please enter one of: {options}")


def prompt_specific_folder() -> str | None:
    """Interactively prompt for an optional specific subfolder."""
    raw = input(
        "Specific folder name (leave blank to sync all subfolders): "
    ).strip()
    return raw if raw else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    jig_type: str = args.jig_type if args.jig_type else prompt_jig_type()
    specific_folder: str | None = (
        args.folder if args.folder is not None else prompt_specific_folder()
    )

    print()
    print(f"Source  : {ADDIN_SOURCE_DIR}")
    print(f"Jig type: {jig_type}")
    print(f"Folder  : {specific_folder if specific_folder else '(all subfolders)'}")
    print()

    pdfs = collect_pdfs(ADDIN_SOURCE_DIR)
    print(f"Found {len(pdfs)} PDF(s) to copy: {[p.name for p in pdfs]}")
    print()

    target_dirs = resolve_target_dirs(jig_type, specific_folder)

    if not target_dirs:
        print("No target directories resolved. Nothing to do.")
        sys.exit(0)

    total_copied: int = 0
    total_updated: int = 0

    for target_dir in target_dirs:
        print(f"  → {target_dir}")
        copied, updated = copy_pdfs_to_dir(pdfs, target_dir)
        total_copied += copied
        total_updated += updated

    print()
    print(
        f"Done — {total_copied} new file(s) copied, "
        f"{total_updated} existing file(s) updated, "
        f"across {len(target_dirs)} folder(s)."
    )


if __name__ == "__main__":
    main()
