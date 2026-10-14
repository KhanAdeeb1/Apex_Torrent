"""ApexTorrent GUI (PySide6): live throughput header, torrent list, slide-in inspector, settings sheet."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import libtorrent as lt
from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor, QDesktopServices, QFontMetrics, QGuiApplication, QIcon, QKeySequence, QPainter, QPalette, QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

import config
import ipc
import security
from engine import PRESET_LABELS, Engine, list_interfaces, tracker_status
from ui_kit import (
    MED, SEMI, C, DropOverlay, EmptyState, Hero, Segmented, Switch, Toast, glyph_icon, paint_glyph, rgba,
    ui_font,
)

_QSS = """
* { color: @text; outline: 0; }
QMainWindow, QDialog, QMessageBox, QInputDialog, QWidget#root { background: @canvas; }
QLabel { background: transparent; }
QToolTip { background: @raised2; color: @text; border: 1px solid @hair2; border-radius: 8px; padding: 6px 9px; }

QFrame#addbar { background: @raised; border: 1px solid @hair; border-radius: 16px; }
QFrame#addbar[focused="true"] { background: @surface; border: 1px solid @accent; }
QLineEdit#bar { background: transparent; border: none; font-size: 15px; padding: 0 4px;
                selection-background-color: @accent; }
QLineEdit { background: @raised; border: 1px solid @hair; border-radius: 10px; padding: 8px 12px;
            selection-background-color: @accent; }
QLineEdit:focus { border: 1px solid @accent; }

QPushButton { background: @raised2; color: @text; border: none; border-radius: 10px; padding: 8px 16px;
              font-weight: 600; }
QPushButton:hover { background: #2A303B; }
QPushButton:pressed { background: #232832; }
QPushButton:disabled { background: @raised; color: @text3; }
QPushButton#primary { background: @accent; color: #FFFFFF; }
QPushButton#primary:hover { background: #2D97FF; }
QPushButton#primary:pressed { background: #0873E0; }
QPushButton#primary:disabled { background: @raised2; color: @text3; }
QPushButton#plain { background: transparent; color: @text2; font-weight: 500; }
QPushButton#plain:hover { background: rgba(255,255,255,7%); color: @text; }
QPushButton#danger { background: rgba(255,69,58,14%); color: @red; }
QPushButton#danger:hover { background: rgba(255,69,58,26%); }
QPushButton#danger:disabled { background: @raised; color: @text3; }
QPushButton#pill { background: @raised; border: 1px solid @hair; border-radius: 20px; padding: 6px 16px 6px 12px;
                   color: @text2; font-weight: 500; }
QPushButton#pill:hover { color: @text; border: 1px solid @hair2; }

QToolButton { background: transparent; border: none; border-radius: 10px; padding: 6px; }
QToolButton:hover { background: rgba(255,255,255,8%); }
QToolButton#rowbtn { border-radius: 15px; padding: 0; }

QFrame#seg { background: @raised; border: 1px solid @hair; border-radius: 12px; }
QPushButton#segbtn { background: transparent; color: @text2; border-radius: 9px; padding: 6px 14px;
                     font-weight: 500; }
QPushButton#segbtn:hover { color: @text; }
QPushButton#segbtn:checked { background: @raised2; color: @text; font-weight: 600; }

QFrame#footer { background: @canvas; border-top: 1px solid @hair; }
QFrame#inspector { background: @surface; border-left: 1px solid @hair; }
QFrame#banner { background: rgba(255,69,58,12%); border: 1px solid rgba(255,69,58,35%); border-radius: 14px; }
QFrame#rule { background: @hair; max-height: 1px; min-height: 1px; border: none; }

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 12px; background: transparent; margin: 6px 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,14%); border-radius: 4px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,26%); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { height: 0; }

QTableWidget { background: transparent; border: none; gridline-color: transparent;
               selection-background-color: rgba(10,132,255,20%); selection-color: @text; }
QTableWidget::item { padding: 0 10px; border: none; border-radius: 8px; }
QHeaderView { background: transparent; }
QHeaderView::section { background: transparent; color: @text3; border: none; padding: 8px 10px;
                       font-weight: 500; }
QPlainTextEdit { background: @canvas; border: 1px solid @hair; border-radius: 12px; padding: 8px 10px;
                 font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; font-size: 12px;
                 color: @text2; }

