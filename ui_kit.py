"""ApexTorrent design system: color tokens, line icons and the custom widgets the main window is built from.

Dark only, on purpose. Colors follow Apple's dark system palette for meaning (blue = active, green = safe,
amber = attention, red = danger) on a graphite-blue canvas.
"""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import (
    QEasingCurve, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTransform,
)
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QPushButton, QWidget,
)


# ----------------------------------------------------------------------------- tokens
class C:
    canvas = "#0B0D11"
    surface = "#10131A"
    raised = "#161A21"
    raised2 = "#1F242D"
    hair = "#222731"
    hair2 = "#2D3340"
    text = "#F4F6FA"
    text2 = "#A3ABBB"
    text3 = "#6F7789"
    accent = "#0A84FF"
    green = "#30D158"
    amber = "#FF9F0A"
    red = "#FF453A"
    cyan = "#64D2FF"


FAMILIES = ["Segoe UI Variable Display", "Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Display",
            "Helvetica Neue", "Arial"]


def rgba(color, alpha):
    c = QColor(color)
    c.setAlphaF(alpha)
    return c


def ui_font(px, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(FAMILIES)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


MED, SEMI = QFont.Weight.Medium, QFont.Weight.DemiBold


# ----------------------------------------------------------------------------- icons (24 x 24 grid, line style)
def _poly(p, *pts):
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)


def _build_paths():
    g = {}

    p = QPainterPath(); _poly(p, (12, 5), (12, 19)); _poly(p, (6.5, 13.5), (12, 19), (17.5, 13.5)); g["down"] = p
    p = QPainterPath(); _poly(p, (12, 19), (12, 5)); _poly(p, (6.5, 10.5), (12, 5), (17.5, 10.5)); g["up"] = p
    p = QPainterPath(); _poly(p, (5, 12.5), (10, 17.5), (19, 7)); g["check"] = p
    p = QPainterPath(); _poly(p, (9, 6.5), (9, 17.5)); _poly(p, (15, 6.5), (15, 17.5)); g["pause"] = p
    p = QPainterPath(); _poly(p, (8.5, 6), (18, 12), (8.5, 18)); p.closeSubpath(); g["play"] = p
    p = QPainterPath(); _poly(p, (9, 6), (15, 12), (9, 18)); g["chevron"] = p
    p = QPainterPath(); _poly(p, (6, 6), (18, 18)); _poly(p, (18, 6), (6, 18)); g["close"] = p

    p = QPainterPath()
    p.moveTo(3, 17.5); p.lineTo(3, 7.5); p.quadTo(3, 6, 4.5, 6); p.lineTo(9, 6); p.lineTo(11.5, 8.5)
    p.lineTo(19.5, 8.5); p.quadTo(21, 8.5, 21, 10); p.lineTo(21, 17.5); p.quadTo(21, 19, 19.5, 19)
    p.lineTo(4.5, 19); p.quadTo(3, 19, 3, 17.5); p.closeSubpath()
    g["folder"] = p

    p = QPainterPath()
    _poly(p, (4, 7), (20, 7)); _poly(p, (9, 7), (9, 5), (15, 5), (15, 7))
    p.moveTo(6, 7); p.lineTo(7, 19.2); p.quadTo(7.1, 20, 8, 20); p.lineTo(16, 20); p.quadTo(16.9, 20, 17, 19.2)
    p.lineTo(18, 7); _poly(p, (10.2, 11), (10.2, 16)); _poly(p, (13.8, 11), (13.8, 16))
    g["trash"] = p

    p = QPainterPath()
    for y, kx in ((7, 15), (12, 9), (17, 16)):
        p.moveTo(4, y); p.lineTo(kx - 2.4 - 1.2, y)
        p.moveTo(kx + 2.4 + 1.2, y); p.lineTo(20, y)
        p.addEllipse(QPointF(kx, y), 2.4, 2.4)
    g["sliders"] = p

    t = QTransform(); t.translate(12, 12); t.rotate(-45)
    q = QPainterPath(); q.addRoundedRect(QRectF(-10.5, -3.4, 11.5, 6.8), 3.4, 3.4)
    q.addRoundedRect(QRectF(-1, -3.4, 11.5, 6.8), 3.4, 3.4)
    g["link"] = t.map(q)

    p = QPainterPath()
    p.moveTo(12, 3.5); p.lineTo(19.5, 6.5); p.lineTo(19.5, 12)
    p.cubicTo(19.5, 16.5, 16.5, 19.6, 12, 21); p.cubicTo(7.5, 19.6, 4.5, 16.5, 4.5, 12)
    p.lineTo(4.5, 6.5); p.closeSubpath()
    g["shield"] = p
    p2 = QPainterPath(p); _poly(p2, (8.8, 12), (11, 14.2), (15.5, 9.6)); g["shield_check"] = p2

    p = QPainterPath()
    _poly(p, (12, 4.5), (21, 19.5), (3, 19.5)); p.closeSubpath()
    _poly(p, (12, 10.5), (12, 14.5)); _poly(p, (12, 17), (12, 17.02))
    g["warning"] = p

    p = QPainterPath(); p.addRoundedRect(QRectF(6, 11, 12, 9), 2.5, 2.5)
    p.moveTo(8.5, 11); p.lineTo(8.5, 8.5); p.arcTo(QRectF(8.5, 5, 7, 7), 180, -180); p.lineTo(15.5, 11)
    g["lock"] = p

    p = QPainterPath(); p.addEllipse(QPointF(12, 12), 9, 9); p.addEllipse(QPointF(12, 12), 4, 9)
    _poly(p, (3, 12), (21, 12)); g["globe"] = p

    p = QPainterPath(); p.addEllipse(QPointF(12, 12), 9, 9); _poly(p, (12, 7), (12, 12), (15.5, 14)); g["clock"] = p

    p = QPainterPath(); _poly(p, (12, 4), (12, 14)); _poly(p, (7.5, 10), (12, 14.5), (16.5, 10))
    _poly(p, (4, 14), (4, 19), (20, 19), (20, 14)); g["inbox"] = p
    return g


