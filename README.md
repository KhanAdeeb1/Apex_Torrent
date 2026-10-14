# ApexTorrent

Ad-free, uncapped BitTorrent client with an automatic post-download security pipeline.
Python + libtorrent (the engine behind qBittorrent/Deluge) + PySide6.

## Run

    python -m pip install -r requirements.txt
    python app.py

Python 3.10 to 3.13 (3.12 recommended). libtorrent has no Windows wheels for Python 3.14 yet.
Package as an .exe: `pip install pyinstaller && pyinstaller --onefile --windowed app.py`.

## Use

- Paste a magnet link or `.torrent` path into the top bar, press Enter, or drop a `.torrent` anywhere on the window.
- Preset (top bar): Balanced, Max Throughput, Quiet Mode.
- Interface (top bar): pick your VPN adapter to bind all traffic to it. If it goes down, the session pauses and
  nothing can leave the machine; it resumes automatically when the adapter returns.
- Select a torrent and press Inspect: Overview (diagnostics + trackers), Peers and pieces, Security.
- Settings menu: download folder, VirusTotal key, require encryption, seed after clean scan, adaptive tuning.

## Security pipeline (runs when a torrent completes; the torrent is paused first)

1. Audit: double-extension traps (`.mp4.exe`), masqueraded binaries (PE/ELF/Mach-O header under a media/doc name),
   hidden scripts, shortcuts, RTL-override names, zero-byte media.
2. Streaming SHA-256 + MD5 (constant memory).
3. VirusTotal v3 hash lookup (needs your free API key). Hash only, nothing is uploaded. Limited to 10 lookups per
   torrent, 16 s apart, to respect the free quota (4/min, 500/day). Only executable/script/archive/flagged files.
4. Local AV: Microsoft Defender (`MpCmdRun.exe`) on Windows, `clamscan` elsewhere.
5. Threat verdict: offending files are renamed `*.quarantined` and execute permission is stripped
   (`chmod 000` / `icacls deny Everyone:X`). Release or delete from the Security tab.

Verdicts: Clean, Suspicious, Threat Flagged, Unverified. "Clean" is never shown unless a scanner or VirusTotal
actually checked the files; with neither available you get Unverified.

## Tests

    python tests/test_core.py          # 11 unit tests (security, tuner, kill switch, engine)
    python tests/gui_smoke.py out.png  # headless GUI run + screenshot

## Known limits

- Speed depends on seeders, your ISP and a forwarded port (default 6881). The app sets no cap, it cannot create bandwidth.
- Signature scanning misses new malware. Never run executables from untrusted torrents.
- "Require encryption" shrinks your peer pool (many peers don't speak MSE/PE), so it is off by default.
- Tracker latency is not exposed by libtorrent; the Overview shows tracker status and failures instead.
- The kill switch binds to the adapter's IPv4 address and pauses on disconnect. It does not stop other programs.
- No automatic VirusTotal upload of unknown files: that would share your downloads with third parties.

## Building the Windows installer (ApexTorrent_Setup.exe)

On a Windows 10/11 x64 machine with 64-bit Python 3.10 to 3.13 (3.12 recommended; 3.14 does not work yet because libtorrent has no wheel for it):

    build_installer.bat            (add --skip-tests to skip the test suites)

The script creates `.venv`, installs dependencies, generates the icons (`build_assets.py`), runs the tests,
builds the app with PyInstaller (`apextorrent.spec`), **runs the bundled exe's `--selftest`** (fails the build if
Qt, libtorrent or the icon cannot load), then compiles `installer.iss` with Inno Setup 6.3+ (auto-detected; installed
through winget if missing). Output: `dist\ApexTorrent_Setup.exe` and its SHA-256.

Before you ship, edit `version.py` (publisher, copyright, URL, version) and the matching `#define` lines at the
top of `installer.iss`. Never change the `AppId` GUID after the first public release.

What the installer does: license page, install folder (Program Files, or per-user without admin via the startup
dialog), desktop and Start menu shortcuts with an uninstaller entry, optional start-with-Windows (minimized),
`.torrent` association with its own file icon, `magnet:` handler, Defender Firewall inbound rule (admin installs),
and an uninstaller that removes all of it and asks before deleting `%USERPROFILE%\.apextorrent`.

### Things to know before distributing

- **SmartScreen / antivirus warnings.** An unsigned installer shows "Windows protected your PC", and PyInstaller
  apps are sometimes flagged falsely, especially torrent clients. The build is one-directory, UPX is off and version
  metadata is embedded, which all help. The real fix is an Authenticode certificate: set `SIGNTOOL_CMD` (see the
  top of `build_installer.bat`) and the installer and uninstaller get signed. Submit false positives to the AV vendor.
- **Default apps.** Windows 10/11 protects the user's default-app choice, so the installer registers
  ApexTorrent and sets the classic keys, but Windows may still ask the user to confirm it under
  Settings > Apps > Default apps the first time.
- **Licenses.** PySide6/Qt is LGPLv3: keep the one-directory build (do not switch to `--onefile`) and keep
  `THIRD_PARTY_NOTICES.txt`. `LICENSE.txt` is a plain permissive template, not legal advice; have it reviewed
  if you distribute commercially.
- **Command line.** `ApexTorrent.exe "magnet:?xt=..."`, `ApexTorrent.exe file.torrent`, `--minimized`.
  A second launch hands its argument to the running window and exits.
- **Diagnostics.** The windowed exe writes errors to `%USERPROFILE%\.apextorrent\apextorrent.log`.

### Tests

    python tests\test_core.py        # engine + security (11)
    python tests\test_packaging.py   # frozen paths, magnet handoff, selftest, .iss/.bat/.spec lint (26)

## Building without a Windows PC (GitHub Actions)

`.github/workflows/build-windows.yml` runs `build_installer.bat` on a GitHub-hosted Windows machine.

1. Create a GitHub repository (private is fine) and push this folder to it.
2. Repo > Actions tab > "Build Windows installer" > Run workflow.
3. When it finishes (about 10-15 minutes), open the run and download the `ApexTorrent_Setup` artifact.
   GitHub wraps artifacts in a zip, so unzip it to get `ApexTorrent_Setup.exe`.

Pushing a tag such as `v1.0.0` also attaches the installer to a GitHub Release, which gives you a permanent
download link to share. If a run fails, open the failed step and read the log; the bundle self-test result
is printed in its own step. A failed run also uploads a `build_diagnostics` artifact (logs, PyInstaller warnings and,
if the app itself was built, a portable zip you can run without the installer).
