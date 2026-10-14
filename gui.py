"""ApexTorrent GUI (PySide6): quick-add bar, minimal table, inspector drawer with security audit."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import libtorrent as lt
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextBrowser, QToolBar, QVBoxLayout, QWidget,
)

import config
import ipc
import security
from engine import PRESET_LABELS, Engine, list_interfaces, tracker_status

QSS = """
* { font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif; font-size: 13px; color: #E6EDF3; }
QMainWindow, QWidget#canvas { background: #0D0F12; }
QMenuBar { background: #0D0F12; } QMenuBar::item:selected { background: #181B20; }
QToolBar { background: #0D0F12; border: none; spacing: 6px; padding: 4px 0; }
QToolButton { background: #181B20; border: 1px solid #232830; border-radius: 8px; padding: 6px 12px; }
QToolButton:hover { background: #20252C; }
QTableWidget { background: #181B20; border: 1px solid #232830; border-radius: 10px; gridline-color: #20252C;
  selection-background-color: #243044; alternate-background-color: #161A1F; outline: 0; }
QHeaderView::section { background: #12151A; color: #8B949E; border: none; padding: 8px; font-weight: 600; }
QLineEdit, QComboBox { background: #181B20; border: 1px solid #2A303A; border-radius: 8px; padding: 8px 10px; }
QLineEdit:focus, QComboBox:focus { border-color: #4C8DFF; }
QComboBox QAbstractItemView { background: #181B20; selection-background-color: #243044; }
QPushButton { background: #4C8DFF; color: #fff; border: none; border-radius: 8px; padding: 8px 18px; font-weight: 600; }
QPushButton:hover { background: #6AA0FF; }
QPushButton#ghost { background: #232830; } QPushButton#ghost:hover { background: #2C333D; }
QPushButton#danger { background: #B62324; } QPushButton#danger:hover { background: #D1383A; }
QDockWidget { color: #8B949E; }
QDockWidget::title { background: #12151A; padding: 8px; }
QTabWidget::pane { border: 1px solid #232830; background: #181B20; border-radius: 8px; }
QTabBar::tab { background: #12151A; padding: 8px 14px; color: #8B949E; }
QTabBar::tab:selected { color: #E6EDF3; border-bottom: 2px solid #4C8DFF; }
QProgressBar { background: #0D0F12; border: none; border-radius: 5px; max-height: 10px; }
QProgressBar::chunk { background: #4C8DFF; border-radius: 5px; }
QPlainTextEdit, QTextBrowser { background: #12151A; border: 1px solid #232830; border-radius: 8px; }
QStatusBar { background: #0D0F12; color: #8B949E; }
QMenu { background: #181B20; border: 1px solid #2A303A; } QMenu::item { padding: 6px 22px; }
QMenu::item:selected { background: #243044; }
"""

GREEN, AMBER, RED, GRAY, BLUE = "#3FB950", "#D29922", "#F85149", "#8B949E", "#4C8DFF"
VERDICT_COLOR = {"clean": GREEN, "suspicious": AMBER, "threat": RED, "unverified": GRAY}
LEVEL = {"ok": (GREEN, "●"), "info": (BLUE, "●"), "warn": (AMBER, "▲"), "bad": (RED, "■")}
SEV_COLOR = {"": GRAY, "low": GRAY, "medium": AMBER, "high": RED}

COLS = ["Name", "Size", "Progress", "Speed  ↓ / ↑", "ETA", "Security"]


def resource_path(rel):
    """Bundled-resource lookup that works from source and inside a PyInstaller build (sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def app_icon():
    icon = QIcon()
    for rel in ("assets/apextorrent.ico", "assets/apextorrent.png"):
        p = resource_path(rel)
        if os.path.exists(p):
            icon.addFile(p)
    return icon


def _set_windows_app_id():
    """Gives the process its own taskbar identity so the taskbar shows our icon, not python's."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ApexTorrent.Desktop")
        except Exception:
            pass


def fmt_size(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_rate(n):
    return fmt_size(n) + "/s" if n > 0 else "–"


def fmt_eta(secs):
    secs = int(secs)
    if secs >= 86400:
        return f"{secs // 86400}d {secs % 86400 // 3600}h"
    if secs >= 3600:
        return f"{secs // 3600}h {secs % 3600 // 60}m"
    if secs >= 60:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs}s"


def esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class PieceMap(QWidget):
    def __init__(self):
        super().__init__()
        self.pieces = []
        self.setMinimumHeight(110)

    def set_pieces(self, pieces):
        self.pieces = pieces
        self.update()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.fillRect(self.rect(), QColor("#12151A"))
        n = len(self.pieces)
        if not n:
            return
        cell = 7
        cols, rows = max(1, self.width() // cell), max(1, self.height() // cell)
        cells = min(cols * rows, n)
        per = n / cells
        for i in range(cells):
            a, b = int(i * per), max(int(i * per) + 1, int((i + 1) * per))
            seg = self.pieces[a:b]
            col = QColor(BLUE)
            col.setAlphaF(0.12 + 0.88 * sum(1 for x in seg if x) / len(seg))
            qp.fillRect((i % cols) * cell, (i // cols) * cell, cell - 1, cell - 1, col)


class IfaceCombo(QComboBox):
    def __init__(self, refresh):
        super().__init__()
        self._refresh = refresh

    def showPopup(self):
        self._refresh()
        super().showPopup()


class MainWindow(QMainWindow):
    pipeline_done = Signal(str, object)

    def __init__(self, engine_factory=Engine):
        super().__init__()
        self.cfg = config.load()
        self.engine = engine_factory(self.cfg)
        self.reports, self.scanning = {}, set()
        self._shown_report = None
        self.pipeline_done.connect(self._on_pipeline_done)
        self.setWindowTitle("ApexTorrent")
        self.setWindowIcon(app_icon())
        self.resize(1360, 700)
        self.setAcceptDrops(True)

        # --- central: quick-add + table
        canvas = QWidget(objectName="canvas")
        lay = QVBoxLayout(canvas)
        lay.setContentsMargins(14, 10, 14, 6)
        bar = QHBoxLayout()
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Paste a magnet link or .torrent path, or drop a .torrent anywhere on this window")
        self.quick.returnPressed.connect(self.quick_add)
        add = QPushButton("Add")
        add.clicked.connect(self.quick_add)
        browse = QPushButton("Browse…", objectName="ghost")
        browse.clicked.connect(self.browse_torrents)
        self.preset = QComboBox()
        for k, v in PRESET_LABELS.items():
            self.preset.addItem(v, k)
        self.preset.setCurrentIndex(list(PRESET_LABELS).index(self.cfg["preset"]))
        self.preset.currentIndexChanged.connect(lambda _: self.engine.set_preset(self.preset.currentData()))
        self.iface = IfaceCombo(self.fill_ifaces)
        self.fill_ifaces()
        self.iface.currentIndexChanged.connect(self.iface_changed)
        for w, s in ((self.quick, 1), (add, 0), (browse, 0), (self.preset, 0), (self.iface, 0)):
            bar.addWidget(w, s)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setMinimumSectionSize(60)
        for c, w in ((1, 80), (2, 120), (3, 170), (4, 80), (5, 150)):
            h.setSectionResizeMode(c, QHeaderView.Fixed)
            self.table.setColumnWidth(c, w)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        lay.addWidget(self.table)
        self.setCentralWidget(canvas)

        # --- toolbar + menus
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        for text, fn in (("Pause / Resume", self.toggle_pause), ("Remove", self.remove_selected),
                         ("Open folder", self.open_folder), ("Inspect", self.show_inspector)):
            a = QAction(text, self)
            a.triggered.connect(fn)
            tb.addAction(a)
        m = self.menuBar().addMenu("Settings")
        m.addAction("Download folder…", self.choose_folder)
        m.addAction("VirusTotal API key…", self.set_vt_key)
        for text, key, cb in (("Require encryption (fewer peers)", "require_encryption", self.engine.set_encryption),
                              ("Keep seeding after a clean scan", "seed_after_finish", None),
                              ("Adaptive connection tuning", "adaptive", None)):
            a = QAction(text, self, checkable=True)
            a.setChecked(bool(self.cfg[key]))
            a.toggled.connect(lambda on, k=key, f=cb: self.set_flag(k, on, f))
            m.addAction(a)

        # --- inspector drawer
        self.dock = QDockWidget("Inspector", self)
        self.dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.tabs = QTabWidget()
        self.dock.setWidget(self.tabs)
        self.dock.setMinimumWidth(520)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()
        self.overview = QTextBrowser()
        self.tabs.addTab(self.overview, "Overview")
        peers_w = QWidget()
        pl = QVBoxLayout(peers_w)
        self.piece_map = PieceMap()
        pl.addWidget(QLabel("Piece map"))
        pl.addWidget(self.piece_map)
        self.peer_table = QTableWidget(0, 5)
        self.peer_table.setHorizontalHeaderLabels(["Peer", "Client", "↓", "↑", "Has"])
        self.peer_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.peer_table.verticalHeader().setVisible(False)
        self.peer_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        pl.addWidget(self.peer_table, 1)
        self.tabs.addTab(peers_w, "Peers and pieces")
        sec_w = QWidget()
        sl = QVBoxLayout(sec_w)
        self.sec_head = QLabel()
        self.sec_head.setTextFormat(Qt.RichText)
        self.sec_head.setWordWrap(True)
        sl.addWidget(self.sec_head)
        self.sec_table = QTableWidget(0, 5)
        self.sec_table.setHorizontalHeaderLabels(["File", "Risk", "SHA-256", "VirusTotal", "Why"])
        self.sec_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sec_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sec_table.verticalHeader().setVisible(False)
        sh = self.sec_table.horizontalHeader()
        sh.setSectionResizeMode(0, QHeaderView.Stretch)
        sh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        sh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        sh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        sh.setSectionResizeMode(4, QHeaderView.Stretch)
        sl.addWidget(self.sec_table, 2)
        self.audit_log = QPlainTextEdit(readOnly=True)
        sl.addWidget(self.audit_log, 1)
        row = QHBoxLayout()
        for text, name, fn in (("Rescan", "ghost", self.rescan), ("Release selected", "ghost", self.release_selected),
                               ("Delete selected", "danger", self.delete_selected)):
            b = QPushButton(text, objectName=name)
            b.clicked.connect(fn)
            row.addWidget(b)
        sl.addLayout(row)
        self.tabs.addTab(sec_w, "Security")

        self.statusBar()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self.engine.request_resume_save)
        self.save_timer.start(60_000)

    # --- adding
    def add_text(self, text):
        text = text.strip().strip('"')
        try:
            if text.lower().startswith("magnet:"):
                self.engine.add_magnet(text)
            elif text.lower().endswith(".torrent") and os.path.isfile(text):
                self.engine.add_file(text)
            else:
                QMessageBox.warning(self, "Not a torrent", "Paste a magnet link or the path to a .torrent file.")
                return False
        except Exception as e:
            QMessageBox.warning(self, "Could not add torrent", str(e))
            return False
        return True

    def on_external(self, items):
        """Called when another launch (magnet: click, .torrent double-click) is forwarded to this window."""
        for it in items:
            self.add_text(it)
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()

    def quick_add(self):
        if self.quick.text().strip() and self.add_text(self.quick.text()):
            self.quick.clear()

    def browse_torrents(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose .torrent file(s)", "", "Torrents (*.torrent)")
        for p in paths:
            self.add_text(p)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                self.add_text(u.toLocalFile() if u.isLocalFile() else u.toString())
        elif md.hasText():
            self.add_text(md.text())

    # --- settings
    def fill_ifaces(self):
        cur = self.cfg.get("interface", "")
        self.iface.blockSignals(True)
        self.iface.clear()
        self.iface.addItem("Any interface (no kill switch)", "")
        names = []
        for name, ip in list_interfaces():
            self.iface.addItem(f"Bind to {name} ({ip})", name)
            names.append(name)
        if cur and cur not in names:
            self.iface.addItem(f"Bind to {cur} (DOWN)", cur)
        i = self.iface.findData(cur)
        self.iface.setCurrentIndex(max(i, 0))
        self.iface.blockSignals(False)

    def iface_changed(self, _):
        self.engine.set_interface(self.iface.currentData())
        config.save(self.cfg)

    def set_flag(self, key, on, fn):
        self.cfg[key] = bool(on)
        if fn:
            fn(on)
        config.save(self.cfg)

    def choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Download folder", self.cfg["download_dir"])
        if d:
            self.cfg["download_dir"] = d
            config.save(self.cfg)

    def set_vt_key(self):
        key, ok = QInputDialog.getText(self, "VirusTotal API key",
                                       "Free key from virustotal.com (hash lookups only, nothing is uploaded):",
                                       QLineEdit.Password, self.cfg.get("vt_api_key", ""))
        if ok:
            self.cfg["vt_api_key"] = key.strip()
            config.save(self.cfg)

    # --- selection / actions
    def _selected_ih(self):
        r = self.table.currentRow()
        it = self.table.item(r, 0) if r >= 0 else None
        return it.data(Qt.UserRole) if it else None

    def _row_of(self, ih):
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.data(Qt.UserRole) == ih:
                return r
        return -1

    def selection_changed(self):
        if self._selected_ih() and self.dock.isVisible():
            self.refresh_inspector(force=True)

    def show_inspector(self):
        if self._selected_ih():
            self.dock.show()
            self.refresh_inspector(force=True)

    def toggle_pause(self):
        h = self.engine.handles.get(self._selected_ih())
        if h:
            h.resume() if h.status().flags & lt.torrent_flags.paused else h.pause()

    def remove_selected(self):
        ih = self._selected_ih()
        if ih:
            self.engine.remove(ih)

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.cfg["download_dir"]))

    def context_menu(self, pos):
        if not self._selected_ih():
            return
        m = QMenu(self)
        m.addAction("Inspect", self.show_inspector)
        m.addAction("Pause / Resume", self.toggle_pause)
        m.addAction("Open download folder", self.open_folder)
        m.addAction("Remove from list", self.remove_selected)
        m.exec(self.table.viewport().mapToGlobal(pos))

    # --- security
    def start_scan(self, ih, path):
        if ih in self.scanning:
            return
        self.scanning.add(ih)
        cfg = dict(self.cfg)

        def work():
            self.pipeline_done.emit(ih, security.run_pipeline(path, cfg))

        threading.Thread(target=work, daemon=True).start()

    def _on_pipeline_done(self, ih, report):
        self.scanning.discard(ih)
        self.reports[ih] = report
        h = self.engine.handles.get(ih)
        name = Path(report.root).name
        if report.verdict == "threat":
            self.statusBar().showMessage(f"THREAT in {name}: quarantined. Open the Inspector → Security tab.", 15000)
            QMessageBox.warning(self, "Threat flagged",
                                f"{name}\n\nSuspicious or malicious files were quarantined (renamed .quarantined, "
                                "execute permission removed). Review them in the Security tab.")
        else:
            self.statusBar().showMessage(f"{name}: {report.badge()}", 8000)
            if report.verdict == "clean" and self.cfg["seed_after_finish"] and h and h.is_valid():
                h.resume()
        self._shown_report = None

    def _current_report(self):
        return self.reports.get(self._selected_ih())

    def rescan(self):
        ih = self._selected_ih()
        h = self.engine.handles.get(ih)
        if h:
            s = h.status()
            self.start_scan(ih, os.path.join(s.save_path, s.name))

    def _selected_file(self):
        rep, r = self._current_report(), self.sec_table.currentRow()
        if rep and 0 <= r < len(rep.files):
            return rep, rep.files[r]
        return None, None

    def release_selected(self):
        rep, fr = self._selected_file()
        if fr and fr.quarantined:
            if QMessageBox.question(self, "Release file", f"Restore {fr.path}? Only do this if you trust it.") \
                    == QMessageBox.Yes:
                fr.abs_path = security.release_file(fr.quarantined)
                fr.quarantined = ""
                rep.log.append(f"Released {fr.path} by user")
                self._shown_report = None

    def delete_selected(self):
        rep, fr = self._selected_file()
        if fr and QMessageBox.question(self, "Delete file", f"Permanently delete {fr.path}?") == QMessageBox.Yes:
            security.delete_file(fr.quarantined or fr.abs_path)
            rep.log.append(f"Deleted {fr.path} by user")
            rep.files.remove(fr)
            self._shown_report = None

    # --- refresh
    def tick(self):
        for ih, save_path, name in self.engine.tick():
            self.start_scan(ih, os.path.join(save_path, name))
        self.sync_rows()
        e = self.engine
        kill = "   |   KILL SWITCH ENGAGED: interface down, traffic blocked" if e.kill else ""
        self.setWindowTitle(f"ApexTorrent  –  ↓ {fmt_rate(e.total_down)}  ↑ {fmt_rate(e.total_up)}")
        if not self.statusBar().currentMessage():
            self.statusBar().showMessage(
                f"Saving to {self.cfg['download_dir']}   |   Connections {e.total_conns}/{e.conn_limit}{kill}")
        if self.dock.isVisible():
            self.refresh_inspector()

    def sync_rows(self):
        handles = {ih: h for ih, h in self.engine.handles.items() if h.is_valid()}
        for r in reversed(range(self.table.rowCount())):
            it = self.table.item(r, 0)
            if it is None or it.data(Qt.UserRole) not in handles:
                self.table.removeRow(r)
        for ih, h in handles.items():
            r = self._row_of(ih)
            if r < 0:
                r = self.table.rowCount()
                self.table.insertRow(r)
                for c in range(len(COLS)):
                    self.table.setItem(r, c, QTableWidgetItem())
                self.table.item(r, 0).setData(Qt.UserRole, ih)
                pb = QProgressBar()
                pb.setRange(0, 1000)
                pb.setTextVisible(False)
                box = QWidget()
                bl = QHBoxLayout(box)
                bl.setContentsMargins(8, 0, 8, 0)
                bl.addWidget(pb, 0, Qt.AlignVCenter)
                box.bar = pb
                self.table.setCellWidget(r, 2, box)
            s = h.status()
            paused = bool(s.flags & lt.torrent_flags.paused)
            done = s.progress >= 1.0
            rate = s.download_rate
            if self.engine.kill and not done:
                eta = "VPN down"
            elif ih in self.engine.errors:
                eta = "Error"
            elif done:
                eta = "Done"
            elif paused:
                eta = "Paused"
            elif not s.has_metadata:
                eta = "Metadata…"
            elif rate > 0:
                eta = fmt_eta((s.total_wanted - s.total_wanted_done) / rate)
            else:
                eta = "Stalled" if s.num_peers == 0 else "Waiting"
            rep = self.reports.get(ih)
            if ih in self.scanning:
                badge, color = "Scanning…", BLUE
            elif rep:
                badge, color = rep.badge(), VERDICT_COLOR[rep.verdict]
            else:
                badge, color = "", GRAY
            vals = [s.name or "(fetching metadata…)", fmt_size(s.total_wanted) if s.has_metadata else "–", None,
                    f"↓ {fmt_rate(rate)}   ↑ {fmt_rate(s.upload_rate)}", eta, ("●  " + badge) if badge else ""]
            for c, v in enumerate(vals):
                if v is None:
                    self.table.cellWidget(r, c).bar.setValue(int(s.progress * 1000))
                    continue
                it = self.table.item(r, c)
                it.setText(v)
                if c == 5:
                    it.setForeground(QColor(color))

    def refresh_inspector(self, force=False):
        ih = self._selected_ih()
        if not ih or ih not in self.engine.handles:
            return
        h = self.engine.handles[ih]
        s = h.status()
        diag = "".join(
            f"<p><span style='color:{LEVEL[d['level']][0]}'>{LEVEL[d['level']][1]}</span> "
            f"<b>{esc(d['title'])}</b><br><span style='color:#8B949E'>{esc(d['advice'])}</span></p>"
            for d in self.engine.diagnostics(ih))
        trk = "".join(f"<li>{esc(t['url'])} <span style='color:#8B949E'>"
                      f"{'fails: ' + str(t['fails']) if t['fails'] else 'ok'} {esc(t['message'])}</span></li>"
                      for t in tracker_status(h)[:8])
        self.overview.setHtml(
            f"<h3>{esc(s.name or 'Fetching metadata…')}</h3>"
            f"<p style='color:#8B949E'>{esc(s.save_path)}<br>{fmt_size(s.total_wanted)} · "
            f"{s.progress * 100:.1f}% · seeds {s.num_seeds} · peers {s.num_peers} · "
            f"availability {max(s.distributed_copies, 0):.2f}</p>"
            f"<h4>Diagnostics</h4>{diag or '<p>Nothing to report.</p>'}"
            f"<h4>Trackers</h4><ul>{trk or '<li>none</li>'}</ul>")
        if self.tabs.currentIndex() == 1 or force:
            self.piece_map.set_pieces(self.engine.pieces(ih))
            peers = self.engine.peers(ih)
            self.peer_table.setRowCount(len(peers))
            for i, p in enumerate(peers):
                for c, v in enumerate((p["ip"], p["client"], fmt_rate(p["down"]), fmt_rate(p["up"]),
                                       f"{p['progress'] * 100:.0f}%")):
                    self.peer_table.setItem(i, c, QTableWidgetItem(v))
        rep = self.reports.get(ih)
        if id(rep) != self._shown_report or force:
            self._shown_report = id(rep)
            self.fill_security(rep, ih in self.scanning)

    def fill_security(self, rep, scanning):
        self.sec_table.setRowCount(0)
        self.audit_log.clear()
        if scanning:
            self.sec_head.setText("<b style='color:%s'>Scanning…</b>" % BLUE)
            return
        if rep is None:
            self.sec_head.setText("<span style='color:#8B949E'>No scan yet. It runs automatically when the "
                                  "download completes.</span>")
            return
        col = VERDICT_COLOR[rep.verdict]
        self.sec_head.setText(
            f"<span style='font-size:16px;color:{col}'><b>{esc(rep.badge())}</b></span><br>"
            f"<span style='color:#8B949E'>Antivirus: {esc(rep.av_detail or rep.av_status)}<br>"
            f"VirusTotal: {esc(rep.vt_status)}</span>")
        self.sec_table.setRowCount(len(rep.files))
        for i, fr in enumerate(rep.files):
            risk = "QUARANTINED" if fr.quarantined else (fr.worst() or "ok")
            if fr.av_hit:
                risk = "THREAT"
            vt = ""
            if fr.vt:
                vt = (f"{fr.vt['malicious']}/{fr.vt['total']}" if fr.vt["status"] == "found" else fr.vt["status"])
            why = "; ".join([f.reason for f in fr.findings] + ([fr.av_hit] if fr.av_hit else [])
                            + (fr.vt["signatures"][:3] if fr.vt and fr.vt.get("signatures") else []))
            for c, v in enumerate((fr.path, risk, fr.sha256[:16] + "…" if fr.sha256 else "", vt, why)):
                it = QTableWidgetItem(v)
                it.setToolTip(fr.sha256 if c == 2 else v)
                if c == 1:
                    it.setForeground(QColor(RED if risk in ("QUARANTINED", "THREAT", "high")
                                            else AMBER if risk == "medium" else GREEN if risk == "ok" else GRAY))
                self.sec_table.setItem(i, c, it)
        self.audit_log.setPlainText("\n".join(rep.log))

    def closeEvent(self, e):
        self.engine.shutdown()
        super().closeEvent(e)


def selftest(out_path):
    """Used by the build pipeline: proves the frozen bundle can load Qt, libtorrent and its assets."""
    try:
        import libtorrent as lt
        import psutil
        from PySide6 import __version__ as pyside_version
        from PySide6.QtGui import QImageReader

        app = QApplication.instance() or QApplication([])  # fails here if the Qt platform plugin is missing
        icon = app_icon()
        if icon.pixmap(32, 32).isNull():
            raise RuntimeError("application icon failed to load")
        lt.session({"listen_interfaces": "127.0.0.1:0", "enable_dht": False, "enable_lsd": False,
                    "enable_upnp": False, "enable_natpmp": False})
        psutil.net_if_stats()
        w = QWidget()
        w.setWindowIcon(icon)
        w.resize(50, 50)
        w.grab()
        fmts = sorted(bytes(f).decode() for f in QImageReader.supportedImageFormats())
        res = (f"OK libtorrent={lt.__version__} pyside6={pyside_version} platform={app.platformName()} "
               f"ico={'ico' in fmts} svg={'svg' in fmts}")
    except Exception as e:
        res = f"FAIL {type(e).__name__}: {e}"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(res)
    return 0 if res.startswith("OK") else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        i = argv.index("--selftest")
        out = argv[i + 1] if i + 1 < len(argv) else os.path.join(os.environ.get("TEMP", "."), "apextorrent_selftest.txt")
        return selftest(out)
    items, minimized = ipc.parse_args(argv)
    _set_windows_app_id()
    app = QApplication(sys.argv[:1])
    name = ipc.server_name()
    if ipc.send_to_running(items, name):  # already running: hand over and exit
        return 0
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    server = ipc.InstanceServer(name, w)
    server.received.connect(w.on_external)
    for it in items:
        w.add_text(it)
    w.showMinimized() if minimized else w.show()
    return app.exec()
