import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

_home = tempfile.mkdtemp()
os.environ["HOME"] = _home
os.environ["USERPROFILE"] = _home
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hashlib  # noqa: E402

import libtorrent as lt  # noqa: E402

import config  # noqa: E402
import engine as eng  # noqa: E402
import security as sec  # noqa: E402

MZ = b"MZ\x90\x00" + b"\x00" * 60


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()) / "Some.Torrent"
        self.d.mkdir()
        (self.d / "movie.mp4.exe").write_bytes(MZ)
        (self.d / "fake.pdf").write_bytes(MZ)
        (self.d / "empty.mkv").write_bytes(b"")
        (self.d / ".hid.bat").write_text("echo hi")
        (self.d / "setup.exe").write_bytes(MZ)
        (self.d / "readme.txt").write_text("hello")
        (self.d / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 100)
        (self.d / "weird‮gpj.exe").write_bytes(MZ)

    def findings(self, name):
        return sec.audit_file(self.d / name)

    def test_audit_rules(self):
        self.assertEqual(max(sec.SEV_RANK[f.severity] for f in self.findings("movie.mp4.exe")), 3)
        self.assertTrue(any("Masqueraded" in f.reason for f in self.findings("fake.pdf")))
        self.assertTrue(any("Zero-byte" in f.reason for f in self.findings("empty.mkv")))
        self.assertEqual(self.findings(".hid.bat")[0].severity, "high")
        self.assertEqual(self.findings("setup.exe")[0].severity, "medium")
        self.assertEqual(self.findings("readme.txt"), [])
        self.assertEqual(self.findings("photo.jpg"), [])
        self.assertTrue(any("override" in f.reason for f in sec.audit_file(next(self.d.glob("weird*")))))

    def test_stream_hash_matches_hashlib(self):
        p = self.d / "big.bin"
        data = os.urandom(5 * 1024 * 1024 + 123)
        p.write_bytes(data)
        sha, md = sec.stream_hashes(p, chunk=65536)
        self.assertEqual(sha, hashlib.sha256(data).hexdigest())
        self.assertEqual(md, hashlib.md5(data).hexdigest())

    def test_vt_parse(self):
        data = {"data": {"attributes": {
            "last_analysis_stats": {"malicious": 3, "suspicious": 1, "undetected": 60, "harmless": 8},
            "last_analysis_results": {
                "A": {"category": "malicious", "result": "Trojan.Gen"},
                "B": {"category": "undetected", "result": None},
                "C": {"category": "suspicious", "result": "Heur.X"}}}}}
        r = sec.parse_vt(data)
        self.assertEqual((r["malicious"], r["total"]), (3, 72))
        self.assertEqual(r["signatures"], ["Heur.X", "Trojan.Gen"])

    def test_pipeline_quarantine_release_delete(self):
        calls = []

        def fake_vt(sha, key):
            calls.append(sha)
            return {"status": "found", "malicious": 5, "suspicious": 0, "total": 70, "signatures": ["Evil"]}

        cfg = {"vt_api_key": "k", "vt_max_lookups": 3, "vt_delay": 0}
        rep = sec.run_pipeline(self.d, cfg, sleep=lambda s: None, vt_fetch=fake_vt,
                               av=lambda p: {"status": "unavailable", "hits": {}, "detail": "none"})
        self.assertEqual(rep.verdict, "threat")
        self.assertLessEqual(len(calls), 3)
        self.assertEqual(rep.badge(), "Threat Flagged")
        q = [f for f in rep.files if f.quarantined]
        self.assertTrue(q)
        names = {Path(f.quarantined).name for f in q}
        self.assertIn("movie.mp4.exe.quarantined", names)
        self.assertFalse((self.d / "movie.mp4.exe").exists())
        if os.name != "nt":
            self.assertEqual(os.stat(q[0].quarantined).st_mode & 0o777, 0)
        restored = sec.release_file(q[0].quarantined)
        self.assertTrue(Path(restored).exists())
        sec.delete_file(q[1].quarantined)
        self.assertFalse(Path(q[1].quarantined).exists())
        # a rescan must not choke on remaining quarantined files
        rep2 = sec.run_pipeline(self.d, {}, av=lambda p: {"status": "unavailable", "hits": {}, "detail": "none"})
        self.assertTrue(any("quarantined" in l for l in rep2.log))

    def test_clean_torrent(self):
        d = Path(tempfile.mkdtemp()) / "Clean"
        d.mkdir()
        (d / "a.txt").write_text("x")
        rep = sec.run_pipeline(d, {}, av=lambda p: {"status": "clean", "hits": {}, "detail": "ok"})
        self.assertEqual(rep.verdict, "clean")
        rep = sec.run_pipeline(d, {}, av=lambda p: {"status": "unavailable", "hits": {}, "detail": "none"})
        self.assertEqual(rep.verdict, "unverified")  # never claim clean without a scan

    def test_vt_rate_limit_stops(self):
        d = Path(tempfile.mkdtemp()) / "RL"
        d.mkdir()
        (d / "a.exe").write_bytes(MZ + b"1")
        (d / "b.exe").write_bytes(MZ + b"2")
        n = []

        def rl(sha, key):
            n.append(1)
            return {"status": "rate_limited"}

        rep = sec.run_pipeline(d, {"vt_api_key": "k", "vt_delay": 0}, sleep=lambda s: None, vt_fetch=rl,
                               av=lambda p: {"status": "clean", "hits": {}, "detail": "ok"})
        self.assertEqual(len(n), 1)
        self.assertEqual(rep.vt_status, "rate limited")


