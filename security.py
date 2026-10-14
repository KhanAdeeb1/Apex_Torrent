"""
Post-download security pipeline.

  1. Heuristic file-tree audit  (double extensions, masqueraded binaries, hidden scripts, zero-byte media)
  2. Streaming SHA-256 + MD5    (constant memory, any file size)
  3. VirusTotal v3 hash lookup  (hash only, nothing is uploaded)
  4. Local AV scan              (Microsoft Defender CLI on Windows, ClamAV elsewhere)
  5. Auto-quarantine            (rename to *.quarantined + strip execute permission, reversible)
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from config import APP_DIR

MANIFEST = APP_DIR / "quarantine.json"

# Child processes must not flash console windows or inherit a missing stdin when the app is frozen/windowed.
_SUB = {"stdin": subprocess.DEVNULL}
if os.name == "nt":
    _SUB["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

MEDIA_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg",
             ".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".jpg", ".jpeg", ".png", ".gif",
             ".bmp", ".webp", ".srt", ".sub"}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".epub",
           ".mobi", ".odt", ".csv"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".iso", ".img", ".cab", ".tar", ".gz"}
EXEC_BINARY = {".exe", ".scr", ".pif", ".com", ".dll", ".sys", ".ocx", ".cpl", ".drv", ".msi",
               ".jar", ".apk"}
SCRIPT_EXT = {".bat", ".cmd", ".vbs", ".vbe", ".ps1", ".js", ".jse", ".wsf", ".hta", ".reg", ".sh"}
LINK_EXT = {".lnk"}
DANGEROUS = EXEC_BINARY | SCRIPT_EXT | LINK_EXT
DECOYS = MEDIA_EXT | DOC_EXT | ARCHIVE_EXT
VT_EXT = DANGEROUS | ARCHIVE_EXT

SEV_RANK = {"": 0, "low": 1, "medium": 2, "high": 3}


# ----------------------------------------------------------------------------- models
@dataclass
class Finding:
    severity: str  # low | medium | high
    reason: str


@dataclass
class FileReport:
    path: str            # relative to the torrent's parent folder
    abs_path: str
    size: int
    sha256: str = ""
    md5: str = ""
    vt: dict | None = None
    findings: list = field(default_factory=list)
    av_hit: str = ""
    quarantined: str = ""  # absolute path of the .quarantined file, if quarantined

    def worst(self):
        w = max((SEV_RANK[f.severity] for f in self.findings), default=0)
        return {v: k for k, v in SEV_RANK.items()}[w]


@dataclass
class SecurityReport:
    root: str
    verdict: str = "unverified"   # clean | suspicious | threat | unverified
    files: list = field(default_factory=list)
    av_status: str = "not run"
    av_detail: str = ""
    vt_status: str = "not run"
    vt_summary: str = ""          # e.g. "0/72"
    log: list = field(default_factory=list)
    started: float = 0.0
    finished: float = 0.0

    def badge(self):
        if self.verdict == "clean":
            return f"Clean ({self.vt_summary})" if self.vt_summary else "Clean"
        return {"suspicious": "Suspicious", "threat": "Threat Flagged",
                "unverified": "Unverified"}.get(self.verdict, self.verdict)


# ----------------------------------------------------------------------------- 1. audit
def sniff_binary(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return None
    if head[:2] == b"MZ":
        return "Windows executable (PE)"
    if head == b"\x7fELF":
        return "Linux executable (ELF)"
    if head in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe"):
        return "macOS executable (Mach-O)"
    return None


def audit_file(p: Path):
    out = []
    name = p.name
    suffixes = [s.lower() for s in p.suffixes]
    ext = suffixes[-1] if suffixes else ""
    try:
        size = p.stat().st_size
    except OSError:
        return out

    if "\u202e" in name:
        out.append(Finding("high", "Filename contains a right-to-left override character (reverses the visible extension)"))
    if len(suffixes) >= 2 and ext in DANGEROUS and suffixes[-2] in DECOYS:
        out.append(Finding("high", f"Double-extension trap: looks like {suffixes[-2]} but is really {ext}"))
    elif ext in LINK_EXT:
        out.append(Finding("high", "Shortcut (.lnk) inside a torrent; classic malware launcher"))
    elif ext in EXEC_BINARY:
        out.append(Finding("medium", f"Executable file type ({ext})"))
    elif ext in SCRIPT_EXT:
        if name.startswith("."):
            out.append(Finding("high", f"Hidden script ({ext})"))
        else:
            out.append(Finding("medium", f"Script file type ({ext})"))
    if ext in MEDIA_EXT | DOC_EXT | ARCHIVE_EXT:
        if size == 0:
            out.append(Finding("medium", "Zero-byte file claiming to be media/document"))
        kind = sniff_binary(p)
        if kind:
            out.append(Finding("high", f"Masqueraded binary: named {ext} but contents are a {kind}"))
    return out


# ----------------------------------------------------------------------------- 2. hashing
def stream_hashes(path, chunk=1024 * 1024):
    sha, md = hashlib.sha256(), hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            sha.update(b)
            md.update(b)
    return sha.hexdigest(), md.hexdigest()


# ----------------------------------------------------------------------------- 3. VirusTotal
def parse_vt(data):
    attrs = data.get("data", {}).get("attributes", {})
    stats = attrs.get("last_analysis_stats", {})
    total = sum(stats.get(k, 0) for k in ("malicious", "suspicious", "undetected", "harmless"))
    sigs = sorted({v.get("result") for v in attrs.get("last_analysis_results", {}).values()
                   if v.get("category") in ("malicious", "suspicious") and v.get("result")})
    return {"status": "found", "malicious": stats.get("malicious", 0),
            "suspicious": stats.get("suspicious", 0), "total": total, "signatures": sigs[:8]}


def vt_lookup(sha256, api_key, opener=urllib.request.urlopen):
    req = urllib.request.Request(f"https://www.virustotal.com/api/v3/files/{sha256}",
                                 headers={"x-apikey": api_key})
    try:
        with opener(req, timeout=20) as r:
            return parse_vt(json.load(r))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"status": "unknown"}
        if e.code == 429:
            return {"status": "rate_limited"}
        if e.code in (401, 403):
            return {"status": "auth_error"}
        return {"status": "error", "detail": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return {"status": "error", "detail": str(e)}


# ----------------------------------------------------------------------------- 4. local AV
def find_av():
    if platform.system() == "Windows":
        cands = [r"C:\Program Files\Windows Defender\MpCmdRun.exe"]
        cands += sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"),
                        reverse=True)
        for c in cands:
            if os.path.exists(c):
                return "defender", c
    clam = shutil.which("clamscan")
    if clam:
        return "clamav", clam
    return None


def av_scan(path):
    sc = find_av()
    if not sc:
        return {"status": "unavailable", "hits": {},
                "detail": "No scanner found (Windows Defender on Windows, or install ClamAV)."}
    kind, exe = sc
    try:
        if kind == "clamav":
            r = subprocess.run([exe, "-r", "--infected", "--no-summary", path],
                               capture_output=True, text=True, timeout=7200, **_SUB)
            hits = {}
            for line in r.stdout.splitlines():
                m = re.match(r"^(.*): (.+) FOUND$", line.strip())
                if m:
                    hits[os.path.normpath(m.group(1))] = m.group(2)
            if r.returncode == 0:
                return {"status": "clean", "hits": {}, "detail": "ClamAV: no threats found"}
            if r.returncode == 1:
                return {"status": "threat", "hits": hits, "detail": "ClamAV: " + "; ".join(hits.values())[:300]}
            return {"status": "error", "hits": {}, "detail": "ClamAV error: " + r.stderr.strip()[:300]}
        r = subprocess.run([exe, "-Scan", "-ScanType", "3", "-File", path, "-DisableRemediation"],
                           capture_output=True, text=True, timeout=7200, **_SUB)
        if r.returncode == 0:
            return {"status": "clean", "hits": {}, "detail": "Defender: no threats found"}
        names = re.findall(r"^\s*Threat\s*:\s*(.+)$", r.stdout, flags=re.M)
        return {"status": "threat", "hits": {}, "detail":
                "Defender: " + ("; ".join(names) if names else f"threat or scan error (exit {r.returncode})")}
    except Exception as e:
        return {"status": "error", "hits": {}, "detail": f"Scan failed: {e}"}


# ----------------------------------------------------------------------------- 5. quarantine
def _manifest():
    try:
        return json.loads(MANIFEST.read_text())
    except Exception:
        return {}


def _manifest_save(m):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))


def _retry(fn, tries=4, delay=0.5):
    for i in range(tries):
        try:
            return fn()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(delay)


def quarantine_file(path):
    p = Path(path)
    if not p.exists():
        return ""
    mode = stat.S_IMODE(p.stat().st_mode)
    q = p.with_name(p.name + ".quarantined")
    _retry(lambda: p.rename(q))
    if os.name == "nt":
        subprocess.run(["icacls", str(q), "/deny", "*S-1-1-0:(X)"], capture_output=True, **_SUB)
    else:
        os.chmod(q, 0)
    m = _manifest()
    m[str(q)] = {"original": str(p), "mode": mode}
    _manifest_save(m)
    return str(q)


def release_file(qpath):
    q = Path(qpath)
    m = _manifest()
    info = m.get(str(q), {})
    original = Path(info.get("original", str(q)[: -len(".quarantined")]))
    if os.name == "nt":
        subprocess.run(["icacls", str(q), "/remove:d", "*S-1-1-0"], capture_output=True, **_SUB)
    else:
        os.chmod(q, info.get("mode", 0o644))
    _retry(lambda: q.rename(original))
    m.pop(str(q), None)
    _manifest_save(m)
    return str(original)


def delete_file(path):
    p = Path(path)
    if os.name == "nt":
        subprocess.run(["icacls", str(p), "/remove:d", "*S-1-1-0"], capture_output=True, **_SUB)
    else:
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    p.unlink(missing_ok=True)
    m = _manifest()
    if m.pop(str(p), None) is not None:
        _manifest_save(m)


# ----------------------------------------------------------------------------- pipeline
def run_pipeline(root, cfg, log=None, sleep=time.sleep, vt_fetch=None, av=av_scan):
    rep = SecurityReport(root=str(root), started=time.time())

    def L(msg):
        rep.log.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        if log:
            log(msg)

    root = Path(root)
    if not root.exists():
        L(f"Path not found: {root}. If it was quarantined, release it first.")
        rep.finished = time.time()
        return rep
    base = root.parent
    paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
    skipped = [p for p in paths if p.name.endswith(".quarantined")]
    paths = [p for p in paths if not p.name.endswith(".quarantined")]
    if skipped:
        L(f"Skipping {len(skipped)} already-quarantined file(s)")

    # 1. audit
    L(f"Audit: inspecting {len(paths)} file(s)")
    for p in paths:
        fr = FileReport(path=str(p.relative_to(base)), abs_path=str(p), size=p.stat().st_size)
        fr.findings = audit_file(p)
        rep.files.append(fr)
        for f in fr.findings:
            L(f"  [{f.severity.upper()}] {fr.path}: {f.reason}")

    # 2. hashes
    L("Hashing (SHA-256 + MD5, streaming)")
    for fr in rep.files:
        try:
            fr.sha256, fr.md5 = stream_hashes(fr.abs_path)
        except OSError as e:
            L(f"  hash failed for {fr.path}: {e}")

    # 3. VirusTotal
    key = cfg.get("vt_api_key") or os.environ.get("VT_API_KEY", "")
    if not key:
        rep.vt_status = "skipped (no API key)"
        L("VirusTotal: skipped (no API key set)")
    else:
        cands = [fr for fr in rep.files if fr.sha256 and
                 (fr.findings or Path(fr.path).suffix.lower() in VT_EXT)]
        cap = int(cfg.get("vt_max_lookups", 10))
        if len(cands) > cap:
            L(f"VirusTotal: {len(cands)} candidate files, looking up first {cap} (free-tier quota)")
            cands = cands[:cap]
        rep.vt_status = "no candidate files" if not cands else "ok"
        best = None
        for i, fr in enumerate(cands):
            if i:
                sleep(float(cfg.get("vt_delay", 16.0)))
            res = (vt_fetch or vt_lookup)(fr.sha256, key)
            fr.vt = res
            st = res["status"]
            if st == "rate_limited":
                rep.vt_status = "rate limited"
                L("VirusTotal: rate limit hit, stopping lookups")
                break
            if st == "auth_error":
                rep.vt_status = "API key rejected"
                L("VirusTotal: API key rejected")
                break
            if st == "error":
                rep.vt_status = "network error"
                L(f"VirusTotal: {res.get('detail', 'error')}")
                continue
            if st == "found":
                L(f"VirusTotal {fr.path}: {res['malicious']}/{res['total']} malicious"
                  + (f" ({', '.join(res['signatures'][:3])})" if res["signatures"] else ""))
                if best is None or res["malicious"] > best["malicious"]:
                    best = res
            else:
                L(f"VirusTotal {fr.path}: hash unknown to VirusTotal")
        if best:
            rep.vt_summary = f"{best['malicious']}/{best['total']}"

    # 4. local AV
    res = av(str(root))
    rep.av_status, rep.av_detail = res["status"], res["detail"]
    L(f"Antivirus: {res['detail']}")
    hits = {os.path.normcase(os.path.normpath(k)): v for k, v in res.get("hits", {}).items()}
    for fr in rep.files:
        fr.av_hit = hits.get(os.path.normcase(os.path.normpath(fr.abs_path)), "")

    # verdict
    threat = suspicious = False
    for fr in rep.files:
        w = fr.worst()
        threat |= w == "high"
        suspicious |= w == "medium"
        if fr.vt and fr.vt["status"] == "found":
            if fr.vt["malicious"] >= 2:
                threat = True
            elif fr.vt["malicious"] + fr.vt["suspicious"] >= 1:
                suspicious = True
        threat |= bool(fr.av_hit)
    threat |= rep.av_status == "threat"
    vt_checked = any(fr.vt and fr.vt["status"] in ("found", "unknown") for fr in rep.files)
    if threat:
        rep.verdict = "threat"
    elif suspicious:
        rep.verdict = "suspicious"
    elif rep.av_status == "clean" or vt_checked:
        rep.verdict = "clean"
    else:
        rep.verdict = "unverified"

    # 5. quarantine
    if rep.verdict == "threat":
        mapped = any(fr.av_hit for fr in rep.files)
        for fr in rep.files:
            bad = (fr.worst() == "high" or bool(fr.av_hit)
                   or bool(fr.vt and fr.vt["status"] == "found" and fr.vt["malicious"] >= 2)
                   or (rep.av_status == "threat" and not mapped
                       and Path(fr.path).suffix.lower() in DANGEROUS))
            if bad:
                try:
                    fr.quarantined = quarantine_file(fr.abs_path)
                    L(f"QUARANTINED {fr.path}")
                except OSError as e:
                    L(f"Could not quarantine {fr.path}: {e}")
    L(f"Verdict: {rep.verdict.upper()}")
    rep.finished = time.time()
    return rep
