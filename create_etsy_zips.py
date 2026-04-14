#!/usr/bin/env python3
"""
create_etsy_zips.py

Creates Etsy-ready ZIP files from 3D-printing jig folders.

Each ZIP is structured as:
    McQForYouDesign_<FolderNameNoSpaces>.zip
    ├── 3MF/          ← .3mf files
    ├── FBX/          ← .fbx files
    ├── OBJ/          ← .obj + .mtl files
    ├── STEP/         ← .step files
    ├── STL/          ← .stl files
    ├── *.pdf         ← PDFs stay at root
    └── *.xcs         ← XCS files stay at root

Configuration is loaded from a .env file in the same directory as this
script.  Required keys:

    JIGS_3DPRINT_DIR     Path to the 3D-printing jigs root
    ZIP_OUTPUT_DIR       Where to write the finished ZIPs (defaults to JIGS_3DPRINT_DIR)
    ZIP_BACKUP_DIR       Where to write pre-run backups (defaults to JIGS_3DPRINT_DIR\\_Backups)
    ZIP_LOG_DIR          Where to write log files (defaults to JIGS_3DPRINT_DIR)
    ZIP_PREFIX           Filename prefix for ZIPs (defaults to McQForYouDesign_)

Usage:
    # Interactive (prompts for single folder vs. all, and backup)
    python create_etsy_zips.py

    # All folders, with backup prompt
    python create_etsy_zips.py --all

    # All folders, skip backup prompt (no backup)
    python create_etsy_zips.py --all --no-backup

    # All folders, skip backup prompt (create backup)
    python create_etsy_zips.py --all --backup

    # Specific folder
    python create_etsy_zips.py --folder "Bamboo Pen"
"""

import argparse
import logging
import os
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
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


JIGS_ROOT: Path = Path(_require_env("JIGS_3DPRINT_DIR"))

# Optional overrides — fall back to sensible defaults relative to JIGS_ROOT.
OUTPUT_DIR: Path = Path(os.getenv("ZIP_OUTPUT_DIR") or JIGS_ROOT)
BACKUP_DIR: Path = Path(os.getenv("ZIP_BACKUP_DIR") or JIGS_ROOT / "_Backups")
LOG_DIR: Path    = Path(os.getenv("ZIP_LOG_DIR")    or JIGS_ROOT)
ZIP_PREFIX: str  = os.getenv("ZIP_PREFIX", "McQForYouDesign_")

# Maps file extension (lowercase, no dot) → subfolder inside ZIP.
# Extensions mapped to None stay at the ZIP root.
EXT_TO_SUBFOLDER: dict[str, str | None] = {
    "3mf":  "3MF",
    "fbx":  "FBX",
    "mtl":  "OBJ",
    "obj":  "OBJ",
    "step": "STEP",
    "stl":  "STL",
    "pdf":  None,   # root
    "xcs":  None,   # root
}

