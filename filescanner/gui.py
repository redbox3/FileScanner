"""Desktop window (Qt) - works on macOS and Windows."""

import html
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QObject, QSettings, QSortFilterProxyModel, Qt,
                            QThread, QUrl, Signal)
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSpinBox, QSplitter, QTableView, QTabWidget, QTextBrowser,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import __version__, duplicates, exporter
from .preview import PreviewPane
from .scanner import ScanOptions, enrich, human_size, walk

APP_NAME = "File Scanner"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

# Columns shown in the on-screen table: (record key, heading, sort key)
TABLE_COLUMNS = [
    ("name", "Name"),
    ("category", "Category"),
    ("type", "Type"),
    ("size_human", "Size"),
    ("resolution", "Dimensions"),
    ("duration_human", "Length"),
    ("modified", "Modified"),
    ("created", "Created"),
    ("hidden", "Hidden"),
    ("apps", "Probable apps"),
    ("relative_path", "Path (relative)"),
]
SORT_KEYS = {"size_human": "size", "duration_human": "duration", "resolution": "megapixels"}


# ---------------------------------------------------------------- helpers

def reveal(path):
    if IS_MAC:
        subprocess.Popen(["open", "-R", path])
    elif IS_WIN:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def open_file(path):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def record_html(r, with_preview=True):
    esc = html.escape
    rows = [("File name", r.get("name")), ("Full path", r.get("path")), ("Type", r.get("type")),
            ("Category", r.get("category")), ("MIME", r.get("mime")),
            ("Size", f"{r.get('size_human', '')} ({r.get('size', 0):,} bytes)"),
            ("Dimensions", r.get("resolution")), ("Megapixels", r.get("megapixels")),
            ("Orientation", r.get("orientation")), ("Length", r.get("duration_human")),
            ("Frame rate", r.get("frame_rate")), ("Created", r.get("created")), ("Modified", r.get("modified")),
            ("Last opened", r.get("accessed")), ("Hidden", "Yes" if r.get("hidden") else "No"),
            ("Read only", "Yes" if r.get("read_only") else "No"),
            ("Probable apps (Mac)", r.get("apps_mac")), ("Probable apps (Windows)", r.get("apps_windows")),
            ("Default app", r.get("default_app")), ("Checksum", r.get("hash")),
            ("Duplicate group", r.get("duplicate_group")), ("Error", r.get("error"))]
    out = [f"<h3>{esc(r.get('name', ''))}</h3><table cellpadding=3>"]
    for k, v in rows:
        if v not in (None, "", 0) or k in ("Size",):
            out.append(f"<tr><td><b>{esc(k)}</b></td><td>{esc(str(v))}</td></tr>")
    out.append("</table>")
    meta = r.get("metadata") or {}
    if meta:
        out.append("<h4>Metadata / EXIF</h4><table cellpadding=2>")
        for k, v in meta.items():
            v = str(v)
            cell = f'<a href="{esc(v)}">{esc(v)}</a>' if v.startswith("https://") else esc(v)
            out.append(f"<tr><td><b>{esc(k)}</b></td><td>{cell}</td></tr>")
        out.append("</table>")
    return "".join(out)


# ---------------------------------------------------------------- table model

class FileModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.records = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return len(TABLE_COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return TABLE_COLUMNS[section][1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        r = self.records[index.row()]
        key = TABLE_COLUMNS[index.column()][0]
        if role == Qt.DisplayRole:
            v = r.get(key, "")
            if isinstance(v, bool):
                return "Yes" if v else ""
            return "" if v is None else str(v)
        if role == Qt.UserRole:  # sort value
            v = r.get(SORT_KEYS.get(key, key))
            if v is None or v == "":
                return -1 if key in SORT_KEYS else ""
            return v if isinstance(v, (int, float)) else str(v).lower()
        if role == Qt.ToolTipRole and key in ("relative_path", "apps", "type"):
            return r.get("path") if key == "relative_path" else r.get(key)
        if role == Qt.ForegroundRole:
            if r.get("error"):
                return QBrush(QColor("#c0392b"))
            if r.get("hidden"):
                return QBrush(QColor("#888888"))
        if role == Qt.TextAlignmentRole and key in ("size_human", "duration_human"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def add(self, batch):
        if not batch:
            return
        start = len(self.records)
        self.beginInsertRows(QModelIndex(), start, start + len(batch) - 1)
        self.records.extend(batch)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self.records = []
        self.endResetModel()

    def refresh(self):
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.records) - 1, len(TABLE_COLUMNS) - 1))


class FilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.category = ""
        self.only_dups = False
        self.setSortRole(Qt.UserRole)

    def set_filter(self, text=None, category=None, only_dups=None):
        if text is not None:
            self.text = text.lower()
        if category is not None:
            self.category = category
        if only_dups is not None:
            self.only_dups = only_dups
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().records[row]
        if self.category and r.get("category") != self.category:
            return False
        if self.only_dups and not r.get("duplicate_group"):
            return False
        if self.text:
            hay = f"{r.get('name', '')} {r.get('path', '')} {r.get('type', '')}".lower()
            return all(word in hay for word in self.text.split())
        return True


# ---------------------------------------------------------------- background workers

class ScanWorker(QObject):
    progress = Signal(int, str)
    batch = Signal(list)
    finished = Signal(bool)

    def __init__(self, opts):
        super().__init__()
        self.opts = opts
        self.cancel = False

    def run(self):
        cancelled = lambda: self.cancel
        pending = []
        workers = min(8, (os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = []
            for rec in walk(self.opts, self.progress.emit, cancelled):
                if rec.get("category") in ("Error", "Folder"):
                    pending.append(rec)
                else:
                    futures.append(pool.submit(self._enrich, rec))
                if len(futures) >= 200:
                    pending.extend(f.result() for f in futures)
                    futures = []
                    self.batch.emit(pending)
                    pending = []
                if self.cancel:
                    break
            pending.extend(f.result() for f in futures)
        self.batch.emit(pending)
        self.finished.emit(self.cancel)

    def _enrich(self, rec):
        if self.cancel:
            return rec
        enrich(rec, self.opts)
        if self.opts.compute_hash and not self.cancel:
            try:
                rec["hash"] = duplicates.file_hash(rec["path"], cancelled=lambda: self.cancel)
            except OSError as exc:
                rec["error"] = f"hash: {exc}"
        return rec


class DupWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(list)

    def __init__(self, records, mode, include_empty):
        super().__init__()
        self.records, self.mode, self.include_empty = records, mode, include_empty
        self.cancel = False

    def run(self):
        groups = duplicates.find(self.records, self.mode, self.include_empty, self.progress.emit, lambda: self.cancel)
        self.finished.emit(groups)


# ---------------------------------------------------------------- export dialog

class ExportDialog(QDialog):
    def __init__(self, parent, settings, has_filter, has_dups):
        super().__init__(parent)
        self.setWindowTitle("Export results")
        self.settings = settings
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.format = QComboBox()
        self.format.addItems(exporter.FORMATS)
        self.format.setCurrentText(settings.value("export/format", next(iter(exporter.FORMATS))))
        form.addRow("Format:", self.format)
        layout.addLayout(form)

        layout.addWidget(QLabel("Columns to include:"))
        self.cols = QListWidget()
        saved = settings.value("export/columns")
        saved = set(saved) if isinstance(saved, list) else None
        for key, label, default in exporter.COLUMNS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            on = (key in saved) if saved is not None else default
            item.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.cols.addItem(item)
        layout.addWidget(self.cols, 1)

        row = QHBoxLayout()
        for text, state in (("Select all", Qt.Checked), ("Select none", Qt.Unchecked)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, s=state: self._set_all(s))
            row.addWidget(b)
        b = QPushButton("Defaults")
        b.clicked.connect(self._defaults)
        row.addWidget(b)
        row.addStretch()
        layout.addLayout(row)

        self.split_meta = QCheckBox("Put each metadata/EXIF field in its own column (CSV / Excel)")
        self.split_meta.setChecked(settings.value("export/split", False, type=bool))
        self.only_visible = QCheckBox("Only export the rows currently shown (search / category filter)")
        self.only_visible.setEnabled(has_filter)
        self.with_dups = QCheckBox("Include duplicate groups (Excel / JSON / HTML)")
        self.with_dups.setChecked(has_dups)
        self.with_dups.setEnabled(has_dups)
        for w in (self.split_meta, self.only_visible, self.with_dups):
            layout.addWidget(w)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Export...")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, 620)

    def _set_all(self, state):
        for i in range(self.cols.count()):
            self.cols.item(i).setCheckState(state)

    def _defaults(self):
        for i, (_, _, default) in enumerate(exporter.COLUMNS):
            self.cols.item(i).setCheckState(Qt.Checked if default else Qt.Unchecked)

    def columns(self):
        return [self.cols.item(i).data(Qt.UserRole) for i in range(self.cols.count())
                if self.cols.item(i).checkState() == Qt.Checked]

    def accept(self):
        self.settings.setValue("export/format", self.format.currentText())
        self.settings.setValue("export/columns", self.columns())
        self.settings.setValue("export/split", self.split_meta.isChecked())
        super().accept()


# ---------------------------------------------------------------- main window

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = QSettings("ProAVL", APP_NAME)
        self.scan_root = ""
        self.dup_groups = []
        self.keepers = {}
        self.thread = None
        self.worker = None
        self.setAcceptDrops(True)

        central = QWidget()
        root = QVBoxLayout(central)

        # folder row
        row = QHBoxLayout()
        row.addWidget(QLabel("Folder:"))
        self.folder = QLineEdit(self.settings.value("folder", ""))
        self.folder.setPlaceholderText("Choose a folder, or drag one onto this window")
        row.addWidget(self.folder, 1)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.choose_folder)
        row.addWidget(browse)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setDefault(True)
        self.scan_btn.setMinimumWidth(100)
        self.scan_btn.clicked.connect(self.start_or_cancel_scan)
        row.addWidget(self.scan_btn)
        root.addLayout(row)

        # options
        box = QGroupBox("Scan options")
        grid = QGridLayout(box)
        s = self.settings
        self.opt_recursive = QCheckBox("Include subfolders")
        self.opt_recursive.setChecked(s.value("opt/recursive", True, type=bool))
        self.opt_depth = QSpinBox()
        self.opt_depth.setRange(0, 99)
        self.opt_depth.setSpecialValueText("all levels")
        self.opt_depth.setValue(s.value("opt/depth", 0, type=int))
        self.opt_depth.setPrefix("depth: ")
        self.opt_hidden = QCheckBox("Include hidden files")
        self.opt_hidden.setChecked(s.value("opt/hidden", True, type=bool))
        self.opt_system = QCheckBox("Include system files (.DS_Store, Thumbs.db, ._*)")
        self.opt_system.setChecked(s.value("opt/system", True, type=bool))
        self.opt_links = QCheckBox("Follow shortcuts / symlinks")
        self.opt_links.setChecked(s.value("opt/links", False, type=bool))
        self.opt_meta = QCheckBox("Read dimensions, length && metadata")
        self.opt_meta.setChecked(s.value("opt/meta", True, type=bool))
        self.opt_hash = QCheckBox("Checksum every file (slower)")
        self.opt_hash.setChecked(s.value("opt/hash", False, type=bool))
        self.opt_folders = QCheckBox("Also list folders with their total size")
        self.opt_folders.setChecked(s.value("opt/folders", False, type=bool))
        self.opt_exclude = QLineEdit(s.value("opt/exclude", ""))
        self.opt_exclude.setPlaceholderText("e.g.  node_modules, .git, *.tmp, Cache*")
        self.opt_min = QSpinBox()
        self.opt_min.setRange(0, 10_000_000)
        self.opt_min.setSuffix(" KB")
        self.opt_min.setSpecialValueText("any size")
        self.opt_min.setValue(s.value("opt/min", 0, type=int))
        self.opt_recursive.toggled.connect(self.opt_depth.setEnabled)
        self.opt_depth.setEnabled(self.opt_recursive.isChecked())

        grid.addWidget(self.opt_recursive, 0, 0)
        grid.addWidget(self.opt_depth, 0, 1)
        grid.addWidget(self.opt_hidden, 0, 2)
        grid.addWidget(self.opt_system, 0, 3)
        grid.addWidget(self.opt_meta, 1, 0)
        grid.addWidget(self.opt_hash, 1, 1)
        grid.addWidget(self.opt_links, 1, 2)
        grid.addWidget(self.opt_folders, 1, 3)
        grid.addWidget(QLabel("Skip names matching:"), 2, 0)
        grid.addWidget(self.opt_exclude, 2, 1, 1, 2)
        min_row = QHBoxLayout()
        min_row.addWidget(QLabel("Minimum size:"))
        min_row.addWidget(self.opt_min)
        min_row.addStretch()
        grid.addLayout(min_row, 2, 3)
        root.addWidget(box)

        # progress
        prow = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(10)
        self.status = QLabel("Ready.")
        prow.addWidget(self.status, 1)
        prow.addWidget(self.progress, 1)
        root.addLayout(prow)

        # tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_files_tab(), "Files")
        self.tabs.addTab(self._build_summary_tab(), "Summary")
        self.tabs.addTab(self._build_dups_tab(), "Duplicates")
        root.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self._build_menu()
        self.resize(1300, 850)
        geom = self.settings.value("geometry")
        if geom is not None:
            self.restoreGeometry(geom)

    # ---------- layout builders

    def _build_files_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name, path or type...")
        self.search.textChanged.connect(lambda t: (self.proxy.set_filter(text=t), self._update_count()))
        self.cat_filter = QComboBox()
        self.cat_filter.addItem("All categories", "")
        self.cat_filter.currentIndexChanged.connect(
            lambda _: (self.proxy.set_filter(category=self.cat_filter.currentData()), self._update_count()))
        self.dups_only = QCheckBox("Duplicates only")
        self.dups_only.toggled.connect(lambda on: (self.proxy.set_filter(only_dups=on), self._update_count()))
        self.count_label = QLabel("")
        export_btn = QPushButton("Export...")
        export_btn.clicked.connect(self.export)
        bar.addWidget(self.search, 2)
        bar.addWidget(self.cat_filter)
        bar.addWidget(self.dups_only)
        bar.addWidget(self.count_label, 1)
        bar.addWidget(export_btn)
        v.addLayout(bar)

        self.model = FileModel()
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, width in enumerate((240, 80, 160, 80, 100, 70, 140, 140, 55, 200)):
            self.table.setColumnWidth(i, width)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_menu)
        self.table.doubleClicked.connect(lambda idx: open_file(self._record_at(idx)["path"]))
        self.table.selectionModel().currentRowChanged.connect(self._show_details)

        self.preview = PreviewPane()
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        side = QSplitter(Qt.Vertical)
        side.setChildrenCollapsible(False)
        side.addWidget(self.preview)
        side.addWidget(self.details)
        side.setStretchFactor(0, 3)
        side.setStretchFactor(1, 2)
        side.setSizes([450, 300])

        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(side)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([820, 480])
        v.addWidget(split, 1)
        return w

    def _build_summary_tab(self):
        self.summary_view = QTextBrowser()
        return self.summary_view

    def _build_dups_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Match by:"))
        self.dup_mode = QComboBox()
        self.dup_mode.addItems(duplicates.MODES)
        bar.addWidget(self.dup_mode)
        self.dup_empty = QCheckBox("Include empty files")
        bar.addWidget(self.dup_empty)
        self.dup_btn = QPushButton("Find duplicates")
        self.dup_btn.clicked.connect(self.start_or_cancel_dups)
        bar.addWidget(self.dup_btn)
        bar.addSpacing(20)
        bar.addWidget(QLabel("Keep:"))
        self.keep_rule = QComboBox()
        self.keep_rule.addItems(duplicates.KEEP_RULES)
        self.keep_rule.currentIndexChanged.connect(lambda _: self._fill_dup_tree())
        bar.addWidget(self.keep_rule)
        bar.addStretch()
        v.addLayout(bar)

        self.dup_info = QLabel("Scan a folder, then click Find duplicates. Ticked files are the extra copies "
                               "that will be moved; the unticked one in each group is kept.")
        self.dup_info.setWordWrap(True)
        v.addWidget(self.dup_info)

        self.dup_tree = QTreeWidget()
        self.dup_tree.setHeaderLabels(["File / group", "Folder", "Size", "Created", "Modified", "Dimensions",
                                       "Length", "Checksum"])
        self.dup_tree.setAlternatingRowColors(True)
        self.dup_tree.setColumnWidth(0, 300)
        self.dup_tree.setColumnWidth(1, 360)
        self.dup_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.dup_tree.customContextMenuRequested.connect(self._dup_menu)
        self.dup_tree.currentItemChanged.connect(self._show_dup_compare)
        self.dup_tree.itemDoubleClicked.connect(
            lambda item, _: item.data(0, Qt.UserRole) and open_file(item.data(0, Qt.UserRole)["path"]))

        self.compare = QTextBrowser()
        self.compare.setOpenExternalLinks(True)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.dup_tree)
        split.addWidget(self.compare)
        split.setSizes([450, 250])
        v.addWidget(split, 1)

        bottom = QHBoxLayout()
        for text, slot in (("Tick all copies", lambda: self._tick_all(True)),
                           ("Untick all", lambda: self._tick_all(False)),
                           ("Export duplicate list...", self.export_dups),
                           ("Undo a previous move...", self.undo_move)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bottom.addWidget(b)
        bottom.addStretch()
        self.move_btn = QPushButton("Move ticked files to duplicates folder...")
        self.move_btn.clicked.connect(self.move_dups)
        bottom.addWidget(self.move_btn)
        v.addLayout(bottom)
        return w

    def _build_menu(self):
        m = self.menuBar().addMenu("&File")
        for text, slot, shortcut in (("Choose folder...", self.choose_folder, "Ctrl+O"),
                                     ("Scan", self.start_or_cancel_scan, "Ctrl+R"),
                                     ("Export results...", self.export, "Ctrl+E"),
                                     ("Export duplicate list...", self.export_dups, None)):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            m.addAction(a)
        m.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        m.addAction(quit_action)
        h = self.menuBar().addMenu("&Help")
        about = QAction(f"About {APP_NAME}", self)
        about.triggered.connect(lambda: QMessageBox.about(
            self, APP_NAME, f"<b>{APP_NAME}</b> {__version__}<br>Folder inventory, metadata and duplicate finder."))
        h.addAction(about)

    # ---------- drag & drop

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        path = e.mimeData().urls()[0].toLocalFile()
        if os.path.isfile(path):
            path = os.path.dirname(path)
        self.folder.setText(path)

    # ---------- scanning

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a folder to scan", self.folder.text() or os.path.expanduser("~"))
        if path:
            self.folder.setText(path)

    def _options(self):
        excl = [p.strip() for p in self.opt_exclude.text().replace(";", ",").split(",") if p.strip()]
        return ScanOptions(
            root=self.folder.text().strip(),
            recursive=self.opt_recursive.isChecked(),
            max_depth=self.opt_depth.value(),
            include_hidden=self.opt_hidden.isChecked(),
            include_system=self.opt_system.isChecked(),
            follow_symlinks=self.opt_links.isChecked(),
            read_metadata=self.opt_meta.isChecked(),
            compute_hash=self.opt_hash.isChecked(),
            exclude_patterns=excl,
            min_size=self.opt_min.value() * 1024,
            include_folders=self.opt_folders.isChecked(),
        )

    def _save_options(self):
        s = self.settings
        s.setValue("folder", self.folder.text())
        for key, w in (("recursive", self.opt_recursive), ("hidden", self.opt_hidden), ("system", self.opt_system),
                       ("links", self.opt_links), ("meta", self.opt_meta), ("hash", self.opt_hash),
                       ("folders", self.opt_folders)):
            s.setValue(f"opt/{key}", w.isChecked())
        s.setValue("opt/depth", self.opt_depth.value())
        s.setValue("opt/min", self.opt_min.value())
        s.setValue("opt/exclude", self.opt_exclude.text())

    def start_or_cancel_scan(self):
        if self.worker and isinstance(self.worker, ScanWorker):
            self.worker.cancel = True
            self.status.setText("Cancelling...")
            return
        if self.worker:
            return
        opts = self._options()
        if not opts.root or not os.path.isdir(opts.root):
            QMessageBox.warning(self, APP_NAME, "Please choose a folder that exists.")
            return
        self._save_options()
        self.scan_root = os.path.abspath(opts.root)
        self.model.clear()
        self.dup_groups, self.keepers = [], {}
        self.dup_tree.clear()
        self.compare.clear()
        self.details.clear()
        self.preview.clear()
        self.table.setSortingEnabled(False)
        self.progress.setRange(0, 0)
        self.scan_btn.setText("Cancel")
        self.status.setText("Scanning...")
        self._run(ScanWorker(opts), self._scan_progress, self._scan_done, batch=self.model.add)

    def _run(self, worker, on_progress, on_done, batch=None):
        self.thread = QThread()
        self.worker = worker
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.progress.connect(on_progress)
        if batch:
            worker.batch.connect(batch)
        worker.finished.connect(on_done)
        # quit from the worker thread itself; on_done waits for the thread, so a queued quit would deadlock
        worker.finished.connect(self.thread.quit, Qt.DirectConnection)
        self.thread.start()

    def _scan_progress(self, count, path):
        if path:
            self.status.setText(f"Found {count:,} files...  {os.path.basename(path)}")

    def _scan_done(self, cancelled):
        self.thread.wait()
        self.thread = self.worker = None
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.scan_btn.setText("Scan")
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        recs = self.model.records
        files = [r for r in recs if r.get("category") not in ("Folder", "Error")]
        total = sum(r.get("size", 0) for r in files)
        errors = sum(1 for r in recs if r.get("error"))
        msg = f"{'Cancelled - ' if cancelled else ''}{len(files):,} files, {human_size(total)}"
        if errors:
            msg += f"  ({errors} could not be fully read - shown in red)"
        self.status.setText(msg)
        current = self.cat_filter.currentData()
        self.cat_filter.blockSignals(True)
        self.cat_filter.clear()
        self.cat_filter.addItem("All categories", "")
        for cat in sorted({r.get("category", "") for r in recs}):
            self.cat_filter.addItem(cat, cat)
        idx = self.cat_filter.findData(current)
        self.cat_filter.setCurrentIndex(max(0, idx))
        self.cat_filter.blockSignals(False)
        self._update_count()
        self._fill_summary()

    def _update_count(self):
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count_label.setText(f"{shown:,} shown" if shown == total else f"{shown:,} of {total:,} shown")

    # ---------- files tab

    def _record_at(self, proxy_index):
        return self.model.records[self.proxy.mapToSource(proxy_index).row()]

    def _show_details(self, current, _prev=None):
        if not current.isValid():
            return
        r = self._record_at(current)
        self.details.setHtml(record_html(r))
        self.preview.show_record(r)

    def _context_menu(self, recs, global_pos):
        if not recs:
            return
        menu = QMenu(self)
        menu.addAction("Open", lambda: [open_file(r["path"]) for r in recs[:10]])
        menu.addAction("Show in Finder" if IS_MAC else "Show in Explorer", lambda: reveal(recs[0]["path"]))
        menu.addAction("Copy path" + ("s" if len(recs) > 1 else ""),
                       lambda: QGuiApplication.clipboard().setText("\n".join(r["path"] for r in recs)))
        menu.exec(global_pos)

    def _table_menu(self, pos):
        rows = self.table.selectionModel().selectedRows()
        self._context_menu([self._record_at(i) for i in rows], self.table.viewport().mapToGlobal(pos))

    # ---------- summary tab

    def _fill_summary(self):
        s = exporter.summary(self.model.records)
        esc = html.escape
        out = [f"<h2>{esc(self.scan_root)}</h2>",
               f"<p><b>{s['total_files']:,}</b> files &nbsp; <b>{human_size(s['total_size'])}</b> total &nbsp; "
               f"<b>{s['folders']:,}</b> folders containing files &nbsp; <b>{s['hidden_files']:,}</b> hidden"
               + (f" &nbsp; <b>{s['errors']:,}</b> unreadable" if s["errors"] else "") + "</p>",
               "<table width='100%'><tr><td valign=top width='33%'>",
               "<h3>By category</h3><table cellpadding=3><tr><th align=left>Category</th><th>Files</th><th>Size</th></tr>"]
        for cat, (n, size) in s["by_category"]:
            out.append(f"<tr><td>{esc(cat)}</td><td align=right>{n:,}</td><td align=right>{human_size(size)}</td></tr>")
        out.append("</table></td><td valign=top width='27%'><h3>By extension</h3><table cellpadding=3>"
                   "<tr><th align=left>Ext</th><th>Files</th><th>Size</th></tr>")
        for ext, (n, size) in s["by_extension"][:60]:
            out.append(f"<tr><td>{esc(ext)}</td><td align=right>{n:,}</td><td align=right>{human_size(size)}</td></tr>")
        out.append("</table></td><td valign=top><h3>Largest files</h3><table cellpadding=3>")
        for r in s["largest"]:
            out.append(f"<tr><td align=right>{esc(r.get('size_human', ''))}</td><td>{esc(r.get('relative_path', ''))}</td></tr>")
        out.append("</table></td></tr></table>")
        empties = [r for r in self.model.records if r.get("size") == 0 and r.get("category") not in ("Folder", "Error")]
        if empties:
            out.append(f"<h3>Empty (0 byte) files: {len(empties)}</h3><p>")
            out.append("<br>".join(esc(r.get("relative_path", "")) for r in empties[:50]))
            out.append("</p>")
        errs = [r for r in self.model.records if r.get("error")]
        if errs:
            out.append("<h3>Problems</h3><p>")
            out.append("<br>".join(f"{esc(r.get('path', ''))}: {esc(r['error'])}" for r in errs[:100]))
            out.append("</p>")
        self.summary_view.setHtml("".join(out))

    # ---------- duplicates

    def start_or_cancel_dups(self):
        if self.worker and isinstance(self.worker, DupWorker):
            self.worker.cancel = True
            return
        if self.worker:
            QMessageBox.information(self, APP_NAME, "Please wait for the scan to finish.")
            return
        if not self.model.records:
            QMessageBox.information(self, APP_NAME, "Scan a folder first.")
            return
        self.dup_btn.setText("Cancel")
        self.status.setText("Comparing files...")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._run(DupWorker(self.model.records, self.dup_mode.currentText(), self.dup_empty.isChecked()),
                  self._dup_progress, self._dups_done)

    def _dup_progress(self, done, total, path):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        if path:
            self.status.setText(f"Comparing {done:,} / {total:,}...  {os.path.basename(path)}")

    def _dups_done(self, groups):
        cancelled = self.worker.cancel
        self.thread.wait()
        self.thread = self.worker = None
        self.dup_btn.setText("Find duplicates")
        for r in self.model.records:
            r.pop("duplicate_group", None)
        self.dup_groups = groups
        for g in groups:
            for r in g["files"]:
                r["duplicate_group"] = g["id"]
        self.model.refresh()
        wasted = sum(g["wasted"] for g in groups)
        copies = sum(len(g["files"]) - 1 for g in groups)
        msg = ("Cancelled. " if cancelled else "") + (
            f"{len(groups):,} group{'s' if len(groups) != 1 else ''} of duplicates - "
            f"{copies:,} extra cop{'ies' if copies != 1 else 'y'} using {human_size(wasted)}"
            if groups else "No duplicates found.")
        self.status.setText(msg)
        self.dup_info.setText(msg + ".  Ticked files are the extra copies; the bold unticked file in each "
                                    "group is the one kept. Click a group to compare its files side by side.")
        self._fill_dup_tree()
        self.tabs.setCurrentIndex(2)

    def _fill_dup_tree(self):
        self.dup_tree.clear()
        rule = self.keep_rule.currentText()
        bold = QFont()
        bold.setBold(True)
        self.keepers = {}
        for g in self.dup_groups:
            keeper = duplicates.choose_keeper(g["files"], rule)
            self.keepers[g["id"]] = keeper
            top = QTreeWidgetItem([f"Group {g['id']}: {len(g['files'])} files", g["files"][0]["name"],
                                   human_size(g["size"]), "", "", "", "", f"{human_size(g['wasted'])} could be freed"])
            top.setData(0, Qt.UserRole + 1, g["id"])
            top.setFont(0, bold)
            for r in g["files"]:
                child = QTreeWidgetItem([r["name"], os.path.dirname(r.get("relative_path", "")) or "(top folder)", r.get("size_human", ""), r.get("created", ""),
                                         r.get("modified", ""), r.get("resolution", ""), r.get("duration_human", ""),
                                         (r.get("hash") or "")[:16]])
                child.setData(0, Qt.UserRole, r)
                child.setToolTip(1, r["path"])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                is_keeper = r is keeper
                child.setCheckState(0, Qt.Unchecked if is_keeper else Qt.Checked)
                if is_keeper:
                    for c in range(8):
                        child.setFont(c, bold)
                    child.setText(0, f"{r['name']}  (keep)")
                top.addChild(child)
            self.dup_tree.addTopLevelItem(top)
            top.setExpanded(True)

    def _ticked(self):
        out = []
        for i in range(self.dup_tree.topLevelItemCount()):
            top = self.dup_tree.topLevelItem(i)
            for j in range(top.childCount()):
                c = top.child(j)
                if c.checkState(0) == Qt.Checked:
                    out.append((top.data(0, Qt.UserRole + 1), c.data(0, Qt.UserRole), top))
        return out

    def _tick_all(self, on):
        for i in range(self.dup_tree.topLevelItemCount()):
            top = self.dup_tree.topLevelItem(i)
            keeper = self.keepers.get(top.data(0, Qt.UserRole + 1))
            for j in range(top.childCount()):
                c = top.child(j)
                c.setCheckState(0, Qt.Checked if on and c.data(0, Qt.UserRole) is not keeper else Qt.Unchecked)

    def _show_dup_compare(self, item, _prev=None):
        if item is None:
            return
        group_id = item.data(0, Qt.UserRole + 1) or (item.parent() and item.parent().data(0, Qt.UserRole + 1))
        g = next((g for g in self.dup_groups if g["id"] == group_id), None)
        if not g:
            return
        esc = html.escape
        files = g["files"]
        fields = [("Folder", "folder"), ("Size", "size_human"), ("Created", "created"), ("Modified", "modified"),
                  ("Last opened", "accessed"), ("Dimensions", "resolution"), ("Length", "duration_human"),
                  ("Hidden", "hidden"), ("Checksum", "hash")]
        meta_keys = []
        for r in files:
            for k in (r.get("metadata") or {}):
                if k not in meta_keys:
                    meta_keys.append(k)
        out = [f"<b>Group {g['id']}</b> - differences highlighted<table border=1 cellspacing=0 cellpadding=4>"
               "<tr><th></th>"]
        for r in files:
            tag = " (keep)" if self.keepers.get(g["id"]) is r else ""
            out.append(f"<th align=left>{esc(r['name'])}{tag}</th>")
        out.append("</tr>")

        def row(label, values):
            differs = len(set(values)) > 1
            style = " bgcolor='#fff3c4' style='color:#000'" if differs else ""
            cells = "".join(f"<td{style}>{esc(v)}</td>" for v in values)
            return f"<tr><td><b>{esc(label)}</b></td>{cells}</tr>"

        for label, key in fields:
            out.append(row(label, [str(r.get(key) or "") for r in files]))
        for k in meta_keys:
            out.append(row(k, [str((r.get("metadata") or {}).get(k, "")) for r in files]))
        out.append("</table>")
        self.compare.setHtml("".join(out))

    def _dup_menu(self, pos):
        item = self.dup_tree.itemAt(pos)
        r = item and item.data(0, Qt.UserRole)
        if r:
            self._context_menu([r], self.dup_tree.viewport().mapToGlobal(pos))

    def move_dups(self):
        ticked = self._ticked()
        if not ticked:
            QMessageBox.information(self, APP_NAME, "No files are ticked.")
            return
        # never move every copy of a group
        by_group = {}
        for gid, r, _ in ticked:
            by_group.setdefault(gid, []).append(r)
        for g in self.dup_groups:
            if len(by_group.get(g["id"], [])) >= len(g["files"]):
                QMessageBox.warning(self, APP_NAME, f"Group {g['id']} has every copy ticked. "
                                                    "Untick at least one file to keep.")
                return
        default = os.path.join(os.path.dirname(self.scan_root), os.path.basename(self.scan_root) + " - Duplicates")
        dest = QFileDialog.getExistingDirectory(self, "Choose where to move the duplicates (a new folder is fine)",
                                                os.path.dirname(default))
        if not dest:
            return
        if os.path.normcase(os.path.abspath(dest)) == os.path.normcase(self.scan_root):
            dest = os.path.join(dest, "_Duplicates")
        size = sum(r.get("size", 0) for _, r, _ in ticked)
        if QMessageBox.question(
                self, APP_NAME,
                f"Move {len(ticked):,} files ({human_size(size)}) to:\n{dest}\n\n"
                "Their sub-folder structure is kept, and a log file is written there so the move can be undone."
        ) != QMessageBox.Yes:
            return
        records = [r for _, r, _ in ticked]
        group_ids = {r["path"]: gid for gid, r, _ in ticked}
        self.preview.clear()   # release any file the preview has open
        moved, errors, log = duplicates.move_files(records, dest, self.scan_root, group_ids)
        moved_paths = {src for src, _ in moved}
        # drop moved files from the results
        self.model.beginResetModel()
        self.model.records = [r for r in self.model.records if r.get("path") not in moved_paths]
        self.model.endResetModel()
        for g in self.dup_groups:
            g["files"] = [r for r in g["files"] if r["path"] not in moved_paths]
        self.dup_groups = [g for g in self.dup_groups if len(g["files"]) > 1]
        for r in self.model.records:
            if r.get("duplicate_group") and not any(r in g["files"] for g in self.dup_groups):
                r.pop("duplicate_group", None)
        self._fill_dup_tree()
        self._fill_summary()
        self._update_count()
        msg = f"Moved {len(moved):,} files.\nLog: {log}"
        if errors:
            msg += f"\n\n{len(errors)} could not be moved:\n" + "\n".join(f"{p}: {e}" for p, e in errors[:10])
        QMessageBox.information(self, APP_NAME, msg)
        reveal(log)

    def undo_move(self):
        log, _ = QFileDialog.getOpenFileName(self, "Choose a moved-duplicates log", "", "Move logs (moved-duplicates-*.csv)")
        if not log:
            return
        self.preview.clear()
        restored, errors = duplicates.undo_from_log(log)
        msg = f"Moved {len(restored):,} files back to their original folders."
        if errors:
            msg += f"\n\n{len(errors)} could not be restored:\n" + "\n".join(f"{p}: {e}" for p, e in errors[:10])
        QMessageBox.information(self, APP_NAME, msg + "\n\nRe-scan to refresh the list.")

    # ---------- export

    def _visible_records(self):
        return [self.model.records[self.proxy.mapToSource(self.proxy.index(i, 0)).row()]
                for i in range(self.proxy.rowCount())]

    def export(self):
        if not self.model.records:
            QMessageBox.information(self, APP_NAME, "Scan a folder first.")
            return
        filtered = self.proxy.rowCount() != self.model.rowCount()
        dlg = ExportDialog(self, self.settings, filtered, bool(self.dup_groups))
        if filtered:
            dlg.only_visible.setChecked(True)
        if dlg.exec() != QDialog.Accepted:
            return
        columns = dlg.columns()
        if not columns:
            return
        ext = exporter.FORMATS[dlg.format.currentText()]
        name = f"{os.path.basename(self.scan_root) or 'scan'} - file list{ext}"
        start = os.path.join(self.settings.value("export/dir", os.path.expanduser("~/Desktop")), name)
        path, _ = QFileDialog.getSaveFileName(self, "Save export as", start, f"*{ext}")
        if not path:
            return
        if not path.lower().endswith(ext):
            path += ext
        self.settings.setValue("export/dir", os.path.dirname(path))
        records = self._visible_records() if dlg.only_visible.isChecked() else self.model.records
        try:
            exporter.export(path, records, columns, dlg.split_meta.isChecked(),
                            self.dup_groups if dlg.with_dups.isChecked() else None, self.scan_root)
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Export failed:\n{exc}")
            return
        self.status.setText(f"Exported {len(records):,} rows to {path}")
        reveal(path)

    def export_dups(self):
        if not self.dup_groups:
            QMessageBox.information(self, APP_NAME, "Find duplicates first.")
            return
        start = os.path.join(self.settings.value("export/dir", os.path.expanduser("~/Desktop")),
                             f"{os.path.basename(self.scan_root)} - duplicates.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Save duplicate list", start, "*.csv")
        if path:
            exporter.export_duplicates_csv(path, self.dup_groups, self.keepers)
            reveal(path)

    def closeEvent(self, e):
        self.preview.shutdown()
        self.settings.setValue("geometry", self.saveGeometry())
        self._save_options()
        if self.worker:
            self.worker.cancel = True
            self.thread.wait(3000)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("ProAVL")
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        win.folder.setText(sys.argv[1])
    sys.exit(app.exec())
