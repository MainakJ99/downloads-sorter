#!/usr/bin/env python3
"""
downloads_sorter.py - Sort files in your Downloads folder into subfolders.

Sorts by file extension category, by date, or both, either once or
continuously (watch mode, implemented by polling).

Safety rules (folders are never broken apart):
  * Only loose files are sorted. Any folder you created or extracted (games,
    projects, unzipped archives, ...) is left completely untouched.
  * --recursive only re-sorts inside the sorter's OWN folders (Images, Documents,
    ..., Code, Code/Reading, Other, and date folders such as 2026-11). Any other
    subfolder inside them is treated as a unit and skipped.
  * Hidden/system files (desktop.ini, Thumbs.db, .DS_Store, ...) are never moved.
  * Files still downloading (.crdownload, .part, or a placeholder next to one)
    are skipped.
  * Nothing is ever overwritten; name clashes become "name (1).ext".
  * Every real run writes a move log to <source>/.sorter_logs/, and --undo
    reverses the most recent run (or a specific log).

Examples:
    python downloads_sorter.py                      # sort once by type
    python downloads_sorter.py --dry-run            # preview only
    python downloads_sorter.py -m date              # Downloads/2026-11/file.pdf
    python downloads_sorter.py -m both              # Downloads/Documents/2026-11/file.pdf
    python downloads_sorter.py --watch -i 10        # keep watching, poll every 10s
    python downloads_sorter.py -m both -r --remove-empty   # re-organize an already sorted folder
    python downloads_sorter.py --undo               # put back everything the last run moved
"""

import argparse
import errno
import json
import os
import shutil
import stat
import sys
import time
from datetime import datetime

# Extension -> category folder. Anything not listed goes to "Other".
CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".tiff", ".ico"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".epub", ".pages"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods", ".numbers"},
    "Presentations": {".ppt", ".pptx", ".odp", ".key"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage", ".apk"},
    "Code": {".py", ".js", ".ts", ".css", ".json", ".xml", ".java", ".c", ".cpp",
             ".h", ".go", ".rs", ".r", ".rmd", ".sh", ".yaml", ".yml", ".sql", ".ipynb"},
}
OTHER = "Other"
MANAGED_CATEGORIES = set(CATEGORIES) | {OTHER}

# HTML pages are reading material, so they go in Code/Reading rather than next to source files.
READING_DIR = "Reading"
NESTED_CATEGORIES = {
    ".html": ("Code", READING_DIR),
    ".htm": ("Code", READING_DIR),
}

# Browsers use these while a download is still in progress - never touch them.
PARTIAL_EXTENSIONS = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload"}

# OS bookkeeping files that belong to the folder they sit in.
SYSTEM_FILES = {"desktop.ini", "thumbs.db", "ehthumbs.db", ".ds_store", "icon\r", ".localized"}

LOG_DIR_NAME = ".sorter_logs"

# Reverse lookup for speed: ".pdf" -> "Documents"
EXT_TO_CATEGORY = {ext: cat for cat, exts in CATEGORIES.items() for ext in exts}

_WIN_HIDDEN = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 2) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 4)


def log(message, quiet=False):
    if not quiet:
        print(f"[{datetime.now():%H:%M:%S}] {message}")


def get_category(filename):
    """Return the category folder name for a file based on its extension."""
    return category_parts(filename)[0]


def category_parts(filename):
    """Folders under the source for this file, before any date folders."""
    ext = os.path.splitext(filename)[1].lower()
    nested = NESTED_CATEGORIES.get(ext)
    if nested:
        return list(nested)
    if not ext:
        return [OTHER]
    return [EXT_TO_CATEGORY.get(ext, OTHER)]


def get_file_date(path, date_source):
    """
    Return a datetime for the file.

    'created'  -> true creation time where the OS exposes it (Windows, macOS);
                  falls back to modified time on Linux, where it isn't available.
    'modified' -> last modification time.
    """
    st = os.stat(path)
    if date_source == "modified":
        ts = st.st_mtime
    else:
        # macOS/BSD (and Windows on Python 3.12+) expose st_birthtime;
        # on older Pythons Windows st_ctime is the creation time.
        ts = getattr(st, "st_birthtime", None)
        if ts is None:
            ts = st.st_ctime if sys.platform.startswith("win") else st.st_mtime
    return datetime.fromtimestamp(ts)


# --------------------------------------------------------------------------- folders

