# File Scanner

A desktop app for Mac and Windows. It lists every file in a folder and reads its details and metadata. It can also find duplicate files and move them into a separate folder.

## What it reports

For every file:

- File name, extension, category, file type and MIME type
- The apps likely to open it, for both Mac and Windows. On Windows it also shows the actual default app.
- Size, full path, relative path, folder and folder depth
- Created, modified and last-opened dates
- Hidden, system, read-only and symlink flags. Files inside hidden folders count as hidden.
- Images: width × height, megapixels, orientation, DPI, colour mode, and EXIF data (camera, lens, ISO, exposure, date taken, and GPS with a map link). Includes HEIC and RAW.
- Video: dimensions, length, frame rate, codecs, bit rates, audio tracks, and the camera make/model and GPS location when the file has them.
- Audio: length, codec, sample rate, channels, bit rate, and tags (artist, album, title, etc.).
- PDF: page count, title, author, creating app and whether it is encrypted.
- Word, Excel and PowerPoint files: author, last modified by, title, company, page and word counts, and editing time.
- A checksum (optional)

## Using it

1. Choose a folder (Browse, or drag it onto the window) and pick your options:
   - Include subfolders, and how many levels deep
   - Include hidden files and system files (`.DS_Store`, `Thumbs.db`, `._*`)
   - Follow symlinks
   - Read dimensions, length and metadata
   - Checksum every file
   - Also list folders with their total size
   - Skip names matching a pattern (for example `node_modules, .git, *.tmp`)
   - Minimum file size
2. Click **Scan**.
3. **Files** tab: search, filter by category, or show duplicates only. Click a file to see its details and a preview. Double-click to open it. Right-click to show it in Finder/Explorer or copy its path.
   The preview shows:
   - Images, including HEIC, SVG, animated GIFs, Photoshop files and the embedded preview of camera RAW files. Scroll to zoom and drag to move around. Double-click to switch between fit and actual size.
   - PDFs and PDF-compatible Illustrator files, with every page.
   - Video and audio, with play/pause, a position slider and volume. Videos open on their first frame, and audio shows its cover art.
   - The preview image saved inside InDesign, Illustrator, EPS, Adobe XD, Sketch, Pages, Numbers and Keynote files.
   - Text and code, Markdown, CSV and Excel files as a table, and the text of Word, PowerPoint and OpenDocument files (or their thumbnail).
   - The list of files inside ZIP and TAR archives.
   - A sample of a font file at several sizes.
   - Anything else the operating system can preview (Windows Explorer thumbnails or macOS Quick Look), for example InDesign, Premiere or 3D files when their apps are installed.
4. **Summary** tab: totals by category and by extension, the largest files, empty files, and files that couldn't be read.
5. **Duplicates** tab:
   - Choose how to match: identical content (checksum), name and size, or name only.
   - Choose which copy to keep: oldest, newest, shortest path or longest path. Files with "copy" or "(1)" in their name are never picked as the keeper.
   - Click a group to compare its files side by side. Differences are highlighted.
   - The extra copies are ticked. **Move ticked files to duplicates folder** keeps their sub-folder structure and writes a log, and **Undo a previous move** uses that log to put them back.
6. **Export**: CSV, Excel (with Summary and Duplicates sheets), JSON, an HTML report, or tab-separated text.
   - Tick the columns you want.
   - Put metadata in one column, or give each metadata field its own column.
   - Export everything, or only the rows the current filter shows.

## Running from source

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

## Building the apps

- **Mac:** `./build_mac.sh` makes `dist/File Scanner.app` and `dist/File Scanner-mac.zip`.
- **Windows:** run `build_windows.bat` on a Windows PC. It makes `dist\File Scanner.exe`, a single file that needs no installation.
- **Both at once:** push this folder to GitHub, then run the **Build apps** workflow in the Actions tab (or push a tag such as `v1.0.0`). Download the Mac zip and the Windows exe from the finished run.

The apps aren't code-signed:

- **Mac:** the first time, right-click the app and choose **Open**.
- **Windows:** on the SmartScreen warning, click **More info**, then **Run anyway**.

To test a build without opening the window: `"File Scanner" --selftest <folder>`.