_PATHS = None
_FILLED = {"play"}


def paint_glyph(qp, name, rect, color, width=1.7):
    global _PATHS
    if _PATHS is None:
        _PATHS = _build_paths()
    path = _PATHS[name]
    qp.save()
    qp.setRenderHint(QPainter.Antialiasing)
    qp.translate(rect.topLeft())
    s = rect.width() / 24.0
    qp.scale(s, s)
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    qp.setPen(pen)
    qp.setBrush(QColor(color) if name in _FILLED else Qt.NoBrush)
    qp.drawPath(path)
    qp.restore()


def glyph_icon(name, color=C.text2, size=18, width=1.7):
    scale = 2
    icon = QIcon()
    for col, mode in ((color, QIcon.Normal),):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        paint_glyph(qp, name, QRectF(0, 0, size * scale, size * scale), col, width)
        qp.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm, mode)
    return icon


# ----------------------------------------------------------------------------- number formatting
def rate_parts(n):
    n = float(n)
    if n <= 0:
        return "0", "KB/s"
    for unit, div in (("GB/s", 1 << 30), ("MB/s", 1 << 20), ("KB/s", 1 << 10)):
        if n >= div:
            v = n / div
            return (f"{v:.1f}" if v < 100 else f"{v:.0f}"), unit
    return "<1", "KB/s"