# Extensions we expect to find (used for the "missing types" report).
# XCS is intentionally excluded — it's a bonus file, not a required deliverable.
EXPECTED_EXTENSIONS: set[str] = {"3mf", "fbx", "mtl", "obj", "stl", "pdf", "step"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FolderResult:
    folder_name: str
    zip_path: Path | None = None
    backup_zip_path: Path | None = None
    files_added: list[str] = field(default_factory=list)
    missing_extensions: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def configure_logging() -> logging.Logger:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"create_etsy_zips_{timestamp}.log"

    logger = logging.getLogger("etsy_zip")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"Log file : {log_path}")
    logger.info(f"Run started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    return logger


# ---------------------------------------------------------------------------
# Backup logic
# ---------------------------------------------------------------------------

def backup_folder(folder_path: Path, logger: logging.Logger) -> Path | None:
    """
    Create a flat ZIP backup of *folder_path* (all files, non-recursive) in
    BACKUP_DIR, timestamped so repeated runs never overwrite a prior backup.

    Returns the backup ZIP path on success, or None on failure.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = folder_path.name.replace(" ", "")
    backup_filename = f"BACKUP_{safe_name}_{timestamp}.zip"

    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            f"  ERROR: Could not create backup directory '{BACKUP_DIR}': {e}"
        )
        return None

    backup_path = BACKUP_DIR / backup_filename

    try:
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in sorted(folder_path.iterdir()):
                if file.is_file():
                    zf.write(file, arcname=file.name)
        logger.info(f"  Backup : {backup_filename}")
        return backup_path
    except OSError as e:
        logger.error(f"  ERROR: Backup failed for '{folder_path.name}': {e}")
        return None


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def zip_folder(
    folder_path: Path, logger: logging.Logger, do_backup: bool
) -> FolderResult:
    """
    Process a single jig folder — optionally back it up first, then collect
    eligible files, build the Etsy ZIP with internal subfolders, and report
    any missing expected extension types.
    """
    folder_name = folder_path.name
    safe_name = folder_name.replace(" ", "")
    zip_filename = f"{ZIP_PREFIX}{safe_name}.zip"
    zip_path = OUTPUT_DIR / zip_filename

    result = FolderResult(folder_name=folder_name, zip_path=zip_path)

    logger.info(f"\nFolder : {folder_name}")

    # --- Optional backup ---
    if do_backup:
        backup_path = backup_folder(folder_path, logger)
        result.backup_zip_path = backup_path
    else:
        logger.info("  Backup : skipped")

    logger.info(f"  ZIP    : {zip_filename}")

    # Collect all files (non-recursive) that match accepted extensions.
    eligible: list[Path] = []
    skipped: list[Path] = []

    for file in sorted(folder_path.iterdir()):
        if not file.is_file():
            continue
        ext = file.suffix.lstrip(".").lower()
        if ext in EXT_TO_SUBFOLDER:
            eligible.append(file)
        else:
            skipped.append(file)

    if skipped:
        result.skipped_files = [f.name for f in skipped]
        logger.debug(
            f"  Skipped (unsupported type): {', '.join(result.skipped_files)}"
        )

    if not eligible:
        result.error = "No eligible files found — ZIP not created."
        logger.warning(f"  WARNING: {result.error}")
        return result

    # Identify which expected extension types are absent.
    found_exts: set[str] = {f.suffix.lstrip(".").lower() for f in eligible}
    missing = sorted(EXPECTED_EXTENSIONS - found_exts)
    if missing:
        result.missing_extensions = missing
        logger.info(f"  Missing types: {', '.join(e.upper() for e in missing)}")
    else:
        logger.info("  Missing types: none")

    # Build the ZIP.
    try:
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in eligible:
                ext = file.suffix.lstrip(".").lower()
                subfolder = EXT_TO_SUBFOLDER[ext]
                arc_name = (
                    f"{subfolder}/{file.name}" if subfolder else file.name
                )
                zf.write(file, arcname=arc_name)
                result.files_added.append(arc_name)
                logger.debug(f"    + {arc_name}")

        logger.info(f"  Added {len(result.files_added)} file(s) → {zip_filename}")

    except OSError as e:
        result.error = f"Failed to create ZIP: {e}"
        logger.error(f"  ERROR: {result.error}")

    return result


def process_folders(
    folders: list[Path],
    logger: logging.Logger,
    do_backup: bool,
) -> list[FolderResult]:
    results: list[FolderResult] = []
    for folder in folders:
        result = zip_folder(folder, logger, do_backup)
        results.append(result)
    return results


def write_summary(results: list[FolderResult], logger: logging.Logger) -> None:
    logger.info("\n" + "=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)

    successes    = [r for r in results if r.success]
    failures     = [r for r in results if not r.success]
    with_missing = [r for r in successes if r.missing_extensions]
    backed_up    = [r for r in results if r.backup_zip_path is not None]

    logger.info(f"  Total folders processed : {len(results)}")
    logger.info(f"  Backups created         : {len(backed_up)}")
    logger.info(f"  ZIPs created            : {len(successes)}")
    logger.info(f"  Errors                  : {len(failures)}")
    logger.info(f"  ZIPs with missing types : {len(with_missing)}")

    if with_missing:
        logger.info("\n  Folders with missing file types:")
        for r in with_missing:
            missing_str = ", ".join(e.upper() for e in r.missing_extensions)
            logger.info(f"    • {r.folder_name}: missing {missing_str}")

    if failures:
        logger.info("\n  Folders with errors:")
        for r in failures:
            logger.info(f"    • {r.folder_name}: {r.error}")

    logger.info("\nDone.")


# ---------------------------------------------------------------------------
# CLI / interactive input
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create Etsy-ready ZIP files from 3D-printing jig folders."
    )

    folder_group = parser.add_mutually_exclusive_group()
    folder_group.add_argument(
        "--all",
        action="store_true",
        help="Process every subfolder in the jigs root directory.",
    )
    folder_group.add_argument(
        "--folder",
        metavar="FOLDER_NAME",
        help="Process a single named subfolder (e.g. 'Bamboo Pen').",
    )

    backup_group = parser.add_mutually_exclusive_group()
    backup_group.add_argument(
        "--backup",
        action="store_true",
        default=None,
        help="Create a backup ZIP of each folder before processing (skip prompt).",
    )
    backup_group.add_argument(
        "--no-backup",
        action="store_true",
        default=None,
        help="Skip backup without prompting.",
    )

    return parser.parse_args()


def resolve_folders(args: argparse.Namespace) -> list[Path]:
    """
    Determine which folders to process, prompting interactively if neither
    --all nor --folder was supplied.
    """
    if not JIGS_ROOT.is_dir():
        print(
            f"Error: Jigs root directory not found: {JIGS_ROOT}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.all:
        return _all_subfolders()

    if args.folder:
        return _single_folder(args.folder)

    # Interactive fallback
    print("No arguments provided — running in interactive mode.")
    print()
    print("Options:")
    print("  1) Process ALL subfolders")
    print("  2) Process a specific folder")
    print()

    while True:
        choice = input("Enter 1 or 2: ").strip()
        if choice == "1":
            return _all_subfolders()
        if choice == "2":
            folder_name = input("Folder name: ").strip()
            if folder_name:
                return _single_folder(folder_name)
            print("  Folder name cannot be blank.")
        else:
            print("  Please enter 1 or 2.")


def _all_subfolders() -> list[Path]:
    folders = sorted(entry for entry in JIGS_ROOT.iterdir() if entry.is_dir())
    if not folders:
        print(f"Error: No subfolders found in: {JIGS_ROOT}", file=sys.stderr)
        sys.exit(1)
    return folders


def _single_folder(name: str) -> list[Path]:
    target = JIGS_ROOT / name
    if not target.is_dir():
        print(f"Error: Folder not found: {target}", file=sys.stderr)
        sys.exit(1)
    return [target]


def prompt_backup() -> bool:
    """Interactively ask whether to back up folders before processing."""
    while True:
        raw = input(
            "Create a backup ZIP of each folder before processing? [y/n]: "
        ).strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please enter y or n.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    folders = resolve_folders(args)

    # Resolve backup preference: CLI flags take priority, otherwise prompt.
    if args.backup:
        do_backup = True
    elif args.no_backup:
        do_backup = False
    else:
        do_backup = prompt_backup()

    logger = configure_logging()
    logger.info(f"Jigs root : {JIGS_ROOT}")
    logger.info(f"Output dir: {OUTPUT_DIR}")
    logger.info(f"Folders   : {len(folders)}")
    logger.info(f"Backup    : {'yes' if do_backup else 'no'}")
    if do_backup:
        logger.info(f"Backup dir: {BACKUP_DIR}")

    results = process_folders(folders, logger, do_backup)
    write_summary(results, logger)


if __name__ == "__main__":
    main()