def matches_date_format(rel_parts, date_format):
    """
    True if rel_parts (e.g. ['2026-11']) is a full or leading part of a folder
    produced by date_format. Handles formats with separators such as '%Y/%m'.
    """
    fmt_parts = date_format.replace("\\", "/").split("/")
    if not rel_parts or len(rel_parts) > len(fmt_parts):
        return False
    try:
        datetime.strptime("/".join(rel_parts), "/".join(fmt_parts[:len(rel_parts)]))
        return True
    except ValueError:
        return False


def is_managed_dir(source, dirpath, date_format):
    """
    Is this one of the sorter's own folders (safe to re-sort and clean up)?
      <source>/<Category>                       e.g. Documents
      <source>/<Category>/<date parts>          e.g. Documents/2026-11
      <source>/Code/Reading                     HTML reading material
      <source>/Code/Reading/<date parts>        e.g. Code/Reading/2026-11
      <source>/<date parts>                     e.g. 2026-11
    Anything else - a game, a project, an extracted archive, or a folder you made
    inside a category folder - is not managed and is never entered.
    """
    rel = os.path.relpath(dirpath, source)
    if rel in (".", "") or rel.startswith(".."):
        return False
    parts = rel.split(os.sep)
    if any(p.startswith(".") for p in parts):
        return False
    if parts[0] not in MANAGED_CATEGORIES:
        return matches_date_format(parts, date_format)
    rest = parts[1:]
    if rest and parts[0] == "Code" and rest[0] == READING_DIR:
        rest = rest[1:]
    return not rest or matches_date_format(rest, date_format)


def is_hidden_or_system(path, filename):
    if filename.startswith(".") or filename.lower() in SYSTEM_FILES:
        return True
    try:
        attrs = getattr(os.stat(path, follow_symlinks=False), "st_file_attributes", 0)
    except OSError:
        return True
    return bool(attrs & _WIN_HIDDEN)


def has_partial_companion(path):
    """Firefox/Chrome may create 'file.pdf' as a placeholder next to 'file.pdf.part'."""
    return any(os.path.exists(path + ext) for ext in PARTIAL_EXTENSIONS)


def should_skip(path, filename, settle_seconds, protected):
    """Skip directories, hidden/system files, partial downloads, and files still being written."""
    if os.path.normcase(os.path.abspath(path)) in protected:
        return True
    if not os.path.isfile(path) or os.path.islink(path):
        return True
    if is_hidden_or_system(path, filename):
        return True
    if os.path.splitext(filename)[1].lower() in PARTIAL_EXTENSIONS:
        return True
    if has_partial_companion(path):
        return True
    try:
        if time.time() - os.stat(path).st_mtime < settle_seconds:
            return True  # modified very recently; probably still downloading
    except OSError:
        return True
    return False


def build_target_dir(source, path, filename, mode, date_format, date_source):
    parts = []
    if mode in ("ext", "both"):
        parts.extend(category_parts(filename))
    if mode in ("date", "both"):
        parts.append(get_file_date(path, date_source).strftime(date_format))
    return os.path.join(source, *parts)


def list_files(args):
    """
    Return (directory, filename) pairs.

    Always: loose files directly in the source folder.
    With --recursive: also files inside the sorter's own folders (see is_managed_dir).
    Other folders are never entered, so their structure can't be broken.
    """
    found = [(args.source, name) for name in sorted(os.listdir(args.source))]
    if not args.recursive:
        return found
    for name in sorted(os.listdir(args.source)):
        top = os.path.join(args.source, name)
        if not os.path.isdir(top) or os.path.islink(top):
            continue
        if not is_managed_dir(args.source, top, args.date_format):
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = sorted(
                d for d in dirnames
                if not os.path.islink(os.path.join(dirpath, d))
                and is_managed_dir(args.source, os.path.join(dirpath, d), args.date_format)
            )
            found.extend((dirpath, f) for f in sorted(filenames))
    return found


def remove_empty_dirs(source, date_format, quiet=False):
    """Delete the sorter's own folders that are now empty. Never touches any other folder."""
    for name in os.listdir(source):
        top = os.path.join(source, name)
        if not os.path.isdir(top) or not is_managed_dir(source, top, date_format):
            continue
        for dirpath, _dirs, _files in os.walk(top, topdown=False):
            if not is_managed_dir(source, dirpath, date_format):
                continue
            try:
                os.rmdir(dirpath)  # only succeeds when the folder is empty
                log(f"Removed empty folder {os.path.relpath(dirpath, source)}", quiet)
            except OSError:
                pass


