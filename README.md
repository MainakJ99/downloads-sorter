# Downloads Sorter

A small Python script that sorts loose files in your Downloads folder into subfolders by file type, by date, or both. It can run once, or stay running and pick up new downloads as they appear.

Only files sitting directly in the folder you point it at are moved. Folders you already have — games, projects, unzipped archives — are left alone.

## Requirements

- Python 3.8 or newer
- No third-party packages. `requirements.txt` is empty on purpose.

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

## What it does

| Mode | Flag | Result |
| --- | --- | --- |
| By type (default) | `-m ext` | `Downloads/Documents/report.pdf` |
| By date | `-m date` | `Downloads/2026-11/report.pdf` |
| Both | `-m both` | `Downloads/Documents/2026-11/report.pdf` |

Date folders use the file's creation time (`--date-source created`). On Linux, creation time is not available, so the script uses the modification time instead. Pass `--date-source modified` to always use the last-modified time.

Change the folder name format with `--date-format`. The default is `%Y-%m` (`2026-11`). `%Y/%m` makes `2026/11`.

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
| Code | py, js, ts, html, css, json, xml, java, c, cpp, h, go, rs, sh, yaml, yml, sql, ipynb |
| Other | everything else |

## Safety

- Folders are never entered or rearranged. A game folder, a project, or an extracted zip stays as it is.
- `--recursive` only looks inside folders this script created (`Images`, `Documents`, `Other`, date folders such as `2026-11`, and the same date folders nested under a category). Any other subfolder is skipped.
- Hidden and system files (`desktop.ini`, `Thumbs.db`, `.DS_Store`, dotfiles) are never moved.
- In-progress downloads are skipped: `.crdownload`, `.part`, `.partial`, `.tmp`, `.download`, `.opdownload`, and a finished-looking file that still has one of those companions next to it.
- Files modified in the last 3 seconds are skipped, so a download that is still being written is not moved. Change that window with `--settle`.
- Existing files are never overwritten. A name clash becomes `report (1).pdf`, then `report (2).pdf`.
- If a file is locked (open in another app, or held by a torrent client), that file is skipped and no copy is left behind.
- The script itself is never moved, even if it lives in the folder being sorted.
- A real run writes a move log under `<source>/.sorter_logs/`. Dry runs write nothing.

## Undo

Every move is recorded. Put the last run back:

```bash
python downloads_sorter.py --undo
```

Undo a specific log, or preview the restore:

```bash
python downloads_sorter.py --undo "C:\Users\you\Downloads\.sorter_logs\sort-20261118-221500.jsonl"
python downloads_sorter.py --undo --dry-run
```

Undo moves files back to their original paths, removes category folders that are empty afterward, and renames the log to `*.jsonl.undone`. A file is skipped if it is no longer at the sorted location, or if something already occupies the original path.

## Re-organize an already sorted folder

After a sort by type, switch to type plus date and clean up the old empty folders:

```bash
python downloads_sorter.py -m both --recursive --remove-empty --dry-run
python downloads_sorter.py -m both --recursive --remove-empty
```

`--remove-empty` only deletes folders this script owns, and only when they are empty.

## Watch mode

Keep sorting new files. The default check is every 5 seconds:

```bash
python downloads_sorter.py --watch
python downloads_sorter.py --watch --interval 10
```

Stop with Ctrl+C. `--dry-run` cannot be combined with `--watch`.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `-s`, `--source` | `~/Downloads` | Folder to sort |
| `-m`, `--mode` | `ext` | `ext`, `date`, or `both` |
| `--date-format` | `%Y-%m` | `strftime` pattern for date folders |
| `--date-source` | `created` | `created` or `modified` |
| `-r`, `--recursive` | off | Re-sort files already inside this script's folders |
| `--remove-empty` | off | Delete this script's folders once they are empty |
| `-w`, `--watch` | off | Keep running and sort new files |
| `-i`, `--interval` | `5` | Seconds between checks in watch mode |
| `--settle` | `3` | Skip files modified more recently than this |
| `-n`, `--dry-run` | off | Print the plan and move nothing |
| `-q`, `--quiet` | off | Errors and the final summary only |
| `--undo [LOG]` | | Restore the latest run, or the run in `LOG` |

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
