"""Minimal QR Code generator (byte mode, error correction M, versions 1-10). Pure Python, no dependencies.
Returns an SVG string. Algorithm follows ISO/IEC 18004; verified by decoding with a real QR reader in the tests."""

_DATA_CW = [16, 28, 44, 64, 86, 108, 124, 154, 182, 216]            # data codewords, level M, versions 1..10
_ECC_PER_BLOCK = [10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
_BLOCKS = [1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
_TOTAL_CW = [26, 44, 70, 100, 134, 172, 196, 242, 292, 346]
_ALIGN = [[], [6, 18], [6, 22], [6, 26], [6, 30], [6, 34], [6, 22, 38], [6, 24, 42], [6, 26, 46], [6, 28, 50]]

def _mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z

def _divisor(deg):
    r = [0] * (deg - 1) + [1]; root = 1
    for _ in range(deg):
        for j in range(deg):
            r[j] = _mul(r[j], root)
            if j + 1 < deg: r[j] ^= r[j + 1]
        root = _mul(root, 2)
    return r

def _remainder(data, div):
    r = [0] * len(div)
    for b in data:
        f = b ^ r.pop(0); r.append(0)
        for i, c in enumerate(div): r[i] ^= _mul(c, f)
    return r

def _bits(val, n): return [(val >> i) & 1 for i in range(n - 1, -1, -1)]

def _encode(data: bytes):
    for ver in range(1, 11):
        cc = 8 if ver < 10 else 16
        if 4 + cc + 8 * len(data) <= _DATA_CW[ver - 1] * 8: break
    else:
        raise ValueError("Text too long for the QR code")
    bits = _bits(0b0100, 4) + _bits(len(data), cc)
    for b in data: bits += _bits(b, 8)
    cap = _DATA_CW[ver - 1] * 8
    bits += [0] * min(4, cap - len(bits))
    bits += [0] * (-len(bits) % 8)
    cw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(cw) < _DATA_CW[ver - 1]:
        cw.append(pad); pad ^= 0xEC ^ 0x11
    nb, el, total = _BLOCKS[ver - 1], _ECC_PER_BLOCK[ver - 1], _TOTAL_CW[ver - 1]
    nshort, slen = nb - total % nb, total // nb
    div = _divisor(el); blocks = []; k = 0
    for i in range(nb):
        d = cw[k:k + slen - el + (0 if i < nshort else 1)]; k += len(d)
        e = _remainder(d, div)
        if i < nshort: d = d + [0]
        blocks.append(d + e)
    out = []
    for i in range(len(blocks[0])):
        for j, b in enumerate(blocks):
            if i != slen - el or j >= nshort: out.append(b[i])
    return ver, out

class _Grid:
    def __init__(self, ver):
        self.ver = ver; self.n = ver * 4 + 17
        self.m = [[False] * self.n for _ in range(self.n)]; self.fn = [[False] * self.n for _ in range(self.n)]
        self._patterns()
    def _set(self, x, y, dark):
        self.m[y][x] = bool(dark); self.fn[y][x] = True
    def _patterns(self):
        n = self.n
        for i in range(n): self._set(6, i, i % 2 == 0); self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy)); self._set(x, y, d not in (2, 4))
        pos = _ALIGN[self.ver - 1]
        for i, py in enumerate(pos):
            for j, px in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0): continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3): self._set(px + dx, py + dy, max(abs(dx), abs(dy)) != 1)
        self._format(0)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12): rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                a, b = n - 11 + i % 3, i // 3
                self._set(a, b, (bits >> i) & 1); self._set(b, a, (bits >> i) & 1)
    def _format(self, mask):
        n = self.n; data = (0 << 3) | mask; rem = data
        for _ in range(10): rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        g = lambda i: (bits >> i) & 1
        for i in range(6): self._set(8, i, g(i))
        self._set(8, 7, g(6)); self._set(8, 8, g(7)); self._set(7, 8, g(8))
        for i in range(9, 15): self._set(14 - i, 8, g(i))
        for i in range(8): self._set(n - 1 - i, 8, g(i))
        for i in range(8, 15): self._set(8, n - 15 + i, g(i))
        self._set(8, n - 8, True)
    def place(self, cw):
        n, i = self.n, 0
        for right in range(n - 1, 0, -2):
            if right == 6: right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j; up = ((right + 1) & 2) == 0; y = (n - 1 - vert) if up else vert
                    if not self.fn[y][x] and i < len(cw) * 8:
                        self.m[y][x] = ((cw[i >> 3] >> (7 - (i & 7))) & 1) == 1; i += 1
    def mask(self, k):
        f = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
             lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
             lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0][k]
        for y in range(self.n):
            for x in range(self.n):
                if not self.fn[y][x] and f(x, y): self.m[y][x] = not self.m[y][x]
    def penalty(self):
        n, m, p = self.n, self.m, 0
        for lines in (m, [list(c) for c in zip(*m)]):
            for row in lines:
                run, prev = 1, row[0]
                for v in row[1:]:
                    if v == prev: run += 1
                    else:
                        if run >= 5: p += 3 + run - 5
                        run, prev = 1, v
                if run >= 5: p += 3 + run - 5
                s = "".join("1" if v else "0" for v in row)
                p += 40 * (s.count("10111010000") + s.count("00001011101"))
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]: p += 3
        dark = sum(v for row in m for v in row); total = n * n
        p += 10 * (abs(dark * 20 - total * 10) // total)
        return p

def make_svg(text: str, size_px: int = 220, border: int = 4) -> str:
    ver, cw = _encode(text.encode("utf-8"))
    best = None
    for k in range(8):
        g = _Grid(ver); g.place(cw); g.mask(k); g._format(k)
        pen = g.penalty()
        if best is None or pen < best[0]: best = (pen, g)
    g = best[1]; n = g.n; dim = n + border * 2
    path = "".join(f"M{x + border},{y + border}h1v1h-1z" for y in range(n) for x in range(n) if g.m[y][x])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" width="{size_px}" height="{size_px}" shape-rendering="crispEdges">'
            f'<rect width="100%" height="100%" fill="#fff"/><path d="{path}" fill="#000"/></svg>')

def make_matrix(text: str, mask=None):
    ver, cw = _encode(text.encode("utf-8")); g = _Grid(ver); g.place(cw)
    k = 0 if mask is None else mask
    g.mask(k); g._format(k); return g.m