# --------------------------------------------------------------------------- moving

def unique_destination(dest_dir, filename, reserved=()):
    """Avoid overwriting: 'report.pdf' -> 'report (1).pdf', 'report (2).pdf', ..."""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    counter = 1
    while os.path.lexists(candidate) or os.path.normcase(candidate) in reserved:
        candidate = os.path.join(dest_dir, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


def safe_move(src, dst):
    """Move without ever overwriting an existing file (even if one appears mid-run)."""
    if os.path.lexists(dst):
        raise FileExistsError(f"destination already exists: {dst}")
    try:
        if os.name == "nt":
            os.rename(src, dst)  # Windows rename refuses to overwrite
        else:
            os.link(src, dst)    # fails if dst exists (no overwrite race)
            os.unlink(src)
        return
    except OSError as exc:
        cross_device = exc.errno == errno.EXDEV or getattr(exc, "winerror", None) == 17
        if not cross_device:
            # e.g. the file is locked by a torrent client or still open in an app.
            # Do NOT fall back to copying: that leaves a duplicate behind when the
            # original can't be deleted.
            raise
    # different drive/filesystem: copy, then delete the original; undo the copy on failure
    shutil.copy2(src, dst)
    try:
        os.unlink(src)
    except OSError:
        os.unlink(dst)
        raise


class MoveLog:
    """Append-only JSONL record of every move, so a run can be undone."""

    def __init__(self, source):
        self.path = None
        self.source = source

    def record(self, src, dst):
        if self.path is None:
            log_dir = os.path.join(self.source, LOG_DIR_NAME)
            os.makedirs(log_dir, exist_ok=True)
            self.path = os.path.join(log_dir, f"sort-{datetime.now():%Y%m%d-%H%M%S}.jsonl")
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"src": src, "dst": dst, "time": time.time()}) + "\n")


def sort_folder(args, move_log, protected):
    """Run one sorting pass over the source folder. Returns moved count."""
    moved = 0
    reserved = set()  # destinations planned in this pass (makes dry-run numbering accurate)
    try:
        entries = list_files(args)
    except OSError as exc:
        log(f"Cannot read {args.source}: {exc}")
        return 0

    for directory, filename in entries:
        path = os.path.join(directory, filename)
        if should_skip(path, filename, args.settle, protected):
            continue

        try:
            target_dir = build_target_dir(
                args.source, path, filename, args.mode, args.date_format, args.date_source
            )
            if os.path.normcase(os.path.abspath(target_dir)) == os.path.normcase(os.path.abspath(directory)):
                continue  # already where it belongs
            if os.path.exists(target_dir) and not os.path.isdir(target_dir):
                log(f"Could not move {filename}: '{os.path.relpath(target_dir, args.source)}' "
                    f"exists and is a file, not a folder")
                continue
            destination = unique_destination(target_dir, filename, reserved)
            reserved.add(os.path.normcase(destination))
            rel = os.path.relpath(destination, args.source)

            if args.dry_run:
                log(f"[dry-run] {os.path.relpath(path, args.source)} -> {rel}")
            else:
                os.makedirs(target_dir, exist_ok=True)
                safe_move(path, destination)
                move_log.record(path, destination)
                log(f"Moved {os.path.relpath(path, args.source)} -> {rel}", args.quiet)
            moved += 1
        except (OSError, shutil.Error) as exc:
            log(f"Could not move {filename}: {exc}")

    if args.remove_empty and not args.dry_run:
        remove_empty_dirs(args.source, args.date_format, args.quiet)
    return moved


# --------------------------------------------------------------------------- undo

def latest_log(source):
    log_dir = os.path.join(source, LOG_DIR_NAME)
    try:
        logs = sorted(f for f in os.listdir(log_dir) if f.startswith("sort-") and f.endswith(".jsonl"))
    except OSError:
        return None
    return os.path.join(log_dir, logs[-1]) if logs else None


