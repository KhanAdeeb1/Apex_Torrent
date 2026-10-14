"""Renders the main window with sample data (no network) for README screenshots.  Usage: demo_shots.py out_dir"""
import math
import os
import sys
import tempfile
from pathlib import Path

home = tempfile.mkdtemp()
os.environ.update(HOME=home, USERPROFILE=home, QT_QPA_PLATFORM="offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

import gui  # noqa: E402
from ui_kit import C  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
gui.apply_dark_palette(app)
app.setStyleSheet(gui.QSS)
w = gui.MainWindow()
w.timer.stop()
w.resize(1180, 760)
w.show()

MB = 1024 * 1024
for i in range(120):  # a believable two minutes of traffic
    t = i / 119
    down = (6 + 14 * (1 - math.exp(-t * 5)) + 2.2 * math.sin(i / 3.1) + 1.4 * math.sin(i / 1.7)) * MB
    up = (0.5 + 0.35 * math.sin(i / 5.0) + 0.15 * math.sin(i / 1.3)) * MB
    w.hero.push(max(down, 0), max(up, 0))

sample = [
    ("ubuntu-24.04.2-desktop-amd64.iso", "5.9 GB", 0.62, 18.4 * MB, 1.2 * MB, "4m 12s left", C.text2, C.accent, "down", None, False, False),
    ("Blender Open Movies Collection", "18.2 GB", 0.34, 9.1 * MB, 0.4 * MB, "31m 40s left", C.text2, C.accent, "down", None, False, False),
    ("debian-12.5.0-amd64-netinst.iso", "658 MB", 1.0, 0, 0, "Completed", C.green, C.green, "check", ("Clean", C.green), False, True),
    ("Fedora-Workstation-Live-41.iso", "2.3 GB", 0.71, 0, 0, "Paused", C.amber, C.amber, "pause", None, True, False),
    ("Sample.Pack", "2.9 MB", 1.0, 0, 0, "Completed", C.green, C.red, "warning", ("Threat", C.red), False, True),
]
for i, (name, size, pct, d, u, eta, ec, col, glyph, pill, paused, done) in enumerate(sample):
    r = gui.TorrentRow(f"demo{i}")
    r.set_data(name=name, size=size, pct=pct, down=d, up=u, eta=eta, eta_color=ec, color=col, glyph=glyph,
               pill=pill, paused=paused, done=done)
    w.rows[f"demo{i}"] = r
    w.list_l.insertWidget(0, r)
w.rows["demo0"].set_selected(True)
w.rows["demo0"].hover = True
w.rows["demo0"]._sync_buttons()
w.filter.set_label("all", "All  5")
w.filter.set_label("active", "Active  3")
w.filter.set_label("done", "Completed  2")
w.stack.setCurrentIndex(1)
w.conn_lbl.setText("212 of 500 connections")
w.quick.clearFocus()
w.toast.show_message("debian-12.5.0-amd64-netinst.iso: Clean", "ok", 60000)
for _ in range(15):
    app.processEvents()
w.grab().save(str(out / "main.png"))
print("ok")
