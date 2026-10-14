"""Headless GUI smoke test: builds a torrent, drives the real window, saves a screenshot."""
import os
import sys
import tempfile
import time
from pathlib import Path

home = tempfile.mkdtemp()
os.environ.update(HOME=home, USERPROFILE=home, QT_QPA_PLATFORM="offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import libtorrent as lt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import gui  # noqa: E402
import security  # noqa: E402

from PySide6.QtWidgets import QMessageBox  # noqa: E402

popups = []
QMessageBox.warning = staticmethod(lambda *a, **k: popups.append(a[1:3]))
out = sys.argv[1]
dl = Path(home) / "dl"
(dl / "Sample.Pack").mkdir(parents=True)
MZ = b"MZ\x90\x00" + b"\x00" * 60
(dl / "Sample.Pack" / "episode.mkv").write_bytes(os.urandom(3_000_000))
(dl / "Sample.Pack" / "notes.txt").write_text("hello")
(dl / "Sample.Pack" / "Episode.mp4.exe").write_bytes(MZ)
(dl / "Sample.Pack" / "cover.jpg").write_bytes(MZ)

fs = lt.file_storage()
lt.add_files(fs, str(dl / "Sample.Pack"))
ct = lt.create_torrent(fs)
lt.set_piece_hashes(ct, str(dl))
tpath = dl / "Sample.Pack.torrent"
tpath.write_bytes(lt.bencode(ct.generate()))

app = QApplication([])
app.setStyleSheet(gui.QSS)
w = gui.MainWindow()
w.cfg["download_dir"] = str(dl)
w.cfg["vt_api_key"] = ""
assert w.add_text(str(tpath))
w.add_text("magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Dead.Magnet.Example")
w.resize(1360, 700)
w.show()

deadline = time.time() + 25
while time.time() < deadline:
    w.tick()
    app.processEvents()
    ih = next(iter(w.engine.handles))
    rep = w.reports.get(ih)
    if rep:
        break
    time.sleep(0.2)
if not w.reports:  # finished alert may not fire for pre-existing data; run the pipeline directly
    ih = next(iter(w.engine.handles))
    w.reports[ih] = security.run_pipeline(dl / "Sample.Pack", {}, av=lambda p: {"status": "clean", "hits": {}, "detail": "ClamAV: no threats found"})
    print("pipeline run directly (no finished alert for pre-existing data)")
for _ in range(3):
    w.tick()
    app.processEvents()
w.table.selectRow(0)
w.show_inspector()
w.tabs.setCurrentIndex(2)
app.processEvents()
w.tick()
app.processEvents()
w.grab().save(out)
print("verdict:", [r.verdict for r in w.reports.values()], "rows:", w.table.rowCount(), "popups:", len(popups))
w.tabs.setCurrentIndex(0)
w.show_inspector()
w.engine.handles[ih]  # keep
app.processEvents()
w.grab().save(out.replace(".png", "_overview.png"))
w.engine.shutdown()