# ----------------------------------------------------------------------------- header with live throughput
class Hero(QWidget):
    """The one expressive element: big live numbers over a smooth two-minute throughput graph."""
    SAMPLES = 120

    def __init__(self):
        super().__init__()
        self.setFixedHeight(156)
        self.hist = deque(maxlen=self.SAMPLES)
        self.down = self.up = 0.0
        self._scale = 256 * 1024.0

    def push(self, down, up):
        self.down, self.up = float(down), float(up)
        self.hist.append((self.down, self.up))
        target = max(max((d for d, _ in self.hist), default=0), max((u for _, u in self.hist), default=0),
                     256 * 1024.0) * 1.18
        self._scale = target if target > self._scale else self._scale + (target - self._scale) * 0.12
        self.update()

    def _curve(self, pts):
        path = QPainterPath(pts[0])
        for i in range(1, len(pts)):
            mid = QPointF((pts[i - 1].x() + pts[i].x()) / 2, (pts[i - 1].y() + pts[i].y()) / 2)
            path.quadTo(pts[i - 1], mid)
        path.lineTo(pts[-1])
        return path

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()

        # --- live numbers
        x = 32
        paint_glyph(qp, "down", QRectF(x, 24, 15, 15), C.accent, 2.0)
        qp.setFont(ui_font(13, MED))
        qp.setPen(C.text2)
        qp.drawText(QRectF(x + 21, 22, 160, 20), Qt.AlignVCenter | Qt.AlignLeft, "Download")
        num, unit = rate_parts(self.down)
        big = ui_font(52, SEMI)
        qp.setFont(big)
        qp.setPen(C.text if self.down > 0 else C.text3)
        nw = qp.fontMetrics().horizontalAdvance(num)
        baseline = 97
        qp.drawText(QPointF(x - 2, baseline), num)
        qp.setFont(ui_font(18, MED))
        qp.setPen(C.text2)
        qp.drawText(QPointF(x + nw + 8, baseline), unit)
        paint_glyph(qp, "up", QRectF(x, 112, 13, 13), C.cyan, 2.0)
        un, uu = rate_parts(self.up)
        qp.setFont(ui_font(13, MED))
        qp.setPen(C.text2)
        qp.drawText(QRectF(x + 19, 109, 220, 19), Qt.AlignVCenter | Qt.AlignLeft, f"{un} {uu} upload")

        # --- graph
        gx = max(330, int(w * 0.36))
        gr = QRectF(gx, 18, w - gx, h - 18)
        base = h - 30
        top = gr.top() + 14
        qp.setFont(ui_font(11, MED))
        qp.setPen(C.text3)
        qp.drawText(QRectF(gx, base + 6, 200, 16), Qt.AlignLeft | Qt.AlignVCenter, "Last 2 minutes")
        peak = max((d for d, _ in self.hist), default=0)
        if peak > 0:
            pn, pu = rate_parts(peak)
            qp.drawText(QRectF(w - 232, base + 6, 200, 16), Qt.AlignRight | Qt.AlignVCenter, f"Peak {pn} {pu}")

        def baseline():
            qp.setPen(QPen(rgba("#FFFFFF", 0.07), 1))
            qp.drawLine(QPointF(gx, base), QPointF(w - 32, base))

        n = len(self.hist)
        if n < 2:
            baseline()
            return
        gw = (w - 32) - gx
        step = gw / (self.SAMPLES - 1)
        x0 = (w - 32) - step * (n - 1)

        def pts_for(idx):
            return [QPointF(x0 + i * step, base - (v[idx] / self._scale) * (base - top))
                    for i, v in enumerate(self.hist)]

        fade = QLinearGradient(gx, 0, gx + 90, 0)
        up_pts = pts_for(1)
        if any(u > 0 for _, u in self.hist):
            fade.setColorAt(0, rgba(C.cyan, 0.0)); fade.setColorAt(1, rgba(C.cyan, 0.85))
            qp.setPen(QPen(fade, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            qp.setBrush(Qt.NoBrush)
            qp.drawPath(self._curve(up_pts))
        dn_pts = pts_for(0)
        curve = self._curve(dn_pts)
        area = QPainterPath(curve)
        area.lineTo(dn_pts[-1].x(), base)
        area.lineTo(dn_pts[0].x(), base)
        area.closeSubpath()
        vg = QLinearGradient(0, top, 0, base)
        vg.setColorAt(0, rgba(C.accent, 0.34))
        vg.setColorAt(1, rgba(C.accent, 0.0))
        qp.setPen(Qt.NoPen)
        qp.setBrush(vg)
        qp.drawPath(area)
        edge = QLinearGradient(gx, 0, gx + 130, 0)  # soften the left edge so the graph emerges from the canvas
        edge.setColorAt(0, rgba(C.canvas, 1.0))
        edge.setColorAt(1, rgba(C.canvas, 0.0))
        qp.setBrush(edge)
        qp.drawRect(QRectF(gx - 1, top - 4, 132, base - top + 5))
        baseline()
        lf = QLinearGradient(gx, 0, gx + 90, 0)
        lf.setColorAt(0, rgba(C.accent, 0.0)); lf.setColorAt(1, rgba(C.accent, 1.0))
        qp.setPen(QPen(lf, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.setBrush(Qt.NoBrush)
        qp.drawPath(curve)
        if self.down > 0:
            end = dn_pts[-1]
            qp.setPen(Qt.NoPen)
            qp.setBrush(rgba(C.accent, 0.25))
            qp.drawEllipse(end, 7, 7)
            qp.setBrush(C.accent)
            qp.drawEllipse(end, 3.6, 3.6)


# ----------------------------------------------------------------------------- segmented control
class Segmented(QFrame):
    changed = Signal(str)

    def __init__(self, items, value=None):
        super().__init__()
        self.setObjectName("seg")
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for key, label in items:
            b = QPushButton(label)
            b.setObjectName("segbtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b
        self.value = value or items[0][0]
        self.buttons[self.value].setChecked(True)

    def _pick(self, key):
        if key != self.value:
            self.value = key
            self.changed.emit(key)

    def set(self, key):
        if key in self.buttons:
            self.value = key
            self.buttons[key].setChecked(True)

    def set_label(self, key, text):
        self.buttons[key].setText(text)

    def set_tip(self, key, tip):
        self.buttons[key].setToolTip(tip)


# ----------------------------------------------------------------------------- switch
class Switch(QAbstractButton):
    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 28)
        self._t = 1.0 if checked else 0.0
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(160)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._step)
        self.toggled.connect(self._go)

    def _step(self, v):
        self._t = float(v)
        self.update()

    def _go(self, on):
        self.anim.stop()
        self.anim.setStartValue(self._t)
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        off, on = QColor("#3A4150"), QColor(C.green)
        t = self._t
        col = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                     int(off.blue() + (on.blue() - off.blue()) * t))
        qp.setPen(Qt.NoPen)
        qp.setBrush(col)
        r = QRectF(0, 0, self.width(), self.height())
        qp.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = 3 + (r.width() - d - 6) * t
        qp.setBrush(QColor("#FFFFFF"))
        qp.drawEllipse(QRectF(x, 3, d, d))


# ----------------------------------------------------------------------------- empty state and drop overlay
class EmptyState(QWidget):
    def __init__(self):
        super().__init__()
        self.title, self.body = "", ""

    def set_text(self, title, body):
        self.title, self.body = title, body
        self.update()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.TextAntialiasing)
        cx, cy = self.width() / 2, self.height() * 0.42
        tile = QRectF(cx - 40, cy - 78, 80, 80)
        qp.setPen(QPen(rgba("#FFFFFF", 0.06), 1))
        qp.setBrush(C.raised)
        qp.drawRoundedRect(tile, 24, 24)
        paint_glyph(qp, "inbox", QRectF(cx - 18, cy - 56, 36, 36), C.text2, 1.5)
        qp.setFont(ui_font(19, SEMI))
        qp.setPen(C.text)
        qp.drawText(QRectF(cx - 240, cy + 18, 480, 28), Qt.AlignCenter, self.title)
        qp.setFont(ui_font(14))
        qp.setPen(C.text2)
        qp.drawText(QRectF(cx - 190, cy + 52, 380, 60), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.body)


class DropOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        qp.setBrush(rgba(C.canvas, 0.92))
        qp.setPen(Qt.NoPen)
        qp.drawRect(self.rect())
        qp.setBrush(rgba(C.accent, 0.10))
        pen = QPen(rgba(C.accent, 0.9), 2, Qt.DashLine)
        qp.setPen(pen)
        qp.drawRoundedRect(r, 22, 22)
        cx, cy = r.center().x(), r.center().y()
        paint_glyph(qp, "inbox", QRectF(cx - 24, cy - 56, 48, 48), C.accent, 1.5)
        qp.setFont(ui_font(20, SEMI))
        qp.setPen(C.text)
        qp.drawText(QRectF(cx - 200, cy + 8, 400, 30), Qt.AlignCenter, "Drop to add")
        qp.setFont(ui_font(14))
        qp.setPen(C.text2)
        qp.drawText(QRectF(cx - 200, cy + 40, 400, 24), Qt.AlignCenter, ".torrent files or magnet links")


# ----------------------------------------------------------------------------- toast
class Toast(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.text, self.kind = "", "info"
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        self.fx.setOpacity(0.0)
        self.anim = QPropertyAnimation(self.fx, b"opacity", self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text, kind="info", ms=4500):
        self.text, self.kind = text, kind
        fm = QFontMetrics(ui_font(14, MED))
        self.resize(min(self.parent().width() - 60, fm.horizontalAdvance(text) + 84), 46)
        self.place()
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setDuration(180)
        self.anim.setStartValue(self.fx.opacity())
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(ms)
        self.update()

    def place(self):
        p = self.parent()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 82)

    def _fade_out(self):
        self.anim.stop()
        self.anim.setDuration(300)
        self.anim.setStartValue(self.fx.opacity())
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self._done)
        self.anim.start()

    def _done(self):
        try:
            self.anim.finished.disconnect(self._done)
        except (RuntimeError, TypeError):
            pass
        if self.fx.opacity() <= 0.01:
            self.hide()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setRenderHint(QPainter.TextAntialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        qp.setPen(QPen(QColor(C.hair2), 1))
        qp.setBrush(QColor("#222834"))
        qp.drawRoundedRect(r, 16, 16)
        col = {"ok": C.green, "warn": C.amber, "bad": C.red}.get(self.kind, C.accent)
        qp.setPen(Qt.NoPen)
        qp.setBrush(rgba(col, 0.22))
        qp.drawEllipse(QPointF(26, r.height() / 2), 9, 9)
        qp.setBrush(col)
        qp.drawEllipse(QPointF(26, r.height() / 2), 4.2, 4.2)
        qp.setFont(ui_font(14, MED))
        qp.setPen(C.text)
        fm = qp.fontMetrics()
        qp.drawText(QRectF(46, 0, r.width() - 58, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                    fm.elidedText(self.text, Qt.ElideRight, int(r.width() - 58)))
