"""Walks a folder and builds one record per file."""

import fnmatch
import os
import stat
import sys
from dataclasses import dataclass, field
from datetime import datetime

from . import filetypes, metadata

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


@dataclass
class ScanOptions:
    root: str
    recursive: bool = True
    max_depth: int = 0              # 0 = unlimited
    include_hidden: bool = True
    include_system: bool = True     # .DS_Store, Thumbs.db, ._ files
    follow_symlinks: bool = False
    read_metadata: bool = True
    compute_hash: bool = False
    exclude_patterns: list = field(default_factory=list)   # e.g. ["node_modules", "*.tmp"]
    only_categories: list = field(default_factory=list)    # empty = all
    min_size: int = 0
    max_size: int = 0               # 0 = no limit
    include_folders: bool = False   # also list folders (with total size and file count)


def human_size(n):
    if n is None:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1024


def _ts(value):
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S") if value else ""
    except (OSError, OverflowError, ValueError):
        return ""


def is_hidden(name, st):
    if name.startswith("."):
        return True
    if IS_WIN and getattr(st, "st_file_attributes", 0) & 0x2:  # FILE_ATTRIBUTE_HIDDEN
        return True
    if IS_MAC and getattr(st, "st_flags", 0) & getattr(stat, "UF_HIDDEN", 0x8000):
        return True
    return False


def _is_system(name, st):
    lower = name.lower()
    if lower in (".ds_store", "thumbs.db", "desktop.ini", "icon\r", ".localized") or lower.startswith("._"):
        return True
    return IS_WIN and bool(getattr(st, "st_file_attributes", 0) & 0x4)  # FILE_ATTRIBUTE_SYSTEM


def _excluded(name, rel, patterns):
    return any(fnmatch.fnmatch(name.lower(), p.lower()) or fnmatch.fnmatch(rel.lower(), p.lower()) for p in patterns)


_win_app_cache = {}


def windows_default_app(ext):
    """Friendly name of the app Windows will open this extension with (Windows only)."""
    if not IS_WIN or not ext:
        return ""
    if ext in _win_app_cache:
        return _win_app_cache[ext]
    name = ""
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        # ASSOCF_NONE=0, ASSOCSTR_FRIENDLYAPPNAME=4
        if ctypes.windll.shlwapi.AssocQueryStringW(0, 4, "." + ext, None, buf, ctypes.byref(size)) == 0:
            name = buf.value
    except Exception:
        pass
    _win_app_cache[ext] = name
    return name


def build_record(path, root, st, opts, in_hidden_folder=False):
    name = os.path.basename(path)
    ext, category, description, mime, apps, mac_apps, win_apps = filetypes.describe(name)
    folder = os.path.dirname(path)
    rel = os.path.relpath(path, root)
    created = getattr(st, "st_birthtime", None) or (st.st_ctime if IS_WIN else None)
    rec = {
        "name": name,
        "extension": ext,
        "category": category,
        "type": description,
        "mime": mime,
        "default_app": windows_default_app(ext),
        "apps": apps,
        "apps_mac": mac_apps,
        "apps_windows": win_apps,
        "size": st.st_size,
        "size_human": human_size(st.st_size),
        "path": path,
        "folder": folder,
        "relative_path": rel,
        "depth": rel.count(os.sep),
        "created": _ts(created),
        "modified": _ts(st.st_mtime),
        "accessed": _ts(st.st_atime),
        "hidden": in_hidden_folder or is_hidden(name, st),
        "in_hidden_folder": in_hidden_folder,
        "system": _is_system(name, st),
        "read_only": not os.access(path, os.W_OK),
        "symlink": os.path.islink(path),
        "width": None,
        "height": None,
        "resolution": "",
        "megapixels": None,
        "orientation": "",
        "duration": None,
        "duration_human": "",
        "frame_rate": None,
        "metadata": {},
        "hash": "",
        "error": "",
    }
    return rec


