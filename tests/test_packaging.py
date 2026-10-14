"""Tests for the packaging layer: frozen-path handling, argv/magnet handoff, self-test,
plus static lint of installer.iss and build_installer.bat (which can only be compiled/run on Windows)."""
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_home = tempfile.mkdtemp()
os.environ.update(HOME=_home, USERPROFILE=_home, QT_QPA_PLATFORM="offscreen")
sys.path.insert(0, str(ROOT))

import build_assets  # noqa: E402

if not (ROOT / "assets" / "apextorrent.ico").exists():
    build_assets.main()

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import config  # noqa: E402
import gui  # noqa: E402
import ipc  # noqa: E402

QMessageBox.warning = staticmethod(lambda *a, **k: None)
APP = QApplication.instance() or QApplication([])
MAGNET = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=Test"


class AppPackagingTests(unittest.TestCase):
    def test_resource_path_source_and_frozen(self):
        self.assertTrue(os.path.exists(gui.resource_path("assets/apextorrent.ico")))
        sys._MEIPASS = "/fake/bundle"
        try:
            self.assertEqual(gui.resource_path("assets/x.png"), os.path.join("/fake/bundle", "assets/x.png"))
        finally:
            del sys._MEIPASS

    def test_app_icon_loads(self):
        self.assertFalse(gui.app_icon().pixmap(32, 32).isNull())

    def test_parse_args(self):
        items, mini = ipc.parse_args(["--minimized", MAGNET, "C:\\x\\a.TORRENT", "junk.txt"])
        self.assertTrue(mini)
        self.assertEqual(items[0], MAGNET)
        self.assertTrue(items[1].lower().endswith("a.torrent") and os.path.isabs(items[1]))
        self.assertEqual(len(items), 2)
        self.assertEqual(ipc.parse_args([]), ([], False))
        self.assertEqual(ipc.parse_args(['"' + MAGNET + '"'])[0], [MAGNET])  # quoted by the shell

    def test_single_instance_roundtrip(self):
        import subprocess
        name = f"ApexTest-{os.getpid()}"
        got = []
        srv = ipc.InstanceServer(name)
        self.assertTrue(srv.ok)
        srv.received.connect(got.append)
        # A real second launch is another process, so test it that way (a thread would starve the server via the GIL).
        code = ("import sys, json; sys.path.insert(0, %r)\n"
                "from PySide6.QtCore import QCoreApplication\n"
                "app = QCoreApplication([])\n"
                "import ipc\n"
                "items = json.loads(sys.argv[2])\n"
                "sys.exit(0 if ipc.send_to_running(items, sys.argv[1], timeout=4000) else 1)\n") % str(ROOT)
        for items in ([MAGNET, "/tmp/a.torrent"], []):
            p = subprocess.Popen([sys.executable, "-c", code, name, json.dumps(items)])
            end = time.time() + 10
            while p.poll() is None and time.time() < end:
                QCoreApplication.processEvents()
                time.sleep(0.01)
            self.assertEqual(p.poll(), 0, "client did not get an acknowledgment")
        for _ in range(20):
            QCoreApplication.processEvents()
        self.assertEqual(got, [[MAGNET, "/tmp/a.torrent"], []])
        self.assertFalse(ipc.send_to_running([MAGNET], f"ApexNobodyHome-{os.getpid()}", timeout=100))

    def test_external_launch_adds_torrent(self):
        config.APP_DIR.mkdir(parents=True, exist_ok=True)
        config.CONFIG_FILE.write_text(json.dumps({"listen_port": 0, "download_dir": _home}))
        w = gui.MainWindow()
        try:
            w.on_external([MAGNET])
            self.assertEqual(len(w.engine.handles), 1)
        finally:
            w.engine.shutdown()

    def test_selftest(self):
        out = Path(_home) / "st.txt"
        self.assertEqual(gui.selftest(str(out)), 0)
        self.assertTrue(out.read_text().startswith("OK"))