QMenu { background: @raised2; border: 1px solid @hair2; border-radius: 12px; padding: 6px; }
QMenu::item { padding: 8px 20px 8px 14px; border-radius: 8px; color: @text; }
QMenu::item:selected { background: @accent; color: #FFFFFF; }
QMenu::separator { height: 1px; background: @hair2; margin: 6px 8px; }

QMessageBox QLabel { color: @text; font-size: 13px; }
QMessageBox QPushButton, QInputDialog QPushButton { min-width: 84px; }
"""
_TOKENS = {k: v for k, v in vars(C).items() if not k.startswith("_")}
QSS = _QSS
for _k in sorted(_TOKENS, key=len, reverse=True):
    QSS = QSS.replace("@" + _k, _TOKENS[_k])

VERDICT = {  # verdict -> (label, color, glyph)
    "clean": ("Clean", C.green, "check"),
    "suspicious": ("Suspicious", C.amber, "warning"),
    "threat": ("Threat", C.red, "warning"),
    "unverified": ("Unverified", C.text2, "shield"),
}
LEVEL = {"ok": C.green, "info": C.accent, "warn": C.amber, "bad": C.red}
PRESET_SHORT = {"balanced": "Balanced", "max": "Max", "quiet": "Quiet"}
PRESET_TIPS = {
    "balanced": "Good default. No speed limits.",
    "max": "More connections and a deeper request queue. Uses more CPU and memory.",
    "quiet": "Caps download at 4 MB/s and upload at 128 KB/s so other things keep working.",
}


# ----------------------------------------------------------------------------- helpers
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
            return f"{n:.1f} {u}" if u != "B" else f"{int(n)} B"
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


def apply_dark_palette(app):
    p = QPalette()
    for role, col in ((QPalette.Window, C.canvas), (QPalette.WindowText, C.text), (QPalette.Base, C.raised),
                      (QPalette.AlternateBase, C.surface), (QPalette.Text, C.text), (QPalette.Button, C.raised2),
                      (QPalette.ButtonText, C.text), (QPalette.Highlight, C.accent),
                      (QPalette.HighlightedText, "#FFFFFF"), (QPalette.ToolTipBase, C.raised2),
                      (QPalette.ToolTipText, C.text), (QPalette.PlaceholderText, C.text3),
                      (QPalette.Link, C.accent), (QPalette.BrightText, "#FFFFFF")):
        p.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(C.text3))
    app.setPalette(p)
    app.setFont(ui_font(13))
    try:  # dark title bar on Windows 11 (Qt 6.8+)
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    except Exception:
        pass


class KeepColor(QStyledItemDelegate):
    """Selected table cells keep their own text color (the risk colors carry meaning)."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        fg = index.data(Qt.ForegroundRole)
        if fg is not None:
            option.palette.setBrush(QPalette.HighlightedText, fg)


class GlyphTile(QWidget):
    def __init__(self, size=48):
        super().__init__()
        self.setFixedSize(size, size)
        self.glyph, self.color = "shield", C.text2

    def set(self, glyph, color):
        self.glyph, self.color = glyph, color
        self.update()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        qp.setPen(Qt.NoPen)
        qp.setBrush(rgba(self.color, 0.16))
        qp.drawRoundedRect(r, r.width() * 0.28, r.width() * 0.28)
        s = r.width() * 0.5
        paint_glyph(qp, self.glyph, QRectF((r.width() - s) / 2, (r.height() - s) / 2, s, s), self.color, 1.8)


class PieceMap(QWidget):
    def __init__(self):
        super().__init__()
        self.pieces = []
        self.setMinimumHeight(112)

    def set_pieces(self, pieces):
        self.pieces = pieces
        self.update()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setPen(Qt.NoPen)
        qp.setBrush(C.canvas)
        qp.drawRoundedRect(QRectF(self.rect()), 12, 12)
        n = len(self.pieces)
        if not n:
            return
        cell, pad = 9, 10
        cols = max(1, (self.width() - 2 * pad) // cell)
        rows = max(1, (self.height() - 2 * pad) // cell)
        cells = min(cols * rows, n)
        per = n / cells
        for i in range(cells):
            a, b = int(i * per), max(int(i * per) + 1, int((i + 1) * per))
            seg = self.pieces[a:b]
            have = sum(1 for x in seg if x) / len(seg)
            col = QColor(C.accent) if have > 0 else QColor("#FFFFFF")
            col.setAlphaF(0.07 if have == 0 else 0.25 + 0.75 * have)
            qp.setBrush(col)
            qp.drawRoundedRect(QRectF(pad + (i % cols) * cell, pad + (i // cols) * cell, cell - 2, cell - 2), 2, 2)


# ----------------------------------------------------------------------------- one torrent in the list
class TorrentRow(QWidget):
    HEIGHT = 86
    selected = Signal(str)
    opened = Signal(str)
    menu = Signal(str, QPoint)
    act = Signal(str, str)

    def __init__(self, ih):
        super().__init__()
        self.ih = ih
        self.sel = self.hover = False
        self.d = dict(name="", size="", pct=0.0, down=0, up=0, eta="", eta_color=C.text2, color=C.accent,
                      glyph="down", pill=None, paused=False, done=False, subtitle_extra="")
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.btns = {}
        for key, tip in (("toggle", "Pause"), ("folder", "Show in folder"), ("remove", "Remove from list")):
            b = QToolButton(self)
            b.setObjectName("rowbtn")
            b.setFixedSize(30, 30)
            b.setIconSize(b.size() * 0.6)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self.act.emit(self.ih, k))
            b.hide()
            self.btns[key] = b
        self.btns["folder"].setIcon(glyph_icon("folder", C.text2, 18))
        self.btns["remove"].setIcon(glyph_icon("trash", C.text2, 18))
        self.btns["toggle"].setIcon(glyph_icon("pause", C.text2, 18))
        self._toggle_state = "pause"

    def set_data(self, **kw):
        self.d.update(kw)
        want = "play" if self.d["paused"] else "pause"
        if want != self._toggle_state:
            self._toggle_state = want
            self.btns["toggle"].setIcon(glyph_icon(want, C.text2, 18))
            self.btns["toggle"].setToolTip("Resume" if want == "play" else "Pause")
        self.btns["toggle"].setVisible(self._buttons_wanted() and not self.d["done"])
        self._place_buttons()
        self.update()

    def set_selected(self, on):
        self.sel = on
        self._sync_buttons()
        self.update()

    def _buttons_wanted(self):
        return self.hover or self.sel

    def _sync_buttons(self):
        show = self._buttons_wanted()
        self.btns["folder"].setVisible(show)
        self.btns["remove"].setVisible(show)
        self.btns["toggle"].setVisible(show and not self.d["done"])

    def _place_buttons(self):
        x = self.width() - 24 - 30
        y = 35 + (7 if self.d["done"] else 0)
        for key in ("remove", "folder", "toggle"):
            self.btns[key].move(x, y)
            x -= 34

    def resizeEvent(self, _):
        self._place_buttons()

    def enterEvent(self, e):
        self.hover = True
        self._sync_buttons()
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self._sync_buttons()
        self.update()

    def mousePressEvent(self, e):
        if e.button() in (Qt.LeftButton, Qt.RightButton):
            self.selected.emit(self.ih)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.opened.emit(self.ih)

    def contextMenuEvent(self, e):
        self.selected.emit(self.ih)
        self.menu.emit(self.ih, e.globalPos())

    def paintEvent(self, _):
        d = self.d
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.TextAntialiasing)
        w = self.width()
        r = QRectF(8, 2, w - 16, self.height() - 4)
        if self.sel:
            qp.setPen(QPen(rgba(C.accent, 0.38), 1))
            qp.setBrush(rgba(C.accent, 0.12))
            qp.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        elif self.hover:
            qp.setPen(Qt.NoPen)
            qp.setBrush(rgba("#FFFFFF", 0.04))
            qp.drawRoundedRect(r, 16, 16)

        color = QColor(d["color"])
        # tile
        tile = QRectF(24, (self.height() - 46) / 2, 46, 46)
        qp.setPen(Qt.NoPen)
        qp.setBrush(rgba(color, 0.16))
        qp.drawRoundedRect(tile, 13, 13)
        paint_glyph(qp, d["glyph"], QRectF(tile.x() + 12, tile.y() + 12, 22, 22), color, 1.9)

        left = 86
        right = w - 28
        off = 7 if d["done"] else 0  # finished rows have no bar, so their text sits centered
        # status pill (top right)
        name_right = right
        if d["pill"]:
            text, pc = d["pill"]
            qp.setFont(ui_font(12, SEMI))
            fm = qp.fontMetrics()
            pw = fm.horizontalAdvance(text) + 36
            pr = QRectF(right - pw, 15 + off, pw, 25)
            qp.setPen(Qt.NoPen)
            qp.setBrush(rgba(pc, 0.15))
            qp.drawRoundedRect(pr, 12.5, 12.5)
            qp.setBrush(QColor(pc))
            qp.drawEllipse(QRectF(pr.x() + 11, pr.center().y() - 3, 6, 6))
            qp.setPen(QColor(pc))
            qp.drawText(QRectF(pr.x() + 22, pr.y(), pr.width() - 26, pr.height()), Qt.AlignVCenter | Qt.AlignLeft, text)
            name_right = pr.x() - 14

        # name
        qp.setFont(ui_font(15, SEMI))
        qp.setPen(C.text)
        name = d["name"] or "Fetching metadata…"
        fm = qp.fontMetrics()
        qp.drawText(QRectF(left, 14 + off, name_right - left, 26), Qt.AlignVCenter | Qt.AlignLeft,
                    fm.elidedText(name, Qt.ElideMiddle, int(name_right - left)))

        # subtitle: runs separated by space, not punctuation
        x = float(left)
        y = 40 + off
        sub_right = right - (3 * 34 if self._buttons_wanted() else 0) - 8
        qp.setFont(ui_font(13))
        runs = []
        if d["size"]:
            runs.append((None, d["size"], C.text2))
        if not d["done"] and d["pct"] > 0:
            runs.append((None, f"{d['pct'] * 100:.0f}%", C.text2))
        if d["down"] > 0:
            runs.append(("down", fmt_rate(d["down"]), C.accent))
        if d["up"] > 0:
            runs.append(("up", fmt_rate(d["up"]), C.cyan))
        if d["eta"]:
            runs.append((None, d["eta"], d["eta_color"]))
        fm = qp.fontMetrics()
        for glyph, text, col in runs:
            tw = fm.horizontalAdvance(text)
            need = tw + (18 if glyph else 0)
            if x + need > sub_right:
                break
            if glyph:
                paint_glyph(qp, glyph, QRectF(x, y + 3, 13, 13), col, 2.1)
                x += 17
            qp.setPen(QColor(col))
            qp.drawText(QRectF(x, y, tw + 4, 20), Qt.AlignVCenter | Qt.AlignLeft, text)
            x += tw + 20

        if d["done"]:
            return
        # progress bar
        bar = QRectF(left, 66, right - left, 5)
        qp.setPen(Qt.NoPen)
        qp.setBrush(rgba("#FFFFFF", 0.07))
        qp.drawRoundedRect(bar, 2.5, 2.5)
        if d["pct"] > 0:
            fillw = max(5.0, bar.width() * min(1.0, d["pct"]))
            qp.setBrush(color)
            qp.drawRoundedRect(QRectF(bar.x(), bar.y(), fillw, bar.height()), 2.5, 2.5)


# ----------------------------------------------------------------------------- settings sheet
class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(0)
        title = QLabel("Settings")
        title.setFont(ui_font(22, SEMI))
        lay.addWidget(title)
        lay.addSpacing(8)

        self.folder_lbl = QLabel()
        change = QPushButton("Change…")
        change.clicked.connect(self._pick_folder)
        self._section(lay, "Downloads")
        self._row(lay, "Download folder", self.folder_lbl, change, mono_desc=True)

        self._section(lay, "Security")
        self.vt = QLineEdit(win.cfg.get("vt_api_key", ""))
        self.vt.setEchoMode(QLineEdit.Password)
        self.vt.setPlaceholderText("Paste your key")
        self.vt.setMinimumHeight(40)
        self.vt.editingFinished.connect(self._save_vt)
        self._row(lay, "VirusTotal API key", "Optional. Checks file hashes against VirusTotal. Your files are never uploaded.", self.vt, below=True)

        self._section(lay, "Network")
        self._switch(lay, "Require encryption", "Only connect to peers that support it. You will find fewer peers.",
                     "require_encryption", win.engine.set_encryption)
        self._switch(lay, "Adaptive tuning", "Raises and lowers connection limits automatically as conditions change.",
                     "adaptive", None)

        self._section(lay, "Seeding")
        self._switch(lay, "Keep seeding after a clean scan",
                     "Torrents resume seeding only when the scan finds nothing wrong.", "seed_after_finish", None)

        lay.addSpacing(22)
        row = QHBoxLayout()
        row.addStretch(1)
        done = QPushButton("Done")
        done.setObjectName("primary")
        done.setMinimumWidth(110)
        done.clicked.connect(self.accept)
        row.addWidget(done)
        lay.addLayout(row)
        self._show_folder()

    def _section(self, lay, text):
        lay.addSpacing(20)
        h = QLabel(text)
        h.setFont(ui_font(14, SEMI))
        h.setStyleSheet(f"color:{C.text2}")
        lay.addWidget(h)
        lay.addSpacing(6)

    def _row(self, lay, title, desc, control, mono_desc=False, below=False):
        box = QFrame()
        box.setObjectName("setrow")
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 10, 0, 10)
        h.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(3)
        t = QLabel(title)
        t.setFont(ui_font(14, MED))
        col.addWidget(t)
        if isinstance(desc, QLabel):
            d = desc
        else:
            d = QLabel(desc)
        d.setStyleSheet(f"color:{C.text3}; font-size:12px;")
        col.addWidget(d)
        if below:
            col.addSpacing(6)
            col.addWidget(control)
            h.addLayout(col, 1)
        else:
            h.addLayout(col, 1)
            h.addWidget(control, 0, Qt.AlignVCenter)
        lay.addWidget(box)
        rule = QFrame()
        rule.setObjectName("rule")
        lay.addWidget(rule)

    def _switch(self, lay, title, desc, key, cb):
        sw = Switch(bool(self.win.cfg.get(key)))
        sw.toggled.connect(lambda on, k=key, f=cb: self.win.set_flag(k, on, f))
        self._row(lay, title, desc, sw)

    def _show_folder(self):
        p = self.win.cfg["download_dir"]
        fm = QFontMetrics(self.folder_lbl.font())
        self.folder_lbl.setText(fm.elidedText(p, Qt.ElideMiddle, 330))
        self.folder_lbl.setToolTip(p)

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Download folder", self.win.cfg["download_dir"])
        if d:
            self.win.cfg["download_dir"] = d
            config.save(self.win.cfg)
            self._show_folder()
            self.win.update_footer()

    def _save_vt(self):
        self.win.cfg["vt_api_key"] = self.vt.text().strip()
        config.save(self.win.cfg)

    def done(self, r):
        self._save_vt()
        super().done(r)


# ----------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    pipeline_done = Signal(str, object)
    PANEL_W = 460

    def __init__(self, engine_factory=Engine):
        super().__init__()
        self.cfg = config.load()
        self.engine = engine_factory(self.cfg)
        self.reports, self.scanning = {}, set()
        self.rows = {}
        self.sel_ih = None
        self._shown_report = None
        self._ov_html = {}
        self.inspector_open = False
        self.pipeline_done.connect(self._on_pipeline_done)
        self.setWindowTitle("ApexTorrent")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 600)
        self.resize(1120, 740)
        self.setAcceptDrops(True)

        root = QWidget(objectName="root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        main = QWidget()
        col = QVBoxLayout(main)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        outer.addWidget(main, 1)
        self.main_col = main

        # --- live header
        self.hero = Hero()
        col.addWidget(self.hero)

        # --- add bar
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(28, 4, 28, 0)
        self.addbar = QFrame(objectName="addbar")
        self.addbar.setFixedHeight(58)
        bl = QHBoxLayout(self.addbar)
        bl.setContentsMargins(18, 0, 9, 0)
        bl.setSpacing(8)
        lk = QLabel()
        lk.setPixmap(glyph_icon("link", C.text3, 20).pixmap(20, 20))
        bl.addWidget(lk)
        self.quick = QLineEdit(objectName="bar")
        self.quick.setPlaceholderText("Paste a magnet link or drop a .torrent file")
        self.quick.returnPressed.connect(self.quick_add)
        self.quick.textChanged.connect(lambda t: self.add_btn.setEnabled(bool(t.strip())))
        self.quick.installEventFilter(self)
        bl.addWidget(self.quick, 1)
        browse = QPushButton("Browse…", objectName="plain")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self.browse_torrents)
        bl.addWidget(browse)
        self.add_btn = QPushButton("Add", objectName="primary")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setFixedSize(84, 40)
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.quick_add)
        bl.addWidget(self.add_btn)
        wl.addWidget(self.addbar)
        col.addWidget(wrap)

        # --- filters
        fw = QWidget()
        fl = QHBoxLayout(fw)
        fl.setContentsMargins(28, 18, 28, 8)
        self.filter = Segmented([("all", "All"), ("active", "Active"), ("done", "Completed")])
        self.filter.changed.connect(lambda _: self.apply_filter())
        fl.addWidget(self.filter)
        fl.addStretch(1)
        col.addWidget(fw)

        # --- kill-switch banner
        bw = QWidget()
        bwl = QHBoxLayout(bw)
        bwl.setContentsMargins(28, 0, 28, 8)
        self.banner = QFrame(objectName="banner")
        bnl = QHBoxLayout(self.banner)
        bnl.setContentsMargins(16, 12, 16, 12)
        bi = QLabel()
        bi.setPixmap(glyph_icon("lock", C.red, 20).pixmap(20, 20))
        bnl.addWidget(bi)
        bt = QLabel("Your VPN adapter is down. Traffic is blocked and downloads are paused until it comes back.")
        bt.setWordWrap(True)
        bnl.addWidget(bt, 1)
        bwl.addWidget(self.banner)
        self.banner.hide()
        col.addWidget(bw)

        # --- list / empty state
        self.stack = QStackedWidget()
        self.empty = EmptyState()
        self.stack.addWidget(self.empty)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        self.list_l = QVBoxLayout(inner)
        self.list_l.setContentsMargins(20, 2, 20, 14)
        self.list_l.setSpacing(2)
        self.list_l.addStretch(1)
        self.scroll.setWidget(inner)
        self.stack.addWidget(self.scroll)
        col.addWidget(self.stack, 1)

        # --- footer
        self.footer = QFrame(objectName="footer")
        self.footer.setFixedHeight(62)
        ftl = QHBoxLayout(self.footer)
        ftl.setContentsMargins(24, 0, 20, 0)
        ftl.setSpacing(12)
        self.preset = Segmented([(k, PRESET_SHORT.get(k, v)) for k, v in PRESET_LABELS.items()],
                                self.cfg["preset"] if self.cfg["preset"] in PRESET_LABELS else "balanced")
        for k in PRESET_LABELS:
            self.preset.set_tip(k, PRESET_TIPS.get(k, ""))
        self.preset.changed.connect(self.engine.set_preset)
        ftl.addWidget(self.preset)
        self.net_btn = QPushButton(objectName="pill")
        self.net_btn.setCursor(Qt.PointingHandCursor)
        self.net_btn.setFixedHeight(40)
        self.net_btn.clicked.connect(self.open_network_menu)
        ftl.addWidget(self.net_btn)
        ftl.addStretch(1)
        self.conn_lbl = QLabel()
        self.conn_lbl.setStyleSheet(f"color:{C.text3}; font-size:12px;")
        ftl.addWidget(self.conn_lbl)
        self.folder_btn = QToolButton()
        self.folder_btn.setIcon(glyph_icon("folder", C.text2, 20))
        self.folder_btn.clicked.connect(self.open_folder)
        ftl.addWidget(self.folder_btn)
        self.gear_btn = QToolButton()
        self.gear_btn.setIcon(glyph_icon("sliders", C.text2, 20))
        self.gear_btn.setToolTip("Settings  (Ctrl+,)")
        self.gear_btn.clicked.connect(self.open_settings)
        ftl.addWidget(self.gear_btn)
        col.addWidget(self.footer)

        # --- inspector panel (slides in from the right)
        self.panel = QFrame(objectName="inspector")
        self.panel.setMinimumWidth(0)
        self.panel.setMaximumWidth(0)
        self.panel.hide()
        outer.addWidget(self.panel)
        self._build_inspector()
        self.slide = QPropertyAnimation(self.panel, b"maximumWidth", self)
        self.slide.setDuration(240)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        self.slide.finished.connect(self._slide_done)
        self.setCentralWidget(root)

        self.overlay = DropOverlay(main)
        self.toast = Toast(root)
        self.toast.setFont(ui_font(14, MED))

        for seq, fn in ((QKeySequence.Paste, self.paste_clipboard), (QKeySequence("Ctrl+,"), self.open_settings),
                        (QKeySequence(Qt.Key_Delete), self.remove_selected),
                        (QKeySequence(Qt.Key_Space), self.toggle_pause),
                        (QKeySequence(Qt.Key_Escape), self.close_inspector)):
            QShortcut(seq, self, activated=fn)

        self.fill_ifaces()
        self.update_footer()
        self.apply_filter()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self.engine.request_resume_save)
        self.save_timer.start(60_000)

    # --- inspector construction
    def _build_inspector(self):
        outer = QVBoxLayout(self.panel)
        outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget()
        inner.setFixedWidth(self.PANEL_W)
        outer.addWidget(inner)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(0)

        head = QHBoxLayout()
        self.insp_title = QLabel()
        self.insp_title.setFont(ui_font(18, SEMI))
        head.addWidget(self.insp_title, 1)
        close = QToolButton()
        close.setIcon(glyph_icon("close", C.text2, 18, 2.0))
        close.setToolTip("Close  (Esc)")
        close.clicked.connect(self.close_inspector)
        head.addWidget(close)
        lay.addLayout(head)
        lay.addSpacing(14)
        self.tabs = Segmented([("overview", "Overview"), ("peers", "Peers and pieces"), ("security", "Security")])
        self.tabs.changed.connect(self._tab_changed)
        lay.addWidget(self.tabs)
        lay.addSpacing(18)
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, 1)

        # overview
        ov = QWidget()
        ol = QVBoxLayout(ov)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(18)
        self.stat = {}
        for i, key in enumerate(("Size", "Downloaded", "Uploaded", "Seeds", "Peers", "Availability")):
            v = QLabel("–")
            v.setFont(ui_font(19, SEMI))
            c = QLabel(key)
            c.setStyleSheet(f"color:{C.text3}; font-size:12px;")
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.addWidget(v)
            cell.addWidget(c)
            grid.addLayout(cell, i // 3, i % 3)
            self.stat[key] = v
        ol.addLayout(grid)
        ol.addSpacing(18)
        self.save_lbl = QLabel()
        self.save_lbl.setWordWrap(True)
        self.save_lbl.setStyleSheet(f"color:{C.text3}; font-size:12px;")
        ol.addWidget(self.save_lbl)
        ol.addSpacing(18)
        rule = QFrame(objectName="rule")
        ol.addWidget(rule)
        ol.addSpacing(16)
        dh = QLabel("Health")
        dh.setFont(ui_font(14, SEMI))
        ol.addWidget(dh)
        ol.addSpacing(8)
        self.diag_lbl = QLabel()
        self.diag_lbl.setWordWrap(True)
        self.diag_lbl.setTextFormat(Qt.RichText)
        self.diag_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        ol.addWidget(self.diag_lbl)
        ol.addSpacing(10)
        th = QLabel("Trackers")
        th.setFont(ui_font(14, SEMI))
        ol.addWidget(th)
        ol.addSpacing(8)
        self.trk_lbl = QLabel()
        self.trk_lbl.setWordWrap(True)
        self.trk_lbl.setTextFormat(Qt.RichText)
        self.trk_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        ol.addWidget(self.trk_lbl)
        ol.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(ov)
        self.pages.addWidget(sc)

        # peers and pieces
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(10)
        self.piece_map = PieceMap()
        pl.addWidget(self.piece_map)
        self.peer_table = self._table(["Peer", "Client", "Down", "Up", "Has"])
        ph = self.peer_table.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.Fixed)
        ph.setSectionResizeMode(1, QHeaderView.Stretch)
        for c, wd in ((0, 130), (2, 78), (3, 78), (4, 56)):
            ph.setSectionResizeMode(c, QHeaderView.Fixed)
            self.peer_table.setColumnWidth(c, wd)
        pl.addWidget(self.peer_table, 1)
        self.peer_empty = QLabel("No peers connected right now.")
        self.peer_empty.setAlignment(Qt.AlignCenter)
        self.peer_empty.setStyleSheet(f"color:{C.text3};")
        pl.addWidget(self.peer_empty)
        self.pages.addWidget(pw)

        # security
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        hl = QHBoxLayout()
        hl.setSpacing(14)
        self.verdict_tile = GlyphTile(52)
        hl.addWidget(self.verdict_tile, 0, Qt.AlignTop)
        vc = QVBoxLayout()
        vc.setSpacing(3)
        self.verdict_title = QLabel()
        self.verdict_title.setFont(ui_font(19, SEMI))
        self.verdict_sub = QLabel()
        self.verdict_sub.setWordWrap(True)
        self.verdict_sub.setStyleSheet(f"color:{C.text2}; font-size:12.5px;")
        vc.addWidget(self.verdict_title)
        vc.addWidget(self.verdict_sub)
        hl.addLayout(vc, 1)
        sl.addLayout(hl)
        sl.addSpacing(16)
        self.sec_table = self._table(["File", "Result"])
        self.sec_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sec_table.setSelectionMode(QTableWidget.SingleSelection)
        sh = self.sec_table.horizontalHeader()
        sh.setSectionResizeMode(0, QHeaderView.Stretch)
        sh.setSectionResizeMode(1, QHeaderView.Fixed)
        self.sec_table.setColumnWidth(1, 120)
        self.sec_table.setItemDelegate(KeepColor(self.sec_table))
        self.sec_table.itemSelectionChanged.connect(self._sec_selected)
        sl.addWidget(self.sec_table, 3)
        sl.addSpacing(10)
        self.file_detail = QLabel("Select a file to see why it got its result.")
        self.file_detail.setWordWrap(True)
        self.file_detail.setTextFormat(Qt.RichText)
        self.file_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.file_detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.file_detail.setStyleSheet(f"color:{C.text2}; font-size:12.5px;")
        sl.addWidget(self.file_detail, 2)
        self.log_toggle = QPushButton("Show scan log", objectName="plain")
        self.log_toggle.setStyleSheet("padding: 8px 2px;")
        self.log_toggle.setCursor(Qt.PointingHandCursor)
        self.log_toggle.clicked.connect(self._toggle_log)
        sl.addWidget(self.log_toggle, 0, Qt.AlignLeft)
        self.audit_log = QPlainTextEdit(readOnly=True)
        self.audit_log.setFixedHeight(130)
        self.audit_log.hide()
        sl.addWidget(self.audit_log)
        sl.addSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.rescan_btn = QPushButton("Scan again")
        self.rescan_btn.clicked.connect(self.rescan)
        self.release_btn = QPushButton("Release")
        self.release_btn.setToolTip("Restore the selected quarantined file. Only do this if you trust it.")
        self.release_btn.clicked.connect(self.release_selected)
        self.delete_btn = QPushButton("Delete", objectName="danger")
        self.delete_btn.setToolTip("Permanently delete the selected file.")
        self.delete_btn.clicked.connect(self.delete_selected)
        for b in (self.rescan_btn, self.release_btn, self.delete_btn):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        sl.addLayout(row)
        self.pages.addWidget(sw)
        self._sec_selected()

    def _table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setSelectionMode(QTableWidget.NoSelection)
        t.setShowGrid(False)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(38)
        t.setFocusPolicy(Qt.NoFocus)
        t.horizontalHeader().setHighlightSections(False)
        t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        return t

    # --- window events
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.overlay.setGeometry(self.main_col.rect())
        self.toast.place()

    def eventFilter(self, obj, ev):
        if obj is self.quick and ev.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self.addbar.setProperty("focused", ev.type() == QEvent.FocusIn)
            self.addbar.style().unpolish(self.addbar)
            self.addbar.style().polish(self.addbar)
        return super().eventFilter(obj, ev)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() or e.mimeData().hasText():
            e.acceptProposedAction()
            self.overlay.setGeometry(self.main_col.rect())
            self.overlay.show()
            self.overlay.raise_()

    def dragLeaveEvent(self, e):
        self.overlay.hide()

    def dropEvent(self, e):
        self.overlay.hide()
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                self.add_text(u.toLocalFile() if u.isLocalFile() else u.toString())
        elif md.hasText():
            self.add_text(md.text())

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
        self.sync_rows()
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
            self.toast.show_message("Added. It will start as soon as peers are found.", "ok", 3500)

    def paste_clipboard(self):
        text = (QGuiApplication.clipboard().text() or "").strip()
        if text.lower().startswith("magnet:") and self.add_text(text):
            self.toast.show_message("Added from clipboard.", "ok", 3000)
        else:
            self.quick.setFocus()
            if text:
                self.quick.setText(text)

    def browse_torrents(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose .torrent file(s)", "", "Torrents (*.torrent)")
        for p in paths:
            self.add_text(p)

    # --- settings
    def open_settings(self):
        SettingsDialog(self).exec()
        self.update_footer()

    def set_flag(self, key, on, fn):
        self.cfg[key] = bool(on)
        if fn:
            fn(on)
        config.save(self.cfg)

    def fill_ifaces(self):
        cur = self.cfg.get("interface", "")
        if cur:
            self.net_btn.setIcon(glyph_icon("lock", C.green, 16, 2.0))
            self.net_btn.setText(f"Bound to {cur}")
            self.net_btn.setToolTip("Kill switch is on. If this adapter goes down, everything pauses.")
        else:
            self.net_btn.setIcon(glyph_icon("globe", C.text2, 16, 1.9))
            self.net_btn.setText("Any network")
            self.net_btn.setToolTip("Pick your VPN adapter to turn on the kill switch.")

    def open_network_menu(self):
        cur = self.cfg.get("interface", "")
        m = QMenu(self)
        a = m.addAction("Any network (no kill switch)")
        a.setCheckable(True)
        a.setChecked(not cur)
        a.triggered.connect(lambda: self.set_interface(""))
        m.addSeparator()
        names = []
        for name, ip in list_interfaces():
            names.append(name)
            act = m.addAction(f"Bind to {name}  ({ip})")
            act.setCheckable(True)
            act.setChecked(name == cur)
            act.triggered.connect(lambda _=False, n=name: self.set_interface(n))
        if cur and cur not in names:
            act = m.addAction(f"{cur}  (disconnected)")
            act.setCheckable(True)
            act.setChecked(True)
        if not names and not cur:
            m.addAction("No active network adapters found").setEnabled(False)
        m.exec(self.net_btn.mapToGlobal(QPoint(0, -m.sizeHint().height() - 8)))

    def set_interface(self, name):
        self.cfg["interface"] = name
        self.engine.set_interface(name)
        config.save(self.cfg)
        self.fill_ifaces()
        self.toast.show_message(f"Traffic is now bound to {name}." if name else "Kill switch is off.", "info", 3500)

    def iface_changed(self, *_):  # kept for API compatibility
        self.fill_ifaces()

    def update_footer(self):
        e = self.engine
        self.conn_lbl.setText(f"{e.total_conns} of {e.conn_limit} connections")
        self.folder_btn.setToolTip(f"Open {self.cfg['download_dir']}")

    # --- selection / actions
    def _selected_ih(self):
        return self.sel_ih if self.sel_ih in self.engine.handles else None

    def select(self, ih):
        self.sel_ih = ih
        for k, r in self.rows.items():
            r.set_selected(k == ih)
        if self.inspector_open:
            self.refresh_inspector(force=True)

    def row_count(self):
        return len(self.rows)

    def show_inspector(self, ih=None):
        ih = ih if isinstance(ih, str) else self._selected_ih()
        if not ih:
            return
        if ih != self.sel_ih:
            self.select(ih)
        self.refresh_inspector(force=True)
        if not self.inspector_open:
            self.inspector_open = True
            self.panel.show()
            self._animate_panel(self.PANEL_W)

    def close_inspector(self):
        if self.inspector_open:
            self.inspector_open = False
            self._animate_panel(0)

    def _animate_panel(self, target):
        self.slide.stop()
        self.slide.setStartValue(self.panel.maximumWidth())
        self.slide.setEndValue(target)
        self.slide.start()

    def _slide_done(self):
        if not self.inspector_open:
            self.panel.hide()

    def set_inspector_tab(self, key):
        self.tabs.set(key)
        self._tab_changed(key)

    def _tab_changed(self, key):
        self.pages.setCurrentIndex({"overview": 0, "peers": 1, "security": 2}[key])
        self.refresh_inspector(force=True)

    def toggle_pause(self, ih=None):
        ih = ih if isinstance(ih, str) else self._selected_ih()
        h = self.engine.handles.get(ih)
        if h:
            h.resume() if h.status().flags & lt.torrent_flags.paused else h.pause()
            self.sync_rows()

    def remove_selected(self, ih=None):
        ih = ih if isinstance(ih, str) else self._selected_ih()
        if ih:
            self.engine.remove(ih)
            if self.sel_ih == ih:
                self.sel_ih = None
                self.close_inspector()
            self.sync_rows()
            self.toast.show_message("Removed from the list. Downloaded files were kept.", "info", 3500)

    def open_folder(self, ih=None):
        path = self.cfg["download_dir"]
        h = self.engine.handles.get(ih) if isinstance(ih, str) else None
        if h and h.is_valid():
            s = h.status()
            full = os.path.join(s.save_path, s.name) if s.name else s.save_path
            path = full if os.path.exists(full) else s.save_path
            if os.path.isfile(path):
                path = os.path.dirname(path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _row_action(self, ih, action):
        {"toggle": self.toggle_pause, "folder": self.open_folder, "remove": self.remove_selected}[action](ih)

    def context_menu(self, ih, pos):
        m = QMenu(self)
        m.addAction("Inspect", lambda: self.show_inspector(ih))
        m.addAction("Pause / Resume", lambda: self.toggle_pause(ih))
        m.addAction("Show in folder", lambda: self.open_folder(ih))
        m.addSeparator()
        m.addAction("Remove from list", lambda: self.remove_selected(ih))
        m.exec(pos)

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
            self.toast.show_message(f"Threat in {name}. Files were quarantined.", "bad", 9000)
            QMessageBox.warning(self, "Threat flagged",
                                f"{name}\n\nSuspicious or malicious files were quarantined (renamed .quarantined, "
                                "execute permission removed). Review them in the Security tab.")
        else:
            label, _, _ = VERDICT[report.verdict]
            kind = {"clean": "ok", "suspicious": "warn"}.get(report.verdict, "info")
            self.toast.show_message(f"{name}: {label}", kind, 5000)
            if report.verdict == "clean" and self.cfg["seed_after_finish"] and h and h.is_valid():
                h.resume()
        self._shown_report = None
        self.sync_rows()

    def _current_report(self):
        return self.reports.get(self._selected_ih())

    def rescan(self):
        ih = self._selected_ih()
        h = self.engine.handles.get(ih)
        if h:
            s = h.status()
            self.start_scan(ih, os.path.join(s.save_path, s.name))
            self._shown_report = None

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
                self.refresh_inspector(force=True)

    def delete_selected(self):
        rep, fr = self._selected_file()
        if fr and QMessageBox.question(self, "Delete file", f"Permanently delete {fr.path}?") == QMessageBox.Yes:
            security.delete_file(fr.quarantined or fr.abs_path)
            rep.log.append(f"Deleted {fr.path} by user")
            rep.files.remove(fr)
            self._shown_report = None
            self.refresh_inspector(force=True)

    # --- refresh
    def tick(self):
        for ih, save_path, name in self.engine.tick():
            self.start_scan(ih, os.path.join(save_path, name))
        self.sync_rows()
        e = self.engine
        self.hero.push(e.total_down, e.total_up)
        self.banner.setVisible(bool(e.kill))
        self.update_footer()
        if e.total_down > 0 or e.total_up > 0:
            self.setWindowTitle(f"ApexTorrent  –  ↓ {fmt_rate(e.total_down)}  ↑ {fmt_rate(e.total_up)}")
        else:
            self.setWindowTitle("ApexTorrent")
        if self.inspector_open:
            self.refresh_inspector()

    def apply_filter(self):
        mode = self.filter.value
        shown = 0
        for ih, r in self.rows.items():
            ok = mode == "all" or (mode == "done") == bool(r.d["done"])
            r.setVisible(ok)
            shown += ok
        if not self.rows:
            self.empty.set_text("Add your first download",
                                "Paste a magnet link above, drop a .torrent file on this window, or press Ctrl+V.")
        elif not shown:
            self.empty.set_text("Nothing here", "No torrents match this filter.")
        self.stack.setCurrentIndex(1 if shown else 0)

    def sync_rows(self):
        handles = {ih: h for ih, h in self.engine.handles.items() if h.is_valid()}
        for ih in [k for k in self.rows if k not in handles]:
            r = self.rows.pop(ih)
            self.list_l.removeWidget(r)
            r.deleteLater()
        for ih in handles:
            if ih not in self.rows:
                r = TorrentRow(ih)
                r.selected.connect(self.select)
                r.opened.connect(self.show_inspector)
                r.menu.connect(self.context_menu)
                r.act.connect(self._row_action)
                self.rows[ih] = r
                self.list_l.insertWidget(0, r)
                r.set_selected(ih == self.sel_ih)
        counts = {"all": 0, "active": 0, "done": 0}
        for ih, h in handles.items():
            s = h.status()
            paused = bool(s.flags & lt.torrent_flags.paused)
            done = s.progress >= 1.0
            rate = s.download_rate
            glyph, color = "down", C.accent
            if self.engine.kill and not done:
                eta, ec, glyph, color = "VPN down", C.red, "lock", C.red
            elif ih in self.engine.errors:
                eta, ec, glyph, color = "Error", C.red, "warning", C.red
            elif done:
                eta, ec, glyph, color = "Completed", C.green, "check", C.green
            elif paused:
                eta, ec, glyph, color = "Paused", C.amber, "pause", C.amber
            elif not s.has_metadata:
                eta, ec, glyph, color = "Fetching metadata", C.text2, "clock", C.text2
            elif rate > 0:
                eta, ec = fmt_eta((s.total_wanted - s.total_wanted_done) / rate) + " left", C.text2
            elif s.num_peers == 0:
                eta, ec = "No peers yet", C.amber
            else:
                eta, ec = "Connecting", C.text2
            rep = self.reports.get(ih)
            pill = None
            if ih in self.scanning:
                pill = ("Scanning", C.accent)
                if done:
                    glyph, color = "shield", C.accent
            elif rep:
                label, vcol, vglyph = VERDICT[rep.verdict]
                pill = (label, vcol)
                if done:
                    glyph, color = vglyph, vcol
            row = self.rows[ih]
            row.set_data(name=s.name, size=fmt_size(s.total_wanted) if s.has_metadata else "", pct=s.progress,
                         down=rate, up=s.upload_rate, eta=eta, eta_color=ec, color=color, glyph=glyph, pill=pill,
                         paused=paused, done=done)
            if rep:
                row.setToolTip(rep.badge())
            counts["all"] += 1
            counts["done" if done else "active"] += 1
        for k, label in (("all", "All"), ("active", "Active"), ("done", "Completed")):
            self.filter.set_label(k, f"{label}  {counts[k]}" if counts[k] else label)
        self.apply_filter()

    # --- inspector content
    def refresh_inspector(self, force=False):
        ih = self._selected_ih()
        if not ih:
            return
        h = self.engine.handles[ih]
        s = h.status()
        self.insp_title.setText(QFontMetrics(self.insp_title.font()).elidedText(
            s.name or "Fetching metadata…", Qt.ElideMiddle, self.PANEL_W - 90))
        page = self.tabs.value
        if page == "overview":
            for key, val in (("Size", fmt_size(s.total_wanted)), ("Downloaded", fmt_size(s.total_done)),
                             ("Uploaded", fmt_size(s.total_upload)), ("Seeds", str(s.num_seeds)),
                             ("Peers", str(s.num_peers)), ("Availability", f"{max(s.distributed_copies, 0):.2f}")):
                self.stat[key].setText(val)
            self.save_lbl.setText(esc(s.save_path))
            diag = "".join(
                f"<p style='margin:0 0 12px 0'><span style='color:{LEVEL[d['level']]}'>&#9679;</span>&nbsp; "
                f"<b>{esc(d['title'])}</b><br><span style='color:{C.text2}'>{esc(d['advice'])}</span></p>"
                for d in self.engine.diagnostics(ih)) or f"<span style='color:{C.text2}'>Nothing to report.</span>"
            trk = "".join(
                f"<p style='margin:0 0 7px 0'>{esc(t['url'])}<br><span style='color:{C.text3}'>"
                f"{'Failed ' + str(t['fails']) + ' time(s)' if t['fails'] else 'Working'}"
                f"{'  ' + esc(t['message']) if t['message'] else ''}</span></p>"
                for t in tracker_status(h)[:8]) or f"<span style='color:{C.text2}'>No trackers.</span>"
            if diag != self._ov_html.get("diag"):
                self._ov_html["diag"] = diag
                self.diag_lbl.setText(diag)
            if trk != self._ov_html.get("trk"):
                self._ov_html["trk"] = trk
                self.trk_lbl.setText(trk)
        elif page == "peers":
            self.piece_map.set_pieces(self.engine.pieces(ih))
            peers = self.engine.peers(ih)
            self.peer_empty.setVisible(not peers)
            self.peer_table.setVisible(bool(peers))
            self.peer_table.setRowCount(len(peers))
            for i, p in enumerate(peers):
                for c, v in enumerate((p["ip"], p["client"], fmt_rate(p["down"]), fmt_rate(p["up"]),
                                       f"{p['progress'] * 100:.0f}%")):
                    self.peer_table.setItem(i, c, QTableWidgetItem(v))
        else:
            rep = self.reports.get(ih)
            if id(rep) != self._shown_report or force:
                self._shown_report = id(rep)
                self.fill_security(rep, ih in self.scanning)

    def _toggle_log(self):
        show = not self.audit_log.isVisible()
        self.audit_log.setVisible(show)
        self.log_toggle.setText("Hide scan log" if show else "Show scan log")

    def _sec_selected(self):
        rep, fr = self._selected_file() if hasattr(self, "audit_log") else (None, None)
        self.release_btn.setEnabled(bool(fr and fr.quarantined))
        self.delete_btn.setEnabled(bool(fr))
        if not fr:
            self.file_detail.setText("Select a file to see why it got its result.")
            return
        why = [f.reason for f in fr.findings] + ([fr.av_hit] if fr.av_hit else []) \
            + (fr.vt["signatures"][:3] if fr.vt and fr.vt.get("signatures") else [])
        vt = "Not checked"
        if fr.vt:
            vt = f"{fr.vt['malicious']} of {fr.vt['total']} engines flagged it" if fr.vt["status"] == "found" \
                else fr.vt["status"]
        lines = [f"<b style='color:{C.text}'>{esc(fr.path)}</b>"]
        lines.append(("Why: " + esc("; ".join(why))) if why else "No issues found in this file.")
        lines.append(f"VirusTotal: {esc(vt)}")
        if fr.sha256:
            h = fr.sha256
            lines.append(f"SHA-256<br><span style='font-family:Consolas,monospace; font-size:11px'>"
                         f"{h[:32]}<br>{h[32:]}</span>")
        self.file_detail.setText("<br>".join(lines))

    def fill_security(self, rep, scanning):
        self.sec_table.setRowCount(0)
        self.audit_log.clear()
        self.rescan_btn.setEnabled(not scanning)
        if scanning:
            self.verdict_tile.set("shield", C.accent)
            self.verdict_title.setText("Scanning…")
            self.verdict_sub.setText("Checking file names, hashes and your antivirus. This usually takes a few seconds.")
            self._sec_selected()
            return
        if rep is None:
            self.verdict_tile.set("shield", C.text3)
            self.verdict_title.setText("Not scanned yet")
            self.verdict_sub.setText("The scan runs automatically when the download finishes.")
            self._sec_selected()
            return
        label, col, glyph = VERDICT[rep.verdict]
        self.verdict_tile.set("shield_check" if rep.verdict == "clean" else glyph, col)
        self.verdict_title.setText(label)
        self.verdict_title.setStyleSheet(f"color:{col}")
        self.verdict_sub.setText(f"Antivirus: {rep.av_detail or rep.av_status}\nVirusTotal: {rep.vt_status}")
        self.sec_table.setRowCount(len(rep.files))
        for i, fr in enumerate(rep.files):
            if fr.quarantined:
                risk, rc = "Quarantined", C.red
            elif fr.av_hit:
                risk, rc = "Threat", C.red
            else:
                worst = fr.worst()
                risk, rc = {"high": ("High risk", C.red), "medium": ("Medium risk", C.amber),
                            "low": ("Low risk", C.text2)}.get(worst, ("No issues", C.green))
            a = QTableWidgetItem(fr.path)
            a.setToolTip(fr.path)
            b = QTableWidgetItem(risk)
            b.setForeground(QColor(rc))
            self.sec_table.setItem(i, 0, a)
            self.sec_table.setItem(i, 1, b)
        self.audit_log.setPlainText("\n".join(rep.log))
        for i, fr in enumerate(rep.files):  # open on the first file that needs attention
            if fr.quarantined or fr.av_hit or fr.worst() in ("high", "medium"):
                self.sec_table.selectRow(i)
                break
        self._sec_selected()

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
        h = Hero()  # exercises the custom painting and the UI font fallback list
        h.resize(600, 156)
        h.push(1_500_000, 200_000)
        h.push(2_500_000, 100_000)
        if h.grab().isNull():
            raise RuntimeError("custom widgets failed to paint")
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
    apply_dark_palette(app)
    app.setStyleSheet(QSS)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    server = ipc.InstanceServer(name, w)
    server.received.connect(w.on_external)
    for it in items:
        w.add_text(it)
    w.showMinimized() if minimized else w.show()
    return app.exec()