def enrich(rec, opts):
    """Fill in dimensions / duration / metadata (slow part, so done separately)."""
    if not opts.read_metadata:
        return rec
    try:
        info = metadata.read(rec["path"], rec["category"], rec["extension"])
    except Exception as exc:  # never let one bad file stop the scan
        rec["error"] = f"metadata: {exc}"
        return rec
    rec["width"], rec["height"] = info["width"], info["height"]
    if rec["width"] and rec["height"]:
        rec["resolution"] = f"{rec['width']} x {rec['height']}"
        rec["megapixels"] = round(rec["width"] * rec["height"] / 1_000_000, 2)
        rec["orientation"] = ("Landscape" if rec["width"] > rec["height"]
                              else "Portrait" if rec["width"] < rec["height"] else "Square")
    if info["duration"]:
        rec["duration"] = round(info["duration"], 3)
        rec["duration_human"] = metadata.fmt_duration(info["duration"])
    rec["frame_rate"] = info["frame_rate"]
    rec["metadata"] = info["metadata"]
    return rec


def walk(opts, progress=None, cancelled=lambda: False):
    """Yield (record_dict) for each file. progress(count, current_path) is called periodically."""
    root = os.path.abspath(opts.root)
    seen_dirs = set()
    count = 0
    folders = {}  # folder path -> [file count, total size] (for include_folders)

    def scan_dir(directory, depth, hidden_parent=False):
        nonlocal count
        if cancelled():
            return
        try:
            real = os.path.realpath(directory)
            if real in seen_dirs:  # symlink loop guard
                return
            seen_dirs.add(real)
            entries = sorted(os.scandir(directory), key=lambda e: e.name.lower())
        except OSError as exc:
            yield {"name": os.path.basename(directory), "path": directory, "folder": os.path.dirname(directory),
                   "category": "Error", "error": f"Cannot open folder: {exc.strerror or exc}", "size": 0}
            return
        subdirs = []
        for entry in entries:
            if cancelled():
                return
            try:
                is_link = entry.is_symlink()
                st = entry.stat(follow_symlinks=opts.follow_symlinks)
            except OSError as exc:
                yield {"name": entry.name, "path": entry.path, "folder": directory, "category": "Error",
                       "error": f"Cannot read: {exc.strerror or exc}", "size": 0}
                continue
            rel = os.path.relpath(entry.path, root)
            if opts.exclude_patterns and _excluded(entry.name, rel, opts.exclude_patterns):
                continue
            if not opts.include_hidden and is_hidden(entry.name, st):
                continue
            if not opts.include_system and _is_system(entry.name, st):
                continue
            if stat.S_ISDIR(st.st_mode):
                # macOS packages (.app, .photoslibrary, .fcpbundle...) are treated as folders too
                if is_link and not opts.follow_symlinks:
                    continue
                subdirs.append((entry.path, hidden_parent or is_hidden(entry.name, st)))
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            if st.st_size < opts.min_size or (opts.max_size and st.st_size > opts.max_size):
                continue
            rec = build_record(entry.path, root, st, opts, hidden_parent)
            if opts.only_categories and rec["category"] not in opts.only_categories:
                continue
            count += 1
            if progress and count % 25 == 0:
                progress(count, entry.path)
            if opts.include_folders:
                d = directory
                while True:
                    f = folders.setdefault(d, [0, 0])
                    f[0] += 1
                    f[1] += st.st_size
                    if os.path.normcase(d) == os.path.normcase(root):
                        break
                    d = os.path.dirname(d)
            yield rec
        if opts.recursive and (not opts.max_depth or depth < opts.max_depth):
            for sub, hidden in subdirs:
                yield from scan_dir(sub, depth + 1, hidden)

    yield from scan_dir(root, 1)

    if opts.include_folders and not cancelled():
        for path, (n, total) in sorted(folders.items()):
            yield {"name": os.path.basename(path) or path, "extension": "", "category": "Folder",
                   "type": f"Folder ({n} files)", "size": total, "size_human": human_size(total),
                   "path": path, "folder": os.path.dirname(path), "relative_path": os.path.relpath(path, root),
                   "metadata": {"Files inside (incl. subfolders)": n}}
    if progress:
        progress(count, "")
