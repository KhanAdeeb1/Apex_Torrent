"""
ApexTorrent engine: libtorrent session, presets, adaptive connection tuning,
interface-bound kill switch, resume persistence and per-torrent diagnostics.
"""
from __future__ import annotations

import socket
import time
from pathlib import Path

import libtorrent as lt
import psutil

from config import RESUME_DIR

PRESET_LABELS = {"balanced": "Balanced", "max": "Max Throughput", "quiet": "Quiet Mode"}

BASE = {
    "user_agent": "ApexTorrent/1.0",
    "enable_dht": True,
    "enable_lsd": True,
    "enable_upnp": True,
    "enable_natpmp": True,
    "download_rate_limit": 0,   # 0 = unlimited
    "upload_rate_limit": 0,
    "active_downloads": -1,
    "active_seeds": -1,
    "active_limit": -1,
    "alert_mask": lt.alert.category_t.error_notification
    | lt.alert.category_t.status_notification
    | lt.alert.category_t.performance_warning,
}

PRESETS = {
    "balanced": {"connections_limit": 500, "unchoke_slots_limit": 16,
                 "max_out_request_queue": 500, "max_queued_disk_bytes": 2 * 1024 * 1024},
    "max": {"connections_limit": 1500, "unchoke_slots_limit": -1,
            "max_out_request_queue": 1500, "max_queued_disk_bytes": 8 * 1024 * 1024},
    "quiet": {"connections_limit": 100, "unchoke_slots_limit": 4,
              "max_out_request_queue": 200, "max_queued_disk_bytes": 1024 * 1024,
              "download_rate_limit": 4 * 1024 * 1024, "upload_rate_limit": 128 * 1024,
              "active_downloads": 2},
}


# ----------------------------------------------------------------------------- interfaces
def list_interfaces():
    """[(adapter name, IPv4)] for adapters that are up and have a non-loopback IPv4."""
    out = []
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        v4 = [a.address for a in addrs if a.family == socket.AF_INET and not a.address.startswith("127.")]
        if v4 and name in stats and stats[name].isup:
            out.append((name, v4[0]))
    return out


def probe_interface(name):
    for n, ip in list_interfaces():
        if n == name:
            return ip
    return None


# ----------------------------------------------------------------------------- adaptive tuner
class AdaptiveTuner:
    """
    Grows the connection limit while throughput is improving and the limit is nearly saturated;
    shrinks it only after three consecutive >15% throughput drops. A 30 s cooldown between changes
    and asymmetric thresholds give hysteresis, so the limit does not oscillate.
    """

    def __init__(self, lo, hi, cooldown=30.0):
        self.lo, self.hi, self.cooldown = lo, hi, cooldown
        self.ewma = None
        self.drops = 0
        self.last_change = -1e9
        self.last_sample = -1e9

    def update(self, now, rate, conns, limit):
        if now - self.last_sample < 5:
            return None
        self.last_sample = now
        prev = self.ewma
        self.ewma = rate if prev is None else 0.7 * prev + 0.3 * rate
        if prev is None or prev <= 0:
            return None
        self.drops = self.drops + 1 if self.ewma < prev * 0.85 else 0
        if now - self.last_change < self.cooldown:
            return None
        util = conns / max(limit, 1)
        if util >= 0.9 and self.ewma >= prev * 1.05 and limit < self.hi:
            self.last_change = now
            return min(self.hi, int(limit * 1.15))
        if self.drops >= 3 and util < 0.8 and limit > self.lo:
            self.drops = 0
            self.last_change = now
            return max(self.lo, int(limit * 0.85))
        return None


# ----------------------------------------------------------------------------- engine
def ih_of(h):
    try:
        return str(h.info_hashes().get_best())
    except AttributeError:
        return str(h.info_hash())


def tracker_status(h):
    rows = []
    try:
        for t in h.trackers():
            eps = t.get("endpoints") or [{}]
            fails = max((e.get("fails", 0) for e in eps), default=0)
            msg = next((e.get("message") for e in eps if e.get("message")), "")
            rows.append({"url": t.get("url", ""), "fails": fails, "message": msg})
    except Exception:
        pass
    return rows


