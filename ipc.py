"""Command-line parsing and single-instance forwarding, so clicking a magnet: link or a .torrent file
in an already-running ApexTorrent adds it to that window instead of starting a second copy."""
from __future__ import annotations

import getpass
import os

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

PING = "\x00ping"


def server_name():
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get("USERNAME", "user")
    return f"ApexTorrent-{user}"


def parse_args(argv):
    """Returns (items, minimized). Items are magnet: URIs or absolute .torrent paths."""
    items, minimized = [], False
    for a in argv:
        low = a.lower().strip('"')
        if low == "--minimized":
            minimized = True
        elif low.startswith("magnet:"):
            items.append(a.strip('"'))
        elif low.endswith(".torrent"):
            items.append(os.path.abspath(a.strip('"')))
    return items, minimized


END = b"\x00"  # message terminator; the server acknowledges with ACK once it has read everything
ACK = b"\x06"


def send_to_running(items, name=None, timeout=1500):
    """True if another instance received the message (it then handles items / raises its window).
    Waits for the server's acknowledgment: on Windows, disconnecting right after writing a named pipe can discard
    data the server has not read yet."""
    sock = QLocalSocket()
    sock.connectToServer(name or server_name())
    if not sock.waitForConnected(timeout):
        return False
    payload = ("\n".join(items) if items else PING).encode("utf-8") + END
    sock.write(payload)
    sock.flush()
    sock.waitForBytesWritten(timeout)  # returns False when flush() already wrote everything; not an error
    got_ack = sock.bytesAvailable() > 0 or sock.waitForReadyRead(timeout)
    ok = got_ack and bytes(sock.readAll()).startswith(ACK)
    sock.disconnectFromServer()
    return bool(ok)


def _alive(obj):
    try:
        obj.state()
        return True
    except RuntimeError:
        return False


class InstanceServer(QObject):
    received = Signal(list)  # list of magnet/path strings; empty list = just bring the window forward

    def __init__(self, name=None, parent=None):
        super().__init__(parent)
        name = name or server_name()
        QLocalServer.removeServer(name)  # clears a stale socket left by a crash
        self.server = QLocalServer(self)
        self.ok = self.server.listen(name)
        self.server.newConnection.connect(self._on_connection)

    def _on_connection(self):
        sock = self.server.nextPendingConnection()
        if sock is None:
            return
        buf = bytearray()
        done = []

        def finish():
            if done or not _alive(sock):
                return
            done.append(True)
            buf.extend(bytes(sock.readAll()))
            text = bytes(buf).rstrip(END).decode("utf-8", errors="ignore")
            items = [] if text == PING else [ln for ln in text.splitlines() if ln.strip()]
            self.received.emit(items)
            if sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
                sock.write(ACK)
                sock.flush()
            sock.disconnected.connect(sock.deleteLater)
            sock.disconnectFromServer()
            if sock.state() == QLocalSocket.LocalSocketState.UnconnectedState:
                sock.deleteLater()

        def on_ready():
            buf.extend(bytes(sock.readAll()))
            if buf.endswith(END):
                finish()

        sock.readyRead.connect(on_ready)
        sock.disconnected.connect(finish)  # sender left without the terminator: use whatever arrived
        on_ready()
        QTimer.singleShot(2000, finish)    # never leave a half-open connection behind
