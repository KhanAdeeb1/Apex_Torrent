"""
Generates every icon and installer image from code (original artwork, no external files).

    python build_assets.py          (needs Pillow)

Outputs in ./assets:
    apextorrent.ico      app icon, 16/32/48/64/128/256 px mipmaps
    torrent.ico          file-type icon for .torrent files, same sizes
    apextorrent.png      512 px master (also used as Qt fallback icon)
    wizard_large.bmp/png installer welcome/finish sidebar, 164x314
    wizard_small.bmp/png installer header badge, 55x58
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets"
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
BLUE_TOP, BLUE_BOT = (94, 160, 255), (34, 84, 196)
CANVAS = (13, 15, 18)
ACCENT = (76, 141, 255)


def _rounded_mask(s, radius):
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, s - 1, s - 1), radius=radius, fill=255)
    return m


def _arrow(draw, s, color):
    """Download arrow over a tray, in unit coordinates of an s x s canvas."""
    draw.rectangle((0.43 * s, 0.20 * s, 0.57 * s, 0.50 * s), fill=color)
    draw.polygon([(0.27 * s, 0.44 * s), (0.73 * s, 0.44 * s), (0.50 * s, 0.71 * s)], fill=color)
    draw.rounded_rectangle((0.25 * s, 0.76 * s, 0.75 * s, 0.83 * s), radius=0.035 * s, fill=color)


def app_icon(s=1024):
    grad = Image.composite(Image.new("RGB", (s, s), BLUE_BOT), Image.new("RGB", (s, s), BLUE_TOP),
                           Image.linear_gradient("L").resize((s, s)))
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), _rounded_mask(s, int(s * 0.22)))
    _arrow(ImageDraw.Draw(img), s, (255, 255, 255, 255))
    return img


def torrent_icon(s=1024):
    """Document with a folded corner carrying the same arrow, so .torrent files read as 'ours'."""
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m, fold = 0.14 * s, 0.26 * s
    page = [(m, m), (s - m - fold, m), (s - m, m + fold), (s - m, s - m), (m, s - m)]
    d.polygon(page, fill=(24, 27, 32, 255))
    d.line(page + [page[0]], fill=ACCENT + (255,), width=int(0.035 * s), joint="curve")
    d.polygon([(s - m - fold, m), (s - m - fold, m + fold), (s - m, m + fold)], fill=(44, 52, 66, 255))
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    _arrow(ImageDraw.Draw(layer), s, ACCENT + (255,))
    k = int(s * 0.60)
    layer = layer.resize((k, k), Image.Resampling.LANCZOS)
    img.paste(layer, (int(0.20 * s), int(0.30 * s)), layer)
    return img


def save_ico(img, path):
    base = img.resize((256, 256), Image.Resampling.LANCZOS)
    base.save(path, format="ICO", sizes=ICO_SIZES)


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _centered(draw, w, y, text, font, fill):
    draw.text(((w - draw.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


def wizard_large():
    w, h = 164, 314
    bg = Image.composite(Image.new("RGB", (w, h), (20, 32, 56)), Image.new("RGB", (w, h), CANVAS),
                         Image.linear_gradient("L").resize((w, h)))
    icon = app_icon().resize((112, 112), Image.Resampling.LANCZOS)
    bg.paste(icon, ((w - 112) // 2, 44), icon)
    d = ImageDraw.Draw(bg)
    _centered(d, w, 176, "ApexTorrent", _font(21), (230, 237, 243))
    _centered(d, w, 206, "Fast. Clean. Yours.", _font(12), (139, 148, 158))
    _centered(d, w, 272, "Every download", _font(11), (110, 120, 132))
    _centered(d, w, 287, "security-scanned", _font(11), (110, 120, 132))
    return bg


def wizard_small():
    w, h = 55, 58
    bg = Image.new("RGB", (w, h), CANVAS)
    icon = app_icon().resize((44, 44), Image.Resampling.LANCZOS)
    bg.paste(icon, ((w - 44) // 2, (h - 44) // 2), icon)
    return bg


def main():
    OUT.mkdir(exist_ok=True)
    big = app_icon()
    save_ico(big, OUT / "apextorrent.ico")
    save_ico(torrent_icon(), OUT / "torrent.ico")
    big.resize((512, 512), Image.Resampling.LANCZOS).save(OUT / "apextorrent.png")
    for name, img in (("wizard_large", wizard_large()), ("wizard_small", wizard_small())):
        img.save(OUT / f"{name}.bmp", "BMP")
        img.save(OUT / f"{name}.png")
    for name in ("apextorrent.ico", "torrent.ico"):
        got = sorted(Image.open(OUT / name).ico.sizes())
        assert got == sorted(ICO_SIZES), f"{name}: missing mipmaps, got {got}"
    print("assets OK:", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