class Engine:
    def __init__(self, cfg, probe=probe_interface, clock=time.time):
        self.cfg, self.probe, self.clock = cfg, probe, clock
        self.kill = False
        self.bound_ip = None
        self.listen_error = ""
        self.disk_warn_at = 0.0
        self.errors, self.handles = {}, {}
        self.first_seen, self.last_active = {}, {}
        self.total_down = self.total_up = self.total_conns = 0
        self.conn_limit = 0
        self.tuner = None
        self.ses = lt.session(self.build_settings())
        if self.kill:
            self.ses.pause()
        for host in ("router.bittorrent.com", "router.utorrent.com", "dht.transmissionbt.com"):
            self.ses.add_dht_router(host, 6881)
        self._load_resumed()

    # --- settings
    def _resolve_binding(self):
        port = int(self.cfg["listen_port"])
        want = self.cfg.get("interface", "")
        if not want:
            self.kill, self.bound_ip = False, None
            return f"0.0.0.0:{port},[::]:{port}", ""
        ip = self.probe(want)
        if ip is None:
            self.kill, self.bound_ip = True, None
            return "127.0.0.1:0", "127.0.0.1"  # nothing can leave the machine
        self.kill, self.bound_ip = False, ip
        return f"{ip}:{port}", ip

    def build_settings(self):
        s = dict(BASE)
        preset = PRESETS[self.cfg.get("preset", "balanced")]
        s.update(preset)
        enc = 0 if self.cfg.get("require_encryption") else 1  # 0 = forced, 1 = enabled (preferred)
        s.update({"out_enc_policy": enc, "in_enc_policy": enc})
        listen, outgoing = self._resolve_binding()
        s["listen_interfaces"] = listen
        s["outgoing_interfaces"] = outgoing
        self.conn_limit = preset["connections_limit"]
        self.tuner = AdaptiveTuner(50, min(4000, self.conn_limit * 2))
        return s

    def reapply(self):
        was_kill = self.kill
        self.ses.apply_settings(self.build_settings())
        if self.kill and not was_kill:
            self.ses.pause()
        elif was_kill and not self.kill:
            self.ses.resume()

    def set_preset(self, name):
        self.cfg["preset"] = name
        self.reapply()

    def set_interface(self, name):
        self.cfg["interface"] = name
        self.reapply()

    def set_encryption(self, required):
        self.cfg["require_encryption"] = bool(required)
        self.reapply()

    # --- torrents
    def _load_resumed(self):
        for f in RESUME_DIR.glob("*.fastresume"):
            try:
                h = self.ses.add_torrent(lt.read_resume_data(f.read_bytes()))
                self.handles[ih_of(h)] = h
            except Exception:
                pass

    def _register(self, h):
        ih = ih_of(h)
        self.handles[ih] = h
        self.first_seen.setdefault(ih, self.clock())
        return ih

    def add_file(self, path):
        Path(self.cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
        p = lt.add_torrent_params()
        p.save_path = self.cfg["download_dir"]
        p.ti = lt.torrent_info(path)
        return self._register(self.ses.add_torrent(p))

    def add_magnet(self, uri):
        Path(self.cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
        p = lt.parse_magnet_uri(uri)
        p.save_path = self.cfg["download_dir"]
        return self._register(self.ses.add_torrent(p))

    def remove(self, ih):
        h = self.handles.pop(ih, None)
        if h is not None:
            self.ses.remove_torrent(h)  # files stay on disk
        f = RESUME_DIR / f"{ih}.fastresume"
        if f.exists():
            f.unlink()

    # --- main loop
    def tick(self):
        """Call about once per second. Returns [(ih, save_path, name)] for torrents that just finished."""
        now = self.clock()
        finished = []
        for a in self.ses.pop_alerts():
            if isinstance(a, lt.torrent_finished_alert):
                s = a.handle.status()
                a.handle.pause()  # no file may be renamed/quarantined under an active torrent
                finished.append((ih_of(a.handle), s.save_path, s.name))
            elif isinstance(a, lt.save_resume_data_alert):
                self._write_resume(a)
            elif isinstance(a, (lt.torrent_error_alert, lt.file_error_alert)):
                self.errors[ih_of(a.handle)] = a.message()
            elif isinstance(a, lt.listen_failed_alert):
                self.listen_error = a.message()
            elif isinstance(a, lt.listen_succeeded_alert):
                self.listen_error = ""
            elif isinstance(a, lt.performance_alert) and "disk" in a.message().lower():
                self.disk_warn_at = now
        self._check_killswitch()
        self._track(now)
        self._tune(now)
        return finished

    def _check_killswitch(self):
        want = self.cfg.get("interface", "")
        if not want:
            if self.kill:
                self.reapply()
            return
        ip = self.probe(want)
        if (ip is None) != self.kill or (ip is not None and ip != self.bound_ip):
            self.reapply()

    def _track(self, now):
        d = u = c = 0
        for ih, h in self.handles.items():
            if not h.is_valid():
                continue
            s = h.status()
            self.first_seen.setdefault(ih, now)
            if s.download_rate > 0:
                self.last_active[ih] = now
            d += s.download_rate
            u += s.upload_rate
            c += s.num_connections
        self.total_down, self.total_up, self.total_conns = d, u, c

    def _tune(self, now):
        if not self.cfg.get("adaptive") or self.cfg.get("preset") == "quiet" or self.kill:
            return
        new = self.tuner.update(now, self.total_down, self.total_conns, self.conn_limit)
        if new:
            self.ses.apply_settings({"connections_limit": new})
            self.conn_limit = new

    # --- resume data
    def _write_resume(self, alert):
        try:
            (RESUME_DIR / f"{ih_of(alert.handle)}.fastresume").write_bytes(
                lt.write_resume_data_buf(alert.params))
        except Exception:
            pass

    def request_resume_save(self):
        flag = getattr(lt.torrent_handle, "save_info_dict", 0)
        for h in self.handles.values():
            if h.is_valid():
                h.save_resume_data(flag)

    def shutdown(self):
        self.request_resume_save()
        waiting = sum(1 for h in self.handles.values() if h.is_valid())
        deadline = time.time() + 10
        while waiting > 0 and time.time() < deadline:
            self.ses.wait_for_alert(500)
            for a in self.ses.pop_alerts():
                if isinstance(a, lt.save_resume_data_alert):
                    self._write_resume(a)
                    waiting -= 1
                elif isinstance(a, lt.save_resume_data_failed_alert):
                    waiting -= 1

    # --- inspector data
    def pieces(self, ih):
        h = self.handles.get(ih)
        if h is None or not h.is_valid():
            return []
        s = h.status()
        return list(s.pieces) if s.has_metadata else []

    def peers(self, ih, limit=200):
        h = self.handles.get(ih)
        out = []
        if h is None or not h.is_valid():
            return out
        for p in h.get_peer_info()[:limit]:
            client = p.client.decode(errors="ignore") if isinstance(p.client, bytes) else str(p.client)
            out.append({"ip": f"{p.ip[0]}:{p.ip[1]}", "client": client, "down": p.down_speed,
                        "up": p.up_speed, "progress": p.progress})
        return out

    def diagnostics(self, ih):
        h = self.handles.get(ih)
        out = []
        if h is None or not h.is_valid():
            return out
        s, now = h.status(), self.clock()
        paused = bool(s.flags & lt.torrent_flags.paused)

        def add(level, title, advice):
            out.append({"level": level, "title": title, "advice": advice})

        if self.kill:
            add("bad", "Kill switch engaged: bound network interface is down",
                f"Adapter '{self.cfg.get('interface')}' is unavailable, so all traffic is blocked. "
                "Reconnect your VPN; transfers resume automatically.")
        if self.listen_error:
            add("warn", "Cannot listen for incoming connections",
                "Another program may be using the port, or the bound interface changed. "
                "Try a different listen port; incoming peers are what make downloads fast.")
        if ih in self.errors:
            add("bad", "Torrent error", self.errors[ih])
        if s.progress >= 1.0:
            add("ok", "Download complete", "Check the Security tab for the scan result.")
            return out
        if paused and not self.kill:
            add("info", "Paused", "Resume it from the toolbar or the right-click menu.")
            return out
        since = now - self.first_seen.get(ih, now)
        if not s.has_metadata:
            if since > 45:
                add("bad", "Cannot fetch torrent metadata",
                    "No peer has answered for 45+ seconds. The magnet link may be dead or have no "
                    "trackers; try a different source. Make sure DHT is not blocked by your firewall.")
            return out
        if s.num_peers == 0 and since > 30:
            if s.list_seeds == 0 and s.list_peers == 0:
                add("bad", "No peers or seeds known",
                    "Trackers and DHT returned nothing. The torrent is probably dead.")
            else:
                add("warn", "Peers known but none connected",
                    "Likely a firewall or port-forwarding problem. Forward the listen port on your router.")
        elif s.num_seeds == 0 and s.list_seeds == 0 and s.download_rate == 0:
            add("warn", "Zero seeds", "Nobody has the complete file; it will only finish if a seed appears.")
        dc = s.distributed_copies
        if 0 <= dc < 1:
            add("warn", f"Swarm incomplete ({dc * 100:.0f}% of the file exists among connected peers)",
                "The missing pieces may never arrive. Wait for a seed or find another torrent.")
        bad_trackers = [t for t in tracker_status(h) if t["fails"] > 0]
        if bad_trackers and s.num_peers == 0:
            add("warn", f"{len(bad_trackers)} tracker(s) failing",
                (bad_trackers[0]["message"] or "tracker timeout") + ". DHT and PeX may still find peers.")
        if s.num_peers > 0 and s.download_rate == 0 and now - self.last_active.get(ih, self.first_seen.get(ih, now)) > 30:
            add("warn", "Connected but nothing is arriving",
                "Peers are choking you or lack the pieces you need. Wait a few minutes; "
                "if it persists, check the forwarded port and any bandwidth limits on your VPN.")
        if now - self.disk_warn_at < 60:
            add("warn", "Disk I/O is the bottleneck",
                "Save to an SSD, exclude the download folder from real-time antivirus, "
                "and close other disk-heavy programs.")
        if s.download_rate > 0 and not any(d["level"] in ("bad", "warn") for d in out):
            add("ok", "Healthy", "Downloading normally.")
        return out
