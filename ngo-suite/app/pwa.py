"""Installable-app pieces generated on the fly so they follow the white-label brand:
the web app manifest and the home-screen icons (pure Python PNG, no image libraries)."""
import json, zlib, struct, re
from functools import lru_cache

def _hex(c):
    c = c if re.fullmatch(r"#[0-9a-fA-F]{6}", c or "") else "#0f5e63"
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))

@lru_cache(maxsize=16)
def icon_png(size, color):
    r, g, b = _hex(color)
    cx = cy = size / 2
    ro, ri, rd = size * 0.30, size * 0.20, size * 0.085
    rows = []
    for y in range(size):
        dy = (y + 0.5 - cy) ** 2
        row = bytearray([0])
        for x in range(size):
            d2 = (x + 0.5 - cx) ** 2 + dy
            on = (ri * ri <= d2 <= ro * ro) or d2 <= rd * rd
            row += b"\xff\xff\xff" if on else bytes((r, g, b))
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")

def manifest(settings):
    name = settings.get("brand_product") or "NGO Suite"
    color = settings.get("brand_color") or "#0f5e63"
    icons = [dict(src=f"/icon-{s}.png", sizes=f"{s}x{s}", type="image/png", purpose="any maskable") for s in (192, 512)]
    return json.dumps(dict(name=name, short_name=name[:12], description="Field work, photos and expense claims", start_url="/#/r/field", scope="/",
                           display="standalone", orientation="portrait", background_color="#f6f5f2", theme_color=color, icons=icons,
                           shortcuts=[dict(name="Log activity", url="/#/r/fieldact"), dict(name="Expense claim", url="/#/r/fieldclaim")])).encode()