class InstallerLintTests(unittest.TestCase):
    """installer.iss can only be compiled by Inno Setup on Windows; catch the mistakes we can catch here."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / "installer.iss").read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()

    def sections(self):
        return set(re.findall(r"^\[(\w+)\]", self.text, flags=re.M))

    def test_sections_present(self):
        need = {"Setup", "Languages", "Tasks", "Files", "Icons", "Registry", "Run", "UninstallRun", "Code"}
        self.assertTrue(need <= self.sections(), need - self.sections())

    def test_required_setup_directives(self):
        for key in ("AppId", "AppName", "AppVersion", "DefaultDirName", "LicenseFile", "SetupIconFile",
                    "OutputBaseFilename", "ChangesAssociations", "AppMutex", "PrivilegesRequired"):
            self.assertRegex(self.text, rf"(?m)^{key}=", msg=key)
        self.assertIn("OutputBaseFilename=ApexTorrent_Setup", self.text)

    def test_task_references_are_defined(self):
        defined = set(re.findall(r'^Name: "(\w+)"; Description', self.text, flags=re.M))
        used = set()
        for ln in self.lines:
            m = re.search(r"Tasks: (\w+)", ln)
            if m:
                used.add(m.group(1))
        self.assertTrue(used <= defined, used - defined)
        self.assertTrue({"desktopicon", "startup", "assoc_torrent", "assoc_magnet", "firewall"} <= defined)

    def test_macros_defined(self):
        defined = set(re.findall(r"^\s*#define\s+(\w+)", self.text, flags=re.M))
        used = set(re.findall(r"\{#(\w+)\}", self.text))
        self.assertTrue(used <= defined, used - defined)

    def test_quote_parity(self):
        for n, ln in enumerate(self.lines, 1):
            if ln.lstrip().startswith((";", "//")) or "[Code]" in ln:
                continue
            if self.text.index(ln) > self.text.index("[Code]"):
                break
            self.assertEqual(ln.count('"') % 2, 0, f"line {n}: {ln}")

    def test_source_files_exist(self):
        for src in re.findall(r'^Source: "([^"]+)"', self.text, flags=re.M):
            if src.startswith("dist"):
                continue
            self.assertTrue((ROOT / src.replace("\\", "/")).exists(), src)
        for key in ("LicenseFile", "SetupIconFile", "WizardImageFile", "WizardSmallImageFile"):
            rel = re.search(rf"^{key}=(.+)$", self.text, flags=re.M).group(1).strip()
            self.assertTrue((ROOT / rel.replace("\\", "/")).exists(), rel)

    def test_protocol_and_assoc_commands_pass_argument(self):
        cmds = [ln for ln in self.lines if r"\shell\open\command" in ln]
        self.assertEqual(len(cmds), 3)  # .torrent progid, magnet, magnet progid
        for ln in cmds:
            self.assertIn('""%1""', ln.replace('"%1"', '""%1""') if '""%1""' not in ln else ln)
        self.assertIn("URL Protocol", self.text)

    def test_firewall_add_and_remove_pair(self):
        self.assertIn("firewall add rule", self.text)
        self.assertEqual(self.text.count("firewall delete rule"), 2 + 0)  # pre-clean on install + uninstall
        self.assertIn("RunOnceId", self.text)

    def test_uninstall_prompts_before_deleting_user_data(self):
        self.assertIn("usPostUninstall", self.text)
        self.assertIn("MB_DEFBUTTON2", self.text)  # default answer is "No": keep the data
        self.assertIn(".apextorrent", self.text)

    def test_mutex_matches_app(self):
        m = re.search(r'#define MyAppMutex\s+"(\w+)"', self.text).group(1)
        self.assertIn(m, (ROOT / "app.py").read_text())

    def test_exe_name_matches_spec(self):
        self.assertIn('#define MyAppExeName   "ApexTorrent.exe"', self.text)
        import version
        self.assertEqual(version.APP_NAME + ".exe", "ApexTorrent.exe")

    def test_no_default_setup_version_drift(self):
        import version
        self.assertIn(f'#define MyAppVersion "{version.APP_VERSION}"', self.text)


class BatchLintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "build_installer.bat").read_bytes()
        cls.text = cls.raw.decode("utf-8")

    def test_gotos_have_targets(self):
        labels = set(re.findall(r"^:(\w+)", self.text, flags=re.M))
        for target in re.findall(r"goto :(\w+)", self.text):
            self.assertIn(target, labels, target)

    def test_is_ascii_and_crlf_safe(self):
        self.assertTrue(all(b < 128 for b in self.raw), "non-ASCII byte in .bat")
        self.assertNotIn(b"\n", self.raw.replace(b"\r\n", b""), "bare LF breaks goto/labels in cmd.exe")

    def test_prints_build_stamp(self):
        self.assertIn("BUILD_STAMP.txt", self.text)
        self.assertTrue((ROOT / "BUILD_STAMP.txt").exists())

    def test_ci_safe(self):
        self.assertIn('"%CI%"=="true"', self.text)      # GitHub sets CI=true; a bare `pause` would hang the runner
        self.assertIn("APEX_PYTHON", self.text)
        # libtorrent has no Windows wheels for 3.14+, so the script must never fall back to a bare `py -3`
        self.assertNotIn("py -3 ", self.text.replace("py -3.", ""))
        self.assertIn("py -%%V", self.text)
        self.assertIn("<=sys.version_info[:2]<=(3,13)", self.text)

    def test_pipeline_steps_present(self):
        for needle in ("venv", "pip install -r requirements.txt -r requirements-build.txt", "build_assets.py",
                       "PyInstaller --noconfirm --clean apextorrent.spec", "--selftest", "ISCC", "installer.iss",
                       "ApexTorrent_Setup.exe"):
            self.assertIn(needle, self.text, needle)

    def test_parentheses_balanced_in_blocks(self):
        depth = 0
        for ln in self.text.splitlines():
            if ln.lstrip().lower().startswith("rem "):
                continue
            s = ln.strip()
            if s.startswith(")") and s.endswith("("):  # ") else (" closes one block and opens the next
                continue
            if s.endswith("(") and (s.lower().startswith(("if ", "for ", "else")) or s == "("):
                depth += 1
            elif s == ")" or s.startswith(") "):
                depth -= 1
            elif depth > 0 and "(" in s.replace("%ProgramFiles(x86)%", ""):
                self.fail(f"unescaped parenthesis inside a block: {ln}")
        self.assertEqual(depth, 0)


class WorkflowLintTests(unittest.TestCase):
    def test_github_workflow(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        wf = yaml.safe_load((ROOT / ".github" / "workflows" / "build-windows.yml").read_text())
        triggers = wf.get("on", wf.get(True))
        self.assertIn("workflow_dispatch", triggers)
        job = wf["jobs"]["build"]
        self.assertEqual(job["runs-on"], "windows-latest")
        self.assertEqual(job.get("env", {}).get("APEX_PYTHON", "python"), "python")
        steps = job["steps"]
        runs = " ".join(str(s.get("run", "")) for s in steps)
        self.assertIn("build_installer.bat", runs)
        uses = [s.get("uses", "") for s in steps]
        self.assertTrue(any(u.startswith("actions/setup-python@") for u in uses))
        up = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact@"))
        self.assertEqual(up["with"]["path"], "dist/ApexTorrent_Setup.exe")
        self.assertEqual(up["with"]["if-no-files-found"], "error")
        # the setup-python version must be one libtorrent/PySide6 publish wheels for
        py = next(s for s in steps if str(s.get("uses", "")).startswith("actions/setup-python@"))
        self.assertIn(py["with"]["python-version"], ("3.11", "3.12"))
        self.assertTrue((ROOT / ".gitignore").exists())


class SpecTests(unittest.TestCase):
    def test_windows_version_resource_generation(self):
        """The spec only builds this on Windows, so exercise the function here and parse the result back."""
        import version
        import PyInstaller.compat as pic
        if not hasattr(pic, "win32api"):  # only imported at load time; the classes we use are pure Python
            pic.win32api = None
        try:
            from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
        except ImportError as e:  # pefile is a Windows-only PyInstaller dependency
            self.skipTest(f"PyInstaller win32 helpers unavailable here: {e}")
        src = (ROOT / "apextorrent.spec").read_text()
        code = src[src.index("def write_version_file"):src.index("version_file = write_version_file()")]
        ns = {"ROOT": Path(tempfile.mkdtemp()), "V": version}
        exec(code, ns)
        path = ns["write_version_file"]()
        vi = load_version_info_from_text_file(path)
        strings = {x.name: x.val for table in vi.kids[0].kids for x in table.kids}
        self.assertEqual(strings["ProductName"], version.APP_NAME)
        self.assertEqual(strings["CompanyName"], version.PUBLISHER)
        self.assertEqual(strings["FileVersion"], version.APP_VERSION)
        self.assertEqual(strings["OriginalFilename"], "ApexTorrent.exe")
        self.assertEqual((vi.ffi.fileVersionMS, vi.ffi.fileVersionLS), (0x00010000, 0))  # 1.0.0.0

    def test_spec_is_valid_python_and_mentions_required_pieces(self):
        src = (ROOT / "apextorrent.spec").read_text()
        compile(src, "apextorrent.spec", "exec")
        for needle in ("console=False", "upx=False", "icon=icon_file", "version=version_file", "COLLECT(",
                       "libtorrent_binaries", "qwindows", "PySide6.QtSvg", "LegalCopyright", "ProductName"):
            self.assertIn(needle, src, needle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
