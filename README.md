# Downloads Sorter

A small Python script that sorts loose files in your Downloads folder into subfolders by file type, by date, or both. It can run once, or stay running and pick up new downloads as they appear. Every real run is logged, so it can be undone.

Only files sitting directly in the folder you point it at are moved. Folders you already have (games, projects, unzipped archives) are left alone.

## Requirements

- Python 3.6 or newer (the script uses f-strings)
- No third-party packages. It only uses the standard library: `argparse`, `os`, `shutil`, `errno`, `json`, `stat`, `sys`, `time` and `datetime`.

```bash
python downloads_sorter.py --help
```

## Quick start

Preview first. Nothing is moved:

```bash
python downloads_sorter.py --dry-run
```

Sort `~/Downloads` once, by file type (images, documents, videos, and so on):

```bash
python downloads_sorter.py
```

Sort a different folder:

```bash
python downloads_sorter.py --source "D:\Incoming"
```

Changed your mind? Put everything back:

```bash
python downloads_sorter.py --undo
```

## What it does

| Mode | Flag | Result |
| --- | --- | --- |
| By type (default) | `-m ext` | `Downloads/Documents/report.pdf` |
| By date | `-m date` | `Downloads/2026-11/report.pdf` |
| Both | `-m both` | `Downloads/Documents/2026-11/report.pdf` |

Date folders use the file's creation time (`--date-source created`). Windows with Python 3.12 or newer, and macOS, report a true creation time. Older Python on Windows uses the Windows creation time as well. Linux does not provide a creation time, so the script uses the modification time instead. Pass `--date-source modified` to always use the last-modified time.

Change the folder name format with `--date-format`. The default is `%Y-%m` (`2026-11`). `%Y/%m` makes `2026/11`. An invalid format is rejected before anything runs.

Unknown extensions, and files with no extension, go into `Other`.

### Categories

| Folder | Extensions |
| --- | --- |
| Images | jpg, jpeg, png, gif, bmp, webp, svg, heic, tiff, ico |
| Documents | pdf, doc, docx, txt, rtf, odt, md, epub, pages |
| Spreadsheets | xls, xlsx, csv, ods, numbers |
| Presentations | ppt, pptx, odp, key |
| Videos | mp4, mkv, mov, avi, wmv, flv, webm, m4v |
| Audio | mp3, wav, flac, aac, ogg, m4a, wma |
| Archives | zip, rar, 7z, tar, gz, bz2, xz, tgz |
| Installers | exe, msi, dmg, pkg, deb, rpm, appimage, apk |
| Code | py, js, ts, css, json, xml, java, c, cpp, h, go, rs, r, rmd, sh, yaml, yml, sql, ipynb |
| Code/Reading | html, htm |
| Other | everything else |

HTML and HTM files are reading material, so they go in `Code/Reading` instead of next to source files in `Code`. With `-m both` they go in `Code/Reading/2026-11`.

To add or change categories, edit the `CATEGORIES` dictionary at the top of `downloads_sorter.py`.

## Safety

- **Folders are never entered or rearranged.** A game folder, a project, or an extracted zip stays as it is.
- **`--recursive` only looks inside the sorter's own folders:** the category folders (`Images`, `Documents`, ..., `Code`, `Other`), `Code/Reading`, date folders such as `2026-11`, and date folders nested under a category or under `Code/Reading`. Any other subfolder, even one inside a category folder, is treated as a unit and skipped.
- **Folders are recognized by name.** A folder you created yourself that is called `Documents`, `Images`, `Other`, or that matches the date format (for example `2026-11`), is treated as the sorter's own and can be re-sorted with `--recursive`. Pick other names for your own folders inside the source.
- Hidden and system files are never moved: dotfiles, `desktop.ini`, `Thumbs.db`, `ehthumbs.db`, `.DS_Store`, `.localized`, and anything with the Windows Hidden or System attribute. Hidden folders (such as `.sorter_logs`) and symlinks are never touched.
- In-progress downloads are skipped: `.crdownload`, `.part`, `.partial`, `.tmp`, `.download`, `.opdownload`, and a finished-looking file that still has one of those companions next to it (for example `file.pdf` next to `file.pdf.part`).
- Files modified in the last 3 seconds are skipped, so a download that is still being written is not moved. Change that window with `--settle`.
- Existing files are never overwritten. A name clash becomes `report (1).pdf`, then `report (2).pdf`. This also holds if a clashing file appears while the script is running.
- A file that is already in the folder it belongs in is left where it is, so repeated runs are safe.
- If a file is locked (open in another app, or held by a torrent client), that file is skipped with a "Could not move" message, no copy is left behind, and the script continues with the next file.
- The script itself is never moved, even if it lives in the folder being sorted.
- A real run writes a move log under `<source>/.sorter_logs/`. Dry runs write nothing.

