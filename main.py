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


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    else:
        from filescanner.gui import main
        main()
