import sys


def selftest(folder):
    """Headless check used to verify a built app: scans a folder and prints what it found."""
    from filescanner.scanner import ScanOptions, enrich, walk
    from filescanner import metadata
    opts = ScanOptions(root=folder)
    recs = [enrich(r, opts) for r in walk(opts)]
    print(f"mediainfo available: {metadata._HAS_MEDIAINFO}")
    for r in recs:
        print(f"{r.get('relative_path', r['path'])} | {r['category']} | {r.get('resolution', '')} | {r.get('duration_human', '')}")
    print(f"{len(recs)} files")
    selftest_previews(recs)


def selftest_previews(recs):
    """Checks the preview pane's parts are in the build and can open each test file."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from filescanner import preview
    print(f"preview parts: pdf={preview._HAS_PDF} media={preview._HAS_MEDIA} svg={preview._HAS_SVG} pil={preview._HAS_PIL}")
    if preview._HAS_MEDIA:
        from PySide6.QtMultimedia import QMediaFormat
        formats = QMediaFormat().supportedFileFormats(QMediaFormat.Decode)
        print(f"media formats the player can open: {len(formats)}")
    for r in recs:
        if r.get("category") in ("Error", "Folder"):
            continue
        ext, name = r.get("extension", ""), r.get("relative_path", r["path"])
        if ext == "pdf" and preview._HAS_PDF:
            from PySide6.QtPdf import QPdfDocument
            doc = QPdfDocument()
            doc.load(r["path"])
            result = f"pdf viewer, {doc.pageCount()} page(s)" if doc.pageCount() else "pdf viewer could not open it"
        elif r.get("category") in ("Video", "Audio"):
            result = "media player" if preview._HAS_MEDIA else "no media player"
        else:
            kind = preview.build_preview(r["path"], ext, r["category"])
            result = kind[0] + (f": {kind[1]}" if kind[0] == "message" else "")
        print(f"preview | {name} | {result}")
    del app


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    else:
        from filescanner.gui import main
        main()