class TunerTests(unittest.TestCase):
    def test_hysteresis(self):
        t = eng.AdaptiveTuner(50, 1000)
        self.assertIsNone(t.update(0, 1e6, 480, 500))
        up = t.update(5, 1.3e6, 480, 500)
        self.assertEqual(up, 575)
        self.assertIsNone(t.update(10, 2e6, 570, 575))      # cooldown blocks a second raise
        self.assertIsNotNone(t.update(40, 4e6, 570, 575))   # allowed after cooldown

    def test_shrinks_only_after_three_drops(self):
        t = eng.AdaptiveTuner(50, 1000, cooldown=0)
        t.update(0, 10e6, 100, 500)
        self.assertIsNone(t.update(5, 0, 100, 500))    # drop 1 (smoothed)
        self.assertIsNone(t.update(10, 0, 100, 500))   # drop 2
        self.assertEqual(t.update(15, 0, 100, 500), 425)  # drop 3 -> shrink 15%


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.dl = Path(tempfile.mkdtemp())
        self.cfg = dict(config.DEFAULTS, download_dir=str(self.dl), listen_port=0)
        self.up = {"ip": "127.0.0.1"}
        self.e = eng.Engine(self.cfg, probe=lambda name: self.up["ip"])

    def tearDown(self):
        del self.e

    def test_presets_apply(self):
        for p in eng.PRESETS:
            self.e.set_preset(p)
        self.e.set_encryption(True)
        self.e.set_encryption(False)

    def test_kill_switch(self):
        self.e.set_interface("vpn0")
        self.assertFalse(self.e.kill)
        self.assertFalse(self.e.ses.is_paused())
        self.up["ip"] = None            # adapter disappears
        self.e.tick()
        self.assertTrue(self.e.kill)
        self.assertTrue(self.e.ses.is_paused())
        self.assertTrue(any(d["level"] == "bad" for d in self._diag_any()))
        self.up["ip"] = "127.0.0.1"     # adapter returns
        self.e.tick()
        self.assertFalse(self.e.kill)
        self.assertFalse(self.e.ses.is_paused())

    def _diag_any(self):
        src = self.dl / "kk.bin"
        src.write_bytes(os.urandom(300000))
        path = self._make_torrent(src)
        ih = self.e.add_file(path)
        return self.e.diagnostics(ih)

    def _make_torrent(self, src):
        fs = lt.file_storage()
        lt.add_files(fs, str(src))
        ct = lt.create_torrent(fs)
        lt.set_piece_hashes(ct, str(src.parent))
        out = self.dl / (src.name + ".torrent")
        out.write_bytes(lt.bencode(ct.generate()))
        return str(out)

    def test_seeding_torrent_and_inspector_data(self):
        src = self.dl / "data.bin"
        src.write_bytes(os.urandom(2_000_000))
        ih = self.e.add_file(self._make_torrent(src))
        for _ in range(100):
            self.e.tick()
            if self.e.handles[ih].status().progress >= 1.0:
                break
            time.sleep(0.1)
        self.assertGreaterEqual(self.e.handles[ih].status().progress, 1.0)
        pcs = self.e.pieces(ih)
        self.assertTrue(pcs and all(pcs))
        self.assertIsInstance(self.e.peers(ih), list)
        self.assertTrue(self.e.diagnostics(ih))


if __name__ == "__main__":
    unittest.main(verbosity=2)