## Undo

Every move is recorded in a log named like `sort-20261118-221500.jsonl`. The log is created when the first file is moved, so a run that moves nothing leaves no log. In watch mode, one log covers the whole session, from start to Ctrl+C.

Put the last run back:

```bash
python downloads_sorter.py --undo
```

Undo looks for logs in the default `~/Downloads`. For another folder, pass `--source`:

```bash
python downloads_sorter.py --source "D:\Incoming" --undo
```

Undo a specific log, or preview the restore:

```bash
python downloads_sorter.py --undo "C:\Users\you\Downloads\.sorter_logs\sort-20261118-221500.jsonl"
python downloads_sorter.py --undo --dry-run
```

Undo moves files back to their original paths, removes the sorter's own folders that are empty afterward, and renames the log to `*.jsonl.undone`. Because used logs are renamed, running `--undo` again goes back one run further. A file is skipped if it is no longer at the sorted location, or if something already occupies the original path.

`--undo` cannot be combined with `--watch` or `--recursive`.

## Re-organize an already sorted folder

After a sort by type, switch to type plus date and clean up the old empty folders:

```bash
python downloads_sorter.py -m both --recursive --remove-empty --dry-run
python downloads_sorter.py -m both --recursive --remove-empty
```

`--remove-empty` only deletes the sorter's own folders (see [Safety](#safety)), and only when they are empty. It does nothing in a dry run.

If you used a custom `--date-format` before, pass the same one again. Date folders in a different format are not recognized as the sorter's own, so they are not re-sorted or cleaned up.

## Watch mode

Keep sorting new files. The default check is every 5 seconds:

```bash
python downloads_sorter.py --watch
python downloads_sorter.py --watch --interval 10
```

Stop with Ctrl+C. The script polls, so a new file can wait up to one interval, plus the settle time, before it is moved. `--dry-run` cannot be combined with `--watch`.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `-s`, `--source` | `~/Downloads` | Folder to sort |
| `-m`, `--mode` | `ext` | `ext`, `date`, or `both` |
| `--date-format` | `%Y-%m` | `strftime` pattern for date folders |
| `--date-source` | `created` | `created` or `modified` |
| `-r`, `--recursive` | off | Re-sort files already inside the sorter's own folders |
| `--remove-empty` | off | Delete the sorter's own folders once they are empty |
| `-w`, `--watch` | off | Keep running and sort new files |
| `-i`, `--interval` | `5` | Seconds between checks in watch mode (must be above 0) |
| `--settle` | `3` | Skip files modified more recently than this many seconds (cannot be negative) |
| `-n`, `--dry-run` | off | Print the plan and move nothing |
| `-q`, `--quiet` | off | Hide the per-file "Moved" lines. The start line, errors, dry-run lines and the final summary still print |
| `--undo [LOG]` | | Restore the latest run, or the run in `LOG` |

## Known limitations

- On Linux and macOS the move is done by creating a hard link and then removing the original, which guarantees nothing is overwritten. Drives that may not support hard links (FAT32 or exFAT USB drives, some network shares) can fail on every file with "Could not move". Run with `--dry-run`, then a real run on a few files, before trusting a new drive.
- Date folders come from the file's timestamp when it is moved, not from when it was downloaded, so copied or restored files can land in an older month.

## Examples

```bash
python downloads_sorter.py
python downloads_sorter.py --dry-run
python downloads_sorter.py -m date
python downloads_sorter.py -m both
python downloads_sorter.py --watch -i 10
python downloads_sorter.py -m both -r --remove-empty
python downloads_sorter.py --undo
```