def undo(args):
    log_path = args.undo if args.undo != "latest" else latest_log(args.source)
    if not log_path or not os.path.isfile(log_path):
        log("No move log found to undo.")
        return 0
    with open(log_path, encoding="utf-8") as fh:
        moves = [json.loads(line) for line in fh if line.strip()]
    restored = 0
    for mv in reversed(moves):
        src, dst = mv["src"], mv["dst"]
        if not os.path.exists(dst):
            log(f"Skip (no longer there): {dst}")
            continue
        if os.path.lexists(src):
            log(f"Skip (something already at original place): {src}")
            continue
        if args.dry_run:
            log(f"[dry-run] {os.path.relpath(dst, args.source)} -> {os.path.relpath(src, args.source)}")
        else:
            os.makedirs(os.path.dirname(src), exist_ok=True)
            safe_move(dst, src)
            log(f"Restored {os.path.relpath(src, args.source)}", args.quiet)
        restored += 1
    if not args.dry_run:
        remove_empty_dirs(args.source, args.date_format, args.quiet)
        os.replace(log_path, log_path + ".undone")
    return restored


# --------------------------------------------------------------------------- cli

def parse_args():
    parser = argparse.ArgumentParser(
        description="Sort files in your Downloads folder by extension and/or date.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Tip: run with --dry-run first to preview what would happen.",
    )
    parser.add_argument(
        "-s", "--source",
        default=os.path.join(os.path.expanduser("~"), "Downloads"),
        help="folder to sort (default: ~/Downloads)",
    )
    parser.add_argument(
        "-m", "--mode", choices=["ext", "date", "both"], default="ext",
        help="ext: by file type, date: by date, both: type/date (default: ext)",
    )
    parser.add_argument(
        "--date-format", default="%Y-%m",
        help="strftime format for date folders (default: %%Y-%%m, e.g. 2026-11)",
    )
    parser.add_argument(
        "--date-source", choices=["created", "modified"], default="created",
        help="which timestamp to use for date sorting (default: created)",
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true",
        help="also re-sort files already inside the sorter's own folders (use to "
             "re-organize, e.g. switch from 'ext' to 'both'); other folders are never touched",
    )
    parser.add_argument(
        "--remove-empty", action="store_true",
        help="delete the sorter's own folders that end up empty",
    )
    parser.add_argument(
        "-w", "--watch", action="store_true",
        help="keep running and sort new files as they appear",
    )
    parser.add_argument(
        "-i", "--interval", type=float, default=5.0,
        help="seconds between checks in watch mode (default: 5)",
    )
    parser.add_argument(
        "--settle", type=float, default=3.0,
        help="ignore files modified within this many seconds, to avoid "
             "moving in-progress downloads (default: 3)",
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true",
        help="show what would be moved without moving anything",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="only print errors and the final summary",
    )
    parser.add_argument(
        "--undo", nargs="?", const="latest", metavar="LOG",
        help="move files back to where they were before the last run "
             "(or before the run recorded in LOG)",
    )
    args = parser.parse_args()

    args.source = os.path.abspath(os.path.expanduser(args.source))
    if not os.path.isdir(args.source):
        parser.error(f"source folder does not exist: {args.source}")
    if args.interval <= 0:
        parser.error("--interval must be greater than 0")
    if args.settle < 0:
        parser.error("--settle cannot be negative")
    if args.watch and args.dry_run:
        parser.error("--dry-run cannot be combined with --watch (it would report the same files forever)")
    if args.undo and (args.watch or args.recursive):
        parser.error("--undo cannot be combined with --watch or --recursive")
    try:
        datetime.now().strftime(args.date_format)
    except ValueError as exc:
        parser.error(f"invalid --date-format: {exc}")
    return args


def main():
    args = parse_args()

    if args.undo:
        n = undo(args)
        log(f"Done: {'would restore' if args.dry_run else 'restored'} {n} file(s).")
        return

    log(f"Sorting {args.source} (mode={args.mode}"
        f"{', recursive' if args.recursive else ''}"
        f"{', dry-run' if args.dry_run else ''}{', watching' if args.watch else ''})")

    # never move this script itself if it lives in the folder being sorted
    protected = {os.path.normcase(os.path.abspath(__file__))}
    move_log = MoveLog(args.source)
    total = 0
    try:
        if args.watch:
            log(f"Watching every {args.interval:g}s. Press Ctrl+C to stop.")
            while True:
                total += sort_folder(args, move_log, protected)
                time.sleep(args.interval)
        else:
            total = sort_folder(args, move_log, protected)
    except KeyboardInterrupt:
        print()  # newline after ^C

    verb = "would move" if args.dry_run else "moved"
    log(f"Done: {verb} {total} file(s).")
    if move_log.path:
        log(f"Move log: {move_log.path}  (undo with --undo)")


if __name__ == "__main__":
    main()
