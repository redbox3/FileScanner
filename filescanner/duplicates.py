"""Finds duplicate files and moves the extra copies into a duplicates folder (with an undo log)."""

import csv
import hashlib
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime

CHUNK = 1024 * 1024
QUICK = 64 * 1024

MODE_CONTENT = "Identical content (safest)"
MODE_NAME_SIZE = "Same name and size (fast)"
MODE_NAME = "Same file name only"
MODES = [MODE_CONTENT, MODE_NAME_SIZE, MODE_NAME]

KEEP_OLDEST = "Oldest modified"
KEEP_NEWEST = "Newest modified"
KEEP_SHORTEST = "Shortest path"
KEEP_LONGEST = "Longest path"
KEEP_RULES = [KEEP_OLDEST, KEEP_NEWEST, KEEP_SHORTEST, KEEP_LONGEST]

_COPY_HINT = re.compile(r"(copy|kopie|\(\d+\)|\s\d+$| - copy)", re.I)


def file_hash(path, quick=False, cancelled=lambda: False):
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        if quick:
            h.update(f.read(QUICK))
            f.seek(0, 2)
            size = f.tell()
            if size > QUICK * 2:
                f.seek(size - QUICK)
                h.update(f.read(QUICK))
        else:
            while chunk := f.read(CHUNK):
                if cancelled():
                    return ""
                h.update(chunk)
    return h.hexdigest()


def find(records, mode=MODE_CONTENT, include_empty=False, progress=None, cancelled=lambda: False):
    """records: scan records. Returns list of groups: {key, size, files:[records], wasted}."""
    files = [r for r in records if r.get("category") not in ("Folder", "Error") and r.get("path")]
    if not include_empty:
        files = [r for r in files if r.get("size", 0) > 0]

    if mode == MODE_NAME:
        buckets = defaultdict(list)
        for r in files:
            buckets[r["name"].lower()].append(r)
        groups = [b for b in buckets.values() if len(b) > 1]
    elif mode == MODE_NAME_SIZE:
        buckets = defaultdict(list)
        for r in files:
            buckets[(r["name"].lower(), r["size"])].append(r)
        groups = [b for b in buckets.values() if len(b) > 1]
    else:
        by_size = defaultdict(list)
        for r in files:
            by_size[r["size"]].append(r)
        candidates = [g for g in by_size.values() if len(g) > 1]
        total = sum(len(g) for g in candidates)
        done = 0
        groups = []
        for same_size in candidates:
            # stage 1: quick hash of start+end to rule out most non-matches cheaply
            by_quick = defaultdict(list)
            for r in same_size:
                if cancelled():
                    return []
                try:
                    by_quick[file_hash(r["path"], quick=True)].append(r)
                except OSError as exc:
                    r["error"] = f"hash: {exc}"
                done += 1
                if progress and done % 10 == 0:
                    progress(done, total, r["path"])
            # stage 2: full hash only where the quick hash matched
            for quick_group in by_quick.values():
                if len(quick_group) < 2:
                    continue
                by_full = defaultdict(list)
                for r in quick_group:
                    if cancelled():
                        return []
                    try:
                        r["hash"] = r.get("hash") or file_hash(r["path"], cancelled=cancelled)
                        by_full[r["hash"]].append(r)
                    except OSError as exc:
                        r["error"] = f"hash: {exc}"
                    if progress:
                        progress(done, total, r["path"])
                groups.extend(g for g in by_full.values() if len(g) > 1)

    result = []
    for g in groups:
        g.sort(key=lambda r: r["path"].lower())
        size = g[0].get("size", 0)
        result.append({
            "key": g[0].get("hash") or g[0]["name"],
            "size": size,
            "files": g,
            "wasted": size * (len(g) - 1),
        })
    result.sort(key=lambda grp: grp["wasted"], reverse=True)
    for i, grp in enumerate(result, 1):
        grp["id"] = i
    if progress:
        progress(1, 1, "")
    return result


def choose_keeper(files, rule=KEEP_OLDEST):
    """Return the record to keep. Files that look like copies ("copy", "(1)") lose ties."""
    def looks_like_copy(r):
        stem = os.path.splitext(r["name"])[0]
        return 1 if _COPY_HINT.search(stem) else 0

    if rule == KEEP_NEWEST:
        key = lambda r: (looks_like_copy(r), _neg(r.get("modified", "")), len(r["path"]))
    elif rule == KEEP_SHORTEST:
        key = lambda r: (len(r["path"]), looks_like_copy(r), r.get("modified", ""))
    elif rule == KEEP_LONGEST:
        key = lambda r: (-len(r["path"]), looks_like_copy(r), r.get("modified", ""))
    else:
        key = lambda r: (looks_like_copy(r), r.get("modified", "") or "9999", len(r["path"]))
    return min(files, key=key)


def _neg(text):
    return "".join(chr(0x10FFFF - ord(c)) for c in text)


def _unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def move_files(records, dest_root, scan_root, group_ids=None):
    """Move the given records into dest_root, keeping their folder structure relative to scan_root.
    Writes a CSV log (used for undo). Returns (moved list of (src, dst), errors list, log path)."""
    os.makedirs(dest_root, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(dest_root, f"moved-duplicates-{stamp}.csv")
    moved, errors = [], []
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["group", "original_path", "moved_to", "size", "hash", "moved_at"])
        for r in records:
            src = r["path"]
            try:
                rel = os.path.relpath(src, scan_root)
                if rel.startswith(".."):
                    rel = os.path.basename(src)
                dst = _unique(os.path.join(dest_root, rel))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
                moved.append((src, dst))
                writer.writerow([(group_ids or {}).get(src, ""), src, dst, r.get("size", ""), r.get("hash", ""),
                                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            except Exception as exc:
                errors.append((src, str(exc)))
    return moved, errors, log_path


def undo_from_log(log_path):
    """Move files listed in a log back to where they came from."""
    restored, errors = [], []
    with open(log_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        src, dst = row["moved_to"], row["original_path"]
        try:
            if os.path.exists(dst):
                raise FileExistsError("a file already exists at the original location")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            restored.append(dst)
        except Exception as exc:
            errors.append((src, str(exc)))
    return restored, errors
