#!/usr/bin/env python3
"""
HIGHWAY CLASSIC  -  a retro top-down arcade racer for touch screens
-------------------------------------------------------------------
Made for Android (Pydroid 3) but runs anywhere Python 3 + pygame runs.

TOUCH   hold the LEFT half of the screen  = steer left
        hold the RIGHT half of the screen = steer right
        hold the round NITRO button       = boost (fill it with coins
                                            and close calls!)
        tap the II button (top right)     = pause
KEYS    arrows / A D steer, SPACE nitro, P pause, ESC menu (desktop testing)

Drive 4 themed stages, grab coins and fuel, dodge traffic and oil.
You have 3 hearts. Run out of hearts or fuel and it is game over.
"""
import math
import random
import os
import sys
import array
import time

import pygame

# ----------------------------------------------------------------------------
# constants
# ----------------------------------------------------------------------------
W, H = 480, 800                      # logical (portrait) resolution
FPS = 60
ROAD_W = 300
ROAD_X = (W - ROAD_W) // 2
LANES = 4
LANE_W = ROAD_W / LANES
STAGE_METERS = 900
PLAYER_Y = 585
SMOOTH_SCALE = False                 # True = prettier upscaling, slower on weak phones

THEMES = [
    dict(name="SUNNY COUNTRYSIDE", g1=(78, 168, 66), g2=(70, 156, 60),
         road=(66, 66, 72), night=0, warm=0, snow=0,
         scen=["tree", "tree", "bush", "flower", "house", "bush"]),
    dict(name="DESERT SUNSET", g1=(226, 176, 100), g2=(214, 162, 88),
         road=(78, 64, 62), night=0, warm=1, snow=0,
         scen=["cactus", "cactus", "rock", "palm", "rock", "palm"]),
    dict(name="NEON NIGHT CITY", g1=(20, 18, 44), g2=(27, 22, 56),
         road=(36, 36, 50), night=1, warm=0, snow=0,
         scen=["building", "lamp", "building", "sign", "lamp", "building"]),
    dict(name="SNOWY PINES", g1=(228, 238, 248), g2=(214, 227, 241),
         road=(88, 92, 104), night=0, warm=0, snow=1,
         scen=["pine", "pine", "snowman", "rock", "pine", "pine"]),
]
CAR_COLORS = [(214, 40, 40), (40, 110, 220), (250, 200, 30),
              (40, 170, 90), (238, 238, 238)]
TRAFFIC_COLORS = [(70, 130, 200), (230, 120, 40), (150, 60, 160),
                  (60, 160, 120), (200, 200, 205), (90, 90, 100),
                  (180, 50, 60), (40, 60, 90)]


def lane_x(i):
    return ROAD_X + LANE_W * (i + 0.5)


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_col(c1, c2, t):
    return (int(lerp(c1[0], c2[0], t)), int(lerp(c1[1], c2[1], t)),
            int(lerp(c1[2], c2[2], t)))


def shade(c, f):
    return (int(clamp(c[0] * f, 0, 255)), int(clamp(c[1] * f, 0, 255)),
            int(clamp(c[2] * f, 0, 255)))


# ----------------------------------------------------------------------------
# drawing helpers
# ----------------------------------------------------------------------------
def rrect(s, col, rect, r=6, width=0):
    """rounded rectangle, falls back to a plain one on old pygame"""
    try:
        pygame.draw.rect(s, col, rect, width, border_radius=r)
    except TypeError:
        pygame.draw.rect(s, col, rect, width)


_fonts = {}


def font(sz):
    f = _fonts.get(sz)
    if f is None:
        f = pygame.font.Font(None, sz)
        _fonts[sz] = f
    return f


def text(s, msg, sz, col, pos, anchor="center", shadow=(0, 0, 0), sh=2,
         bold=False):
    f = font(sz)
    img = f.render(msg, True, col)
    r = img.get_rect()
    setattr(r, anchor, (int(pos[0]), int(pos[1])))
    if shadow:
        s.blit(f.render(msg, True, shadow), (r.x + sh, r.y + sh))
    s.blit(img, r)
    if bold:
        s.blit(img, (r.x + 1, r.y))
    return r


_glow_cache = {}


def glow(s, x, y, r, col, a=150):
    """soft round light (pre-rendered, cached)"""
    key = (r, col, a)
    g = _glow_cache.get(key)
    if g is None:
        g = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        steps = 14
        for i in range(steps):
            rr = max(1, int(r * (1 - i / steps)))
            al = int(a * ((i + 1) / steps) ** 2)
            pygame.draw.circle(g, (col[0], col[1], col[2], al), (r, r), rr)
        _glow_cache[key] = g
    s.blit(g, (int(x - r), int(y - r)))


def ring_progress(s, cx, cy, r, width, frac, col, back=(40, 40, 55)):
    """circular progress ring built from little quads (works everywhere)"""
    n = 48
    for i in range(n):
        a0 = -math.pi / 2 + 2 * math.pi * i / n
        a1 = -math.pi / 2 + 2 * math.pi * (i + 1.15) / n
        c = col if (i + 0.5) / n <= frac else back
        pts = [(cx + math.cos(a0) * r, cy + math.sin(a0) * r),
               (cx + math.cos(a1) * r, cy + math.sin(a1) * r),
               (cx + math.cos(a1) * (r - width), cy + math.sin(a1) * (r - width)),
               (cx + math.cos(a0) * (r - width), cy + math.sin(a0) * (r - width))]
        pygame.draw.polygon(s, c, pts)


# ----------------------------------------------------------------------------
# sound (all generated in code - no files needed)
# ----------------------------------------------------------------------------
class Sfx:
    def __init__(self):
        self.ok = False
        self.on = True
        self.snd = {}
        self.engine = []
        self.tier = -1
        self.chan = None
        try:
            info = pygame.mixer.get_init()
            if not info or info[1] != -16:          # we generate 16-bit samples
                if info:
                    pygame.mixer.quit()
                pygame.mixer.init(22050, -16, 2, 512)
            info = pygame.mixer.get_init()
            self.rate, self.chs = info[0], info[2]
            self.snd["coin"] = self._tone([988, 1319], 0.16, 0.35, "sq")
            self.snd["fuel"] = self._tone([523, 659, 784, 1047], 0.32, 0.35, "sq")
            self.snd["heart"] = self._tone([660, 880, 1320], 0.3, 0.35, "sin")
            self.snd["near"] = self._tone([1500, 1900], 0.1, 0.25, "sq")
            self.snd["crash"] = self._tone([120], 0.6, 0.6, "noise")
            self.snd["oil"] = self._tone([400, 330, 260, 200, 150], 0.45, 0.3, "sin")
            self.snd["nitro"] = self._tone([200, 300, 450, 700], 0.35, 0.3, "sq")
            self.snd["go"] = self._tone([880], 0.35, 0.35, "sq")
            self.snd["tick"] = self._tone([440], 0.12, 0.3, "sq")
            self.snd["over"] = self._tone([440, 370, 311, 261, 196], 0.9, 0.35, "sq")
            self.snd["stage"] = self._tone([523, 659, 784, 1047, 784, 1047], 0.6, 0.3, "sq")
            self.snd["low"] = self._tone([900, 700], 0.18, 0.25, "sq")
            for f in (52, 74, 100):
                self.engine.append(self._loop(f))
            self.ok = True
        except Exception:
            self.ok = False

    def _pack(self, samples):
        buf = array.array("h")
        for v in samples:
            iv = int(clamp(v, -1, 1) * 32767)
            buf.append(iv)
            if self.chs == 2:
                buf.append(iv)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def _tone(self, freqs, dur, vol, wave):
        n = int(self.rate * dur)
        out = []
        phase = 0.0
        for i in range(n):
            f = freqs[min(len(freqs) - 1, int(i / n * len(freqs)))]
            phase += f / self.rate
            if wave == "sq":
                v = 1.0 if (phase % 1.0) < 0.5 else -1.0
            elif wave == "sin":
                v = math.sin(phase * 2 * math.pi)
            else:
                v = random.uniform(-1, 1)
            out.append(v * (1 - i / n) * vol)
        return self._pack(out)

    def _loop(self, f):
        cycles = max(1, int(0.25 * f))
        n = int(self.rate * cycles / f)
        out = []
        for i in range(n):
            ph = (i * f / self.rate) % 1.0
            v = (ph * 2 - 1) * 0.5 + math.sin(ph * 6.2832 * 2) * 0.3
            out.append(v * 0.22)
        s = self._pack(out)
        return s

    def play(self, name):
        if self.ok and self.on and name in self.snd:
            try:
                self.snd[name].play()
            except Exception:
                pass

    def engine_update(self, frac, running):
        if not (self.ok and self.on) or not running:
            self.engine_stop()
            return
        tier = 0 if frac < 0.45 else (1 if frac < 0.8 else 2)
        if tier != self.tier:
            self.engine_stop()
            try:
                self.chan = self.engine[tier].play(loops=-1)
                self.tier = tier
            except Exception:
                pass

    def engine_stop(self):
        if self.ok and self.chan is not None:
            try:
                self.chan.stop()
            except Exception:
                pass
        self.chan = None
        self.tier = -1


# ----------------------------------------------------------------------------
# procedural art - every sprite is drawn with code
# ----------------------------------------------------------------------------
CAR_DIMS = {"sedan": (36, 66), "taxi": (36, 66), "van": (40, 78),
            "truck": (44, 126), "player": (38, 70)}
PAD = 7


def make_car(kind, body):
    w, h = CAR_DIMS[kind]
    s = pygame.Surface((w + PAD * 2, h + PAD * 2), pygame.SRCALPHA)
    ox = oy = PAD
    rrect(s, (0, 0, 0, 80), (ox + 3, oy + 5, w, h), 10)          # shadow
    wheel = (18, 18, 20)
    if kind == "truck":
        wys = [oy + 14, oy + h - 50, oy + h - 28]
    else:
        wys = [oy + int(h * 0.15), oy + int(h * 0.68)]
    for wy in wys:
        rrect(s, wheel, (ox - 3, wy, 8, 15), 3)
        rrect(s, wheel, (ox + w - 5, wy, 8, 15), 3)
    dark_glass = (34, 52, 84)
    if kind == "truck":
        trailer = shade(body, 1.0)
        rrect(s, (60, 62, 70), (ox + 6, oy + 36, w - 12, 12), 3)   # coupling
        rrect(s, trailer, (ox, oy + 44, w, h - 44), 5)
        for yy in range(oy + 52, oy + h - 6, 12):                   # ribs
            pygame.draw.line(s, shade(trailer, 0.8), (ox + 3, yy),
                             (ox + w - 4, yy), 2)
        rrect(s, shade(trailer, 1.25), (ox + 4, oy + 47, w - 8, 5), 2)
        cab = shade(body, 0.7)
        rrect(s, cab, (ox + 2, oy, w - 4, 42), 9)
        rrect(s, shade(cab, 1.3), (ox + 6, oy + 3, w - 12, 8), 4)
        pygame.draw.polygon(s, dark_glass, [(ox + 7, oy + 14), (ox + w - 7, oy + 14),
                                            (ox + w - 9, oy + 26), (ox + 9, oy + 26)])
        pygame.draw.rect(s, (255, 240, 160), (ox + 5, oy + 1, 7, 4))
        pygame.draw.rect(s, (255, 240, 160), (ox + w - 12, oy + 1, 7, 4))
        pygame.draw.rect(s, (200, 30, 30), (ox + 4, oy + h - 5, 9, 4))
        pygame.draw.rect(s, (200, 30, 30), (ox + w - 13, oy + h - 5, 9, 4))
        return s
    rrect(s, body, (ox, oy, w, h), 11)
    rrect(s, shade(body, 1.18), (ox + 4, oy + 3, w - 8, int(h * 0.27)), 7)   # hood
    if kind == "van":
        roof = shade(body, 0.9)
        rrect(s, roof, (ox + 3, oy + int(h * 0.30), w - 6, int(h * 0.62)), 5)
        for yy in range(oy + int(h * 0.36), oy + int(h * 0.9), 9):
            pygame.draw.line(s, shade(roof, 0.8), (ox + 6, yy), (ox + w - 7, yy), 1)
        pygame.draw.polygon(s, dark_glass, [(ox + 6, oy + int(h * 0.22)),
                                            (ox + w - 6, oy + int(h * 0.22)),
                                            (ox + w - 8, oy + int(h * 0.31)),
                                            (ox + 8, oy + int(h * 0.31))])
    elif kind == "player":
        for dx in (-7, 2):                                           # racing stripes
            rrect(s, (245, 245, 245), (ox + w // 2 + dx, oy + 2, 5, h - 4), 2)
        rrect(s, (24, 26, 34), (ox + 7, oy + int(h * 0.34), w - 14, int(h * 0.30)), 6)
        pygame.draw.circle(s, (240, 200, 60), (ox + w // 2, oy + int(h * 0.47)), 5)
        pygame.draw.polygon(s, dark_glass, [(ox + 7, oy + int(h * 0.30)),
                                            (ox + w - 7, oy + int(h * 0.30)),
                                            (ox + w - 9, oy + int(h * 0.36)),
                                            (ox + 9, oy + int(h * 0.36))])
        rrect(s, shade(body, 0.75), (ox + 3, oy + h - 9, w - 6, 5), 2)     # spoiler
        pygame.draw.circle(s, (255, 245, 190), (ox + 9, oy + 6), 4)
        pygame.draw.circle(s, (255, 245, 190), (ox + w - 9, oy + 6), 4)
    else:
        cab_y = oy + int(h * 0.31)
        rrect(s, shade(body, 0.86), (ox + 5, cab_y, w - 10, int(h * 0.40)), 6)
        rrect(s, shade(body, 1.05), (ox + 8, cab_y + 8, w - 16, int(h * 0.40) - 16), 4)
        pygame.draw.polygon(s, dark_glass, [(ox + 7, oy + int(h * 0.27)),
                                            (ox + w - 7, oy + int(h * 0.27)),
                                            (ox + w - 9, cab_y + 5), (ox + 9, cab_y + 5)])
        pygame.draw.polygon(s, dark_glass, [(ox + 9, oy + int(h * 0.68)),
                                            (ox + w - 9, oy + int(h * 0.68)),
                                            (ox + w - 7, oy + int(h * 0.76)),
                                            (ox + 7, oy + int(h * 0.76))])
        if kind == "taxi":
            rrect(s, (250, 250, 250), (ox + w // 2 - 9, oy + int(h * 0.47), 18, 8), 3)
            pygame.draw.rect(s, (20, 20, 20), (ox + w // 2 - 6, oy + int(h * 0.47) + 2, 12, 4))
            for i in range(6):
                c = (20, 20, 20) if i % 2 == 0 else (245, 245, 245)
                pygame.draw.rect(s, c, (ox + 1, oy + int(h * 0.34) + i * 5, 3, 5))
                pygame.draw.rect(s, c, (ox + w - 4, oy + int(h * 0.34) + i * 5, 3, 5))
    pygame.draw.rect(s, (255, 240, 160), (ox + 4, oy + 1, 8, 4))
    pygame.draw.rect(s, (255, 240, 160), (ox + w - 12, oy + 1, 8, 4))
    pygame.draw.rect(s, (205, 28, 28), (ox + 4, oy + h - 5, 9, 4))
    pygame.draw.rect(s, (205, 28, 28), (ox + w - 13, oy + h - 5, 9, 4))
    rrect(s, shade(body, 0.7), (ox - 1, oy + int(h * 0.30), 3, 6), 1)     # mirrors
    rrect(s, shade(body, 0.7), (ox + w - 2, oy + int(h * 0.30), 3, 6), 1)
    return s


def _blob(s, col, cx, cy, r):
    pygame.draw.circle(s, col, (cx, cy), r)


def make_scenery(kind):
    random.seed(hash(kind) & 0xffff)
    if kind == "tree":
        s = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 60), (12, 18, 46, 42))
        _blob(s, (30, 100, 40), 30, 30, 24)
        for dx, dy in ((-11, -6), (10, -8), (0, 11), (-9, 9), (11, 8)):
            _blob(s, (44, 128, 50), 30 + dx, 30 + dy, 13)
        for dx, dy in ((-8, -10), (7, -4), (-2, 6)):
            _blob(s, (84, 170, 70), 28 + dx, 28 + dy, 7)
        return [s]
    if kind == "bush":
        s = pygame.Surface((36, 30), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 50), (4, 12, 30, 16))
        for dx, dy, r in ((10, 12, 9), (22, 12, 10), (16, 8, 9)):
            _blob(s, (38, 120, 46), dx, dy, r)
        _blob(s, (80, 165, 70), 14, 8, 4)
        return [s]
    if kind == "flower":
        s = pygame.Surface((34, 30), pygame.SRCALPHA)
        for i in range(9):
            col = random.choice([(240, 70, 90), (255, 220, 60), (250, 250, 250),
                                 (240, 130, 220)])
            x, y = random.randint(4, 29), random.randint(4, 25)
            pygame.draw.line(s, (40, 130, 50), (x, y), (x, y + 5), 2)
            _blob(s, col, x, y, 3)
        return [s]
    if kind == "house":
        s = pygame.Surface((70, 64), pygame.SRCALPHA)
        rrect(s, (0, 0, 0, 60), (8, 9, 58, 52), 4)
        rrect(s, (178, 62, 52), (4, 4, 58, 52), 3)
        rrect(s, (150, 48, 42), (4, 30, 58, 26), 3)
        pygame.draw.line(s, (110, 34, 32), (4, 30), (62, 30), 3)
        for yy in range(8, 56, 7):
            pygame.draw.line(s, (160, 54, 46), (6, yy), (60, yy), 1)
        pygame.draw.rect(s, (70, 60, 66), (44, 8, 8, 10))
        return [s]
    if kind == "cactus":
        s = pygame.Surface((30, 44), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 50), (3, 34, 24, 8))
        g, d = (70, 150, 70), (46, 112, 54)
        rrect(s, g, (11, 4, 9, 36), 4)
        rrect(s, d, (16, 4, 4, 36), 3)
        rrect(s, g, (2, 16, 12, 6), 3)
        rrect(s, g, (2, 8, 6, 14), 3)
        rrect(s, g, (17, 22, 11, 6), 3)
        rrect(s, g, (22, 14, 6, 14), 3)
        return [s]
    if kind == "rock":
        out = []
        for sz in (26, 34):
            s = pygame.Surface((sz + 8, sz + 8), pygame.SRCALPHA)
            c = sz // 2 + 4
            pts = []
            for i in range(9):
                a = i / 9 * math.tau
                rr = sz / 2 * random.uniform(0.75, 1.05)
                pts.append((c + math.cos(a) * rr, c + math.sin(a) * rr))
            pygame.draw.polygon(s, (0, 0, 0, 55), [(x + 3, y + 4) for x, y in pts])
            pygame.draw.polygon(s, (128, 120, 114), pts)
            pygame.draw.polygon(s, (158, 150, 142), [(c + (x - c) * 0.6 - 2, c + (y - c) * 0.6 - 2) for x, y in pts])
            out.append(s)
        return out
    if kind == "palm":
        s = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.circle(s, (0, 0, 0, 45), (35, 36), 20)
        for i in range(8):
            a = i / 8 * math.tau
            ex, ey = 32 + math.cos(a) * 27, 32 + math.sin(a) * 27
            mx, my = 32 + math.cos(a + 0.2) * 14, 32 + math.sin(a + 0.2) * 14
            pygame.draw.line(s, (40, 130, 60), (32, 32), (mx, my), 6)
            pygame.draw.line(s, (70, 165, 80), (mx, my), (ex, ey), 4)
        _blob(s, (120, 80, 40), 32, 32, 5)
        return [s]
    if kind == "building":
        out = []
        for w, h, neon in ((74, 92, (255, 60, 200)), (64, 70, (60, 220, 255)),
                           (80, 80, (255, 220, 70))):
            s = pygame.Surface((w + 12, h + 12), pygame.SRCALPHA)
            glow(s, (w + 12) // 2, (h + 12) // 2, max(w, h) // 2 + 6, neon, 55)
            rrect(s, (24, 26, 52), (6, 6, w, h), 4)
            rrect(s, (34, 38, 74), (10, 10, w - 8, h - 8), 3)
            rrect(s, neon, (6, 6, w, h), 4, 2)
            for i in range(3):
                rrect(s, (52, 58, 104), (16 + i * 18, 18, 12, 14), 2)
            pygame.draw.rect(s, (60, 66, 112), (16, h - 30, 22, 18))
            pygame.draw.circle(s, (255, 60, 60), (w - 6, 16), 3)
            out.append(s)
        return out
    if kind == "lamp":
        s = pygame.Surface((80, 80), pygame.SRCALPHA)
        glow(s, 40, 40, 38, (255, 214, 110), 120)
        _blob(s, (50, 50, 60), 40, 40, 5)
        _blob(s, (255, 250, 200), 40, 40, 3)
        return [s]
    if kind == "sign":
        s = pygame.Surface((56, 40), pygame.SRCALPHA)
        col = random.choice([(255, 70, 160), (60, 230, 255)])
        glow(s, 28, 20, 26, col, 70)
        rrect(s, (20, 20, 40), (8, 8, 40, 24), 3)
        rrect(s, col, (8, 8, 40, 24), 3, 2)
        pygame.draw.line(s, col, (14, 16), (42, 16), 3)
        pygame.draw.line(s, (255, 255, 255), (14, 24), (32, 24), 2)
        return [s]
    if kind == "pine":
        out = []
        for sz in (50, 60):
            s = pygame.Surface((sz + 8, sz + 8), pygame.SRCALPHA)
            c = (sz + 8) // 2
            pygame.draw.circle(s, (0, 0, 0, 40), (c + 4, c + 5), sz // 2 - 3)
            for rad, col in ((sz // 2, (28, 92, 66)), (sz // 2 - 8, (40, 118, 82)),
                             (sz // 2 - 16, (60, 140, 98))):
                pts = []
                for i in range(16):
                    r2 = rad if i % 2 == 0 else rad * 0.5
                    a = i / 16 * math.tau
                    pts.append((c + math.cos(a) * r2, c + math.sin(a) * r2))
                pygame.draw.polygon(s, col, pts)
            for i in range(7):
                a = random.random() * math.tau
                r2 = random.random() * sz * 0.28
                _blob(s, (250, 252, 255), int(c + math.cos(a) * r2), int(c + math.sin(a) * r2), 4)
            _blob(s, (255, 255, 255), c, c, 5)
            out.append(s)
        return out
    if kind == "snowman":
        s = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.circle(s, (120, 130, 160, 80), (23, 25), 15)
        _blob(s, (250, 252, 255), 19, 21, 14)
        _blob(s, (232, 238, 248), 17, 17, 9)
        _blob(s, (30, 30, 40), 14, 15, 1)
        _blob(s, (30, 30, 40), 20, 14, 1)
        pygame.draw.polygon(s, (240, 130, 40), [(15, 18), (24, 20), (15, 22)])
        pygame.draw.rect(s, (40, 40, 60), (11, 6, 12, 4))
        return [s]
    if kind == "cloud":
        s = pygame.Surface((190, 100), pygame.SRCALPHA)
        for x, y, w, h in ((10, 30, 90, 50), (60, 14, 90, 60), (100, 34, 80, 46),
                           (40, 40, 100, 44)):
            pygame.draw.ellipse(s, (10, 30, 20, 38), (x, y, w, h))
        return [s]
    raise KeyError(kind)


def make_pickups():
    out = {}
    coins = []
    for wd in (22, 18, 12, 6, 12, 18):
        s = pygame.Surface((26, 26), pygame.SRCALPHA)
        x0 = 13 - wd // 2
        pygame.draw.ellipse(s, (232, 160, 20), (x0, 2, wd, 22))
        if wd > 8:
            pygame.draw.ellipse(s, (255, 214, 60), (x0 + 2, 4, wd - 4, 18))
            pygame.draw.line(s, (255, 244, 170), (13, 8), (13, 18), 2)
        coins.append(s)
    out["coin"] = coins
    f = pygame.Surface((30, 36), pygame.SRCALPHA)
    rrect(f, (0, 0, 0, 70), (5, 7, 24, 28), 5)
    rrect(f, (212, 40, 40), (3, 6, 24, 28), 5)
    rrect(f, (150, 24, 28), (3, 6, 24, 28), 5, 2)
    rrect(f, (255, 214, 60), (17, 2, 8, 7), 2)
    rrect(f, (120, 20, 24), (6, 2, 8, 6), 2, 2)
    pygame.draw.polygon(f, (255, 255, 255), [(15, 13), (21, 22), (15, 27), (9, 22)])
    out["fuel"] = [f]
    h = pygame.Surface((30, 28), pygame.SRCALPHA)
    pygame.draw.circle(h, (240, 60, 90), (10, 10), 8)
    pygame.draw.circle(h, (240, 60, 90), (20, 10), 8)
    pygame.draw.polygon(h, (240, 60, 90), [(3, 14), (27, 14), (15, 26)])
    pygame.draw.circle(h, (255, 170, 190), (8, 8), 3)
    out["heart"] = [h]
    o = pygame.Surface((70, 48), pygame.SRCALPHA)
    for x, y, w, hh in ((4, 10, 40, 28), (22, 4, 44, 34), (14, 16, 44, 28)):
        pygame.draw.ellipse(o, (10, 10, 14, 215), (x, y, w, hh))
    pygame.draw.ellipse(o, (90, 60, 160, 150), (18, 12, 22, 9), 2)
    pygame.draw.ellipse(o, (40, 170, 160, 150), (34, 22, 20, 8), 2)
    out["oil"] = [o]
    return out


class Art:
    def __init__(self):
        self.cars = {}
        self.player_rot = {}
        self.scen = {}
        self.pick = make_pickups()
        for kind in ("tree", "bush", "flower", "house", "cactus", "rock", "palm",
                     "building", "lamp", "sign", "pine", "snowman", "cloud"):
            self.scen[kind] = make_scenery(kind)
        self.cone = self._make_cone()
        self.dim = pygame.Surface((W, H))
        self.dim.fill((0, 0, 0))
        self.topbar = pygame.Surface((W, 58), pygame.SRCALPHA)
        for y in range(58):
            pygame.draw.line(self.topbar, (0, 0, 0, int(150 * (1 - y / 70))), (0, y), (W, y))

    def car(self, kind, color):
        key = (kind, color)
        c = self.cars.get(key)
        if c is None:
            c = make_car(kind, color)
            self.cars[key] = c
        return c

    def player(self, ci, lean=0.0, spin=0.0):
        base = self.car("player", CAR_COLORS[ci])
        ang = int(round((-lean * 7 + spin) / 3.0)) * 3
        if ang == 0:
            return base
        key = (ci, ang)
        c = self.player_rot.get(key)
        if c is None:
            c = pygame.transform.rotate(base, ang)
            self.player_rot[key] = c
        return c

    def _make_cone(self):
        s = pygame.Surface((190, 300), pygame.SRCALPHA)
        for y in range(300):
            hw = 14 + y * 0.28
            a = int(110 * (1 - y / 300) ** 1.4)
            pygame.draw.line(s, (255, 240, 170, a), (95 - hw, 299 - y), (95 + hw, 299 - y))
        return s


# ----------------------------------------------------------------------------
# best score storage
# ----------------------------------------------------------------------------
def _best_path():
    p = os.environ.get("HC_BEST_FILE")
    if p:
        return p
    if os.environ.get("ANDROID_PRIVATE"):          # app-private folder inside an APK
        return os.path.join(os.environ["ANDROID_PRIVATE"], "highway_classic_best.txt")
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "highway_classic_best.txt")
    except NameError:
        return os.path.join(os.getcwd(), "highway_classic_best.txt")


def load_best():
    try:
        with open(_best_path()) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def save_best(v):
    try:
        with open(_best_path(), "w") as f:
            f.write(str(int(v)))
    except Exception:
        pass


# ----------------------------------------------------------------------------
# touch layout (logical 480x800 coordinates)
# ----------------------------------------------------------------------------
NITRO_C = (W // 2, H - 76)
NITRO_R = 52
PAUSE_C = (W - 36, 30)
BTN_START = pygame.Rect(105, 474, 270, 66)
BTN_SOUND = pygame.Rect(W - 120, 12, 108, 36)
SWATCH = [pygame.Rect(W // 2 - 140 + i * 56 - 20, 744 - 20, 40, 40) for i in range(5)]
BTN_RETRY = pygame.Rect(90, 536, 300, 66)
BTN_MENU = pygame.Rect(90, 616, 300, 56)
BTN_RESUME = pygame.Rect(90, 320, 300, 66)
BTN_SOUND_P = pygame.Rect(90, 402, 300, 56)
BTN_MENU_P = pygame.Rect(90, 476, 300, 56)


def near_circle(x, y, c, r):
    return (x - c[0]) ** 2 + (y - c[1]) ** 2 <= r * r


class GameLogic:
    def __init__(self, sfx):
        self.sfx = sfx
        self.art = Art()
        random.seed()
        self.best = load_best()
        self.ci = 0
        self.state = "title"
        self.t = 0.0
        self.keys = set()
        self.touches = {}
        self.cg1, self.cg2 = THEMES[0]["g1"], THEMES[0]["g2"]
        self.croad = THEMES[0]["road"]
        self.night_a = 0.0
        self.warm_a = 0.0
        self.over_t = 0.0
        self.reset()

    # ------------------------------------------------------------------
    def reset(self):
        self.px = lane_x(1.5)
        self.pvx = 0.0
        self.speed = 0.0
        self.dist = 0.0
        self.scroll = 0.0
        self.score = 0.0
        self.coins = 0
        self.fuel = 100.0
        self.nitro = 25.0
        self.boosting = False
        self.hearts = 3
        self.invuln = 0.0
        self.oil_t = 0.0
        self.oil_dir = 1
        self.spin = 0.0
        self.cars, self.items, self.scenery = [], [], []
        self.parts, self.popups, self.snow, self.clouds = [], [], [], []
        self.next_car, self.next_coin = 260, 700
        self.next_fuel, self.next_oil, self.next_heart = 2800, 2200, 9000
        self.next_cloud = 1.0
        self.combo, self.combo_t = 1, 0.0
        self.stage = 0
        self.banner_t = 3.4
        self.play_t = 0.0
        self.countdown = 3.2
        self.dead_t = 0.0
        self.reason = ""
        self.shake = 0.0
        self.beep_t = 0.0
        self.new_best = False
        self.coasting = False
        self.exh_t = 0.0
        self.last_count = 4
        self.cg1, self.cg2 = THEMES[0]["g1"], THEMES[0]["g2"]
        self.croad = THEMES[0]["road"]
        self.night_a = 0.0
        self.warm_a = 0.0
        for y in range(-80, H + 80, 66):
            self.spawn_scenery(y)

    # ------------------------------------------------------------------
    # input helpers
    # ------------------------------------------------------------------
    def in_nitro(self, x, y):
        return near_circle(x, y, NITRO_C, NITRO_R + 14)

    def in_pause(self, x, y):
        return near_circle(x, y, PAUSE_C, 34)

    def get_steer(self):
        s = 0
        if pygame.K_LEFT in self.keys or pygame.K_a in self.keys:
            s -= 1
        if pygame.K_RIGHT in self.keys or pygame.K_d in self.keys:
            s += 1
        for (x, y) in self.touches.values():
            if self.in_nitro(x, y) or self.in_pause(x, y):
                continue
            s += -1 if x < W / 2 else 1
        return clamp(s, -1, 1)

    def nitro_held(self):
        if pygame.K_SPACE in self.keys:
            return True
        for (x, y) in self.touches.values():
            if self.in_nitro(x, y):
                return True
        return False

    def tap(self, x, y):
        st = self.state
        if st == "title":
            if BTN_START.collidepoint(x, y):
                self.start()
            elif BTN_SOUND.collidepoint(x, y):
                self.toggle_sound()
            else:
                for i, r in enumerate(SWATCH):
                    if r.inflate(16, 16).collidepoint(x, y):
                        self.ci = i
        elif st == "play":
            if self.in_pause(x, y):
                self.pause()
        elif st == "pause":
            if BTN_RESUME.collidepoint(x, y):
                self.state = "play"
            elif BTN_SOUND_P.collidepoint(x, y):
                self.toggle_sound()
            elif BTN_MENU_P.collidepoint(x, y):
                self.to_menu()
        elif st == "over" and self.over_t > 0.7:
            if BTN_RETRY.collidepoint(x, y):
                self.start()
            elif BTN_MENU.collidepoint(x, y):
                self.to_menu()

    def key_down(self, key):
        self.keys.add(key)
        if key in (pygame.K_p,):
            if self.state == "play":
                self.pause()
            elif self.state == "pause":
                self.state = "play"
        elif key == pygame.K_ESCAPE:
            if self.state in ("play", "pause", "over"):
                self.to_menu()
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.state == "title" or (self.state == "over" and self.over_t > 0.7):
                self.start()

    def key_up(self, key):
        self.keys.discard(key)

    def toggle_sound(self):
        self.sfx.on = not self.sfx.on
        if not self.sfx.on:
            self.sfx.engine_stop()

    def start(self):
        self.reset()
        self.state = "play"
        self.touches.clear()

    def pause(self):
        if self.state == "play":
            self.state = "pause"
            self.sfx.engine_stop()

    def to_menu(self):
        self.state = "title"
        self.sfx.engine_stop()
        self.reset()

    # ------------------------------------------------------------------
    # spawning
    # ------------------------------------------------------------------
    def theme(self):
        return THEMES[self.stage % 4]

    def spawn_scenery(self, y):
        th = self.theme()
        kind = random.choice(th["scen"])
        spr = random.choice(self.art.scen[kind])
        sw, sh = spr.get_size()
        left = random.random() < 0.5
        if kind == "lamp":
            cx = ROAD_X - 26 if left else ROAD_X + ROAD_W + 26
            x = cx - sw // 2
        elif left:
            x = random.randint(4, max(4, ROAD_X - 12 - sw))
        else:
            lo = ROAD_X + ROAD_W + 12
            x = random.randint(lo, max(lo, W - 4 - sw))
        self.scenery.append({"x": x, "y": y - sh, "spr": spr, "kind": kind})

    def spawn_car(self):
        busy = set(c["lane"] for c in self.cars if c["y"] < 190)
        free = [i for i in range(LANES) if i not in busy]
        if len(busy) >= 2 or not free:
            self.next_car = 70
            return
        lane = random.choice(free)
        kind = random.choices(["sedan", "taxi", "van", "truck"],
                              weights=[5, 2, 2, 1 + min(3, self.stage)])[0]
        w, h = CAR_DIMS[kind]
        if kind == "taxi":
            col = (250, 205, 40)
        elif kind == "truck":
            col = random.choice([(200, 70, 50), (70, 120, 170), (210, 210, 215), (90, 150, 90)])
        else:
            col = random.choice(TRAFFIC_COLORS)
        spd = {"sedan": (140, 230), "taxi": (170, 250), "van": (120, 200),
               "truck": (95, 140)}[kind]
        self.cars.append({"x": lane_x(lane), "y": -h / 2 - 30, "w": w, "h": h,
                          "speed": random.uniform(*spd), "kind": kind,
                          "spr": self.art.car(kind, col), "lane": lane,
                          "near": False})
        gap = random.uniform(230, 400) * max(0.5, 1 - 0.06 * self.stage - self.dist / 14000)
        self.next_car = gap

    def spawn_coins(self):
        lane = random.randint(0, LANES - 1)
        n = random.randint(3, 6)
        zig = random.random() < 0.4
        for i in range(n):
            ln = lane
            if zig and i % 2:
                ln = lane + 1 if lane < LANES - 1 else lane - 1
            self.items.append({"kind": "coin", "x": lane_x(ln), "y": -30 - i * 50,
                               "hit": False})

    def spawn_item(self, kind):
        lane = random.randint(0, LANES - 1)
        self.items.append({"kind": kind, "x": lane_x(lane), "y": -40, "hit": False})

    # ------------------------------------------------------------------
    # effects
    # ------------------------------------------------------------------
    def popup(self, x, y, msg, col=(255, 255, 255)):
        self.popups.append({"x": x, "y": y, "txt": msg, "col": col, "t": 0.0})

    def burst(self, x, y, cols, n, spd, life=0.7, size=(3, 7)):
        for _ in range(n):
            a = random.random() * math.tau
            v = random.uniform(0.2, 1.0) * spd
            lf = random.uniform(0.4, 1.0) * life
            self.parts.append([x, y, math.cos(a) * v, math.sin(a) * v, lf, lf,
                               random.uniform(*size), random.choice(cols)])
        if len(self.parts) > 320:
            del self.parts[:len(self.parts) - 320]

    def explode(self, x, y):
        self.burst(x, y, [(255, 220, 80), (255, 150, 40), (240, 70, 30)], 30, 280, 0.8, (4, 10))
        self.burst(x, y, [(60, 60, 64), (100, 100, 104)], 16, 140, 1.1, (6, 12))

    def start_death(self, reason, boom):
        if self.dead_t > 0:
            return
        self.reason = reason
        self.dead_t = 1.2 if boom else 0.5
        self.sfx.engine_stop()
        if boom:
            self.explode(self.px, PLAYER_Y)
            self.shake = 0.7

    def finish(self):
        self.state = "over"
        self.over_t = 0.0
        sc = int(self.score)
        if sc > self.best:
            self.best = sc
            self.new_best = True
            save_best(sc)
        self.sfx.play("over")

    def crash(self, c):
        self.hearts -= 1
        self.combo = 1
        self.explode((self.px + c["x"]) / 2, (PLAYER_Y + c["y"]) / 2)
        self.cars.remove(c)
        self.shake = 0.5
        self.speed *= 0.5
        self.invuln = 2.2
        self.pvx += 170 if self.px >= c["x"] else -170
        self.sfx.play("crash")
        if self.hearts <= 0:
            self.start_death("CRASHED!", True)
        else:
            self.popup(self.px, PLAYER_Y - 50, "OUCH!", (255, 90, 70))

    # ------------------------------------------------------------------
    # main update
    # ------------------------------------------------------------------
    def update_theme_blend(self, dt):
        th = self.theme()
        k = min(1.0, dt * 1.3)
        self.cg1 = lerp_col(self.cg1, th["g1"], k)
        self.cg2 = lerp_col(self.cg2, th["g2"], k)
        self.croad = lerp_col(self.croad, th["road"], k)
        self.night_a = lerp(self.night_a, 105 if th["night"] else 0, k)
        self.warm_a = lerp(self.warm_a, 44 if th["warm"] else 0, k)

    def update(self, dt):
        self.t += dt
        self.update_theme_blend(dt)
        if self.state == "title":
            return
        if self.state == "pause":
            return
        if self.state == "over":
            self.over_t += dt
            self.update_particles(dt)
            return
        self.update_play(dt)

    def update_particles(self, dt):
        alive = []
        for p in self.parts:
            p[4] -= dt
            if p[4] > 0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt + self.speed * dt * 0.55
                p[2] *= (1 - 1.6 * dt)
                p[3] *= (1 - 1.6 * dt)
                alive.append(p)
        self.parts = alive
        for q in self.popups:
            q["t"] += dt
            q["y"] -= 46 * dt
        self.popups = [q for q in self.popups if q["t"] < 1.0]

    def update_play(self, dt):
        self.shake = max(0.0, self.shake - dt)
        self.banner_t = max(0.0, self.banner_t - dt)
        if self.countdown > 0:
            self.countdown -= dt
            n = int(math.ceil(self.countdown))
            if n != self.last_count and n <= 3:
                self.last_count = n
                self.sfx.play("tick" if n > 0 else "go")
            if self.countdown <= 0:
                self.sfx.play("go")
            self.update_particles(dt)
            return
        self.play_t += dt
        dying = self.dead_t > 0
        steer = 0 if dying else self.get_steer()
        want_nitro = False if dying else self.nitro_held()

        # --- nitro
        if want_nitro and (self.boosting or self.nitro > 8) and self.nitro > 0 \
                and not self.coasting:
            if not self.boosting:
                self.sfx.play("nitro")
            self.boosting = True
            self.nitro = max(0.0, self.nitro - 30 * dt)
            if self.nitro <= 0:
                self.boosting = False
        else:
            self.boosting = False

        # --- speed
        base = min(620.0, 300 + self.dist / STAGE_METERS * 48)
        target = 0.0 if (self.coasting or dying) else base * (1.45 if self.boosting else 1.0)
        offroad = (self.px - 19 < ROAD_X - 2) or (self.px + 19 > ROAD_X + ROAD_W + 2)
        if offroad and not dying:
            target *= 0.6
        if self.oil_t > 0:
            target *= 0.85
        rate = 260 if target > self.speed else 420
        self.speed += clamp(target - self.speed, -rate * dt, rate * dt)

        # --- steering / oil spin
        if self.oil_t > 0:
            self.oil_t -= dt
            self.spin += 700 * dt * self.oil_dir
            self.pvx = lerp(self.pvx, self.oil_dir * 200, min(1.0, 4 * dt))
            if self.oil_t <= 0:
                self.spin = 0.0
        else:
            tvx = steer * 335 * (0.7 + 0.3 * min(1.0, self.speed / 300))
            dv = 2300 * dt
            self.pvx += clamp(tvx - self.pvx, -dv, dv)
        self.px = clamp(self.px + self.pvx * dt, 24, W - 24)

        # --- world motion
        ds = self.speed * dt
        self.scroll += ds
        meters = ds / 12.0
        self.dist += meters
        if not dying:
            self.score += meters * (2 if self.boosting else 1)

        new_stage = int(self.dist // STAGE_METERS)
        if new_stage != self.stage:
            self.stage = new_stage
            self.banner_t = 3.4
            self.score += 250
            self.sfx.play("stage")
            self.popup(W / 2, 250, "STAGE BONUS +250", (255, 230, 90))

        # --- fuel
        if not dying:
            drain = 2.4 + 0.12 * self.stage + (0.7 if self.boosting else 0)
            self.fuel -= drain * dt
            self.beep_t -= dt
            if self.fuel < 25 and self.beep_t <= 0:
                self.beep_t = 0.9
                self.sfx.play("low")
            if self.fuel <= 0:
                self.fuel = 0
                self.coasting = True
            if self.coasting and self.speed < 45:
                self.start_death("OUT OF FUEL!", False)
        if dying:
            self.dead_t -= dt
            if self.dead_t <= 0:
                self.finish()
                return

        self.invuln = max(0.0, self.invuln - dt)
        self.combo_t -= dt
        if self.combo_t <= 0:
            self.combo = 1
        self.sfx.engine_update(self.speed / 520.0, not dying)

        # --- spawning (distance based so it scales with speed)
        self.next_car -= ds
        self.next_coin -= ds
        self.next_fuel -= ds
        self.next_oil -= ds
        self.next_heart -= ds
        if self.next_car <= 0:
            self.spawn_car()
        if self.next_coin <= 0:
            self.spawn_coins()
            self.next_coin = random.uniform(650, 1100)
        if self.next_fuel <= 0:
            self.spawn_item("fuel")
            self.next_fuel = random.uniform(3400, 4400)
        if self.next_oil <= 0:
            self.spawn_item("oil")
            self.next_oil = random.uniform(1500, 2600) * max(0.55, 1 - 0.07 * self.stage)
        if self.next_heart <= 0:
            if self.hearts < 3:
                self.spawn_item("heart")
            self.next_heart = random.uniform(8000, 11000)
        top = min([s["y"] for s in self.scenery] + [0])
        while top > -90:
            top -= random.randint(54, 100)
            self.spawn_scenery(top + 40)

        # --- move things
        for s in self.scenery:
            s["y"] += ds
        self.scenery = [s for s in self.scenery if s["y"] < H + 20]
        for it in self.items:
            it["y"] += ds
        self.items = [i for i in self.items if i["y"] < H + 50 and not (i["hit"] and i["kind"] != "oil")]
        for c in self.cars:
            c["y"] += (self.speed - c["speed"]) * dt
        self.cars = [c for c in self.cars if -400 < c["y"] < H + 160]

        # --- pickups
        if not dying:
            for it in self.items:
                if it["hit"]:
                    continue
                dx, dy = abs(it["x"] - self.px), abs(it["y"] - PLAYER_Y)
                k = it["kind"]
                if k == "oil":
                    if dx < 30 and dy < 22 and self.oil_t <= 0 and self.invuln <= 0:
                        it["hit"] = True
                        self.oil_t = 0.9
                        self.oil_dir = random.choice([-1, 1])
                        self.sfx.play("oil")
                        self.popup(self.px, PLAYER_Y - 50, "OIL!", (190, 150, 255))
                elif dx < 26 and dy < 40:
                    it["hit"] = True
                    if k == "coin":
                        self.coins += 1
                        self.score += 25
                        self.nitro = min(100, self.nitro + 5)
                        self.sfx.play("coin")
                        self.burst(it["x"], it["y"], [(255, 230, 100), (255, 255, 200)], 6, 120, 0.4, (2, 4))
                    elif k == "fuel":
                        self.fuel = min(100.0, self.fuel + 38)
                        self.coasting = False if self.fuel > 0 else self.coasting
                        self.sfx.play("fuel")
                        self.popup(it["x"], it["y"], "+FUEL", (255, 120, 100))
                    elif k == "heart":
                        if self.hearts < 3:
                            self.hearts += 1
                        else:
                            self.score += 100
                        self.sfx.play("heart")
                        self.popup(it["x"], it["y"], "+1 LIFE", (255, 120, 160))

        # --- traffic collisions & close calls
        if not dying:
            pr = pygame.Rect(int(self.px - 13), PLAYER_Y - 30, 26, 60)
            for c in list(self.cars):
                cr = pygame.Rect(int(c["x"] - c["w"] / 2 + 3), int(c["y"] - c["h"] / 2 + 3),
                                 c["w"] - 6, c["h"] - 6)
                if cr.colliderect(pr):
                    if self.invuln <= 0:
                        self.crash(c)
                        if self.dead_t > 0:
                            break
                    continue
                if not c["near"] and self.invuln <= 0 and abs(c["y"] - PLAYER_Y) < 24:
                    gap = abs(c["x"] - self.px) - (c["w"] / 2 + 13)
                    if 0 <= gap < 15:
                        c["near"] = True
                        self.combo = min(5, self.combo + 1) if self.combo_t > 0 else 2
                        self.combo_t = 4.0
                        self.score += 50 * self.combo
                        self.nitro = min(100, self.nitro + 12)
                        self.sfx.play("near")
                        self.popup(self.px, PLAYER_Y - 60, "CLOSE CALL! x%d" % self.combo, (110, 230, 255))

        # --- particles: exhaust, flames, dust
        self.exh_t -= dt
        if self.exh_t <= 0 and self.speed > 30 and self.state == "play":
            self.exh_t = 0.045
            rx = self.px + random.uniform(-9, 9)
            if self.boosting:
                for sx in (-9, 9):
                    lf = random.uniform(0.12, 0.26)
                    self.parts.append([self.px + sx, PLAYER_Y + 38, random.uniform(-14, 14),
                                       random.uniform(90, 170), lf, lf, random.uniform(5, 8),
                                       random.choice([(255, 210, 60), (255, 120, 30), (120, 190, 255)])])
            else:
                self.parts.append([rx, PLAYER_Y + 36, random.uniform(-10, 10), random.uniform(20, 50),
                                   0.4, 0.4, random.uniform(3, 5), (190, 190, 196)])
            if offroad:
                for sx in (-12, 12):
                    self.parts.append([self.px + sx, PLAYER_Y + 24, random.uniform(-40, 40),
                                       random.uniform(20, 80), 0.5, 0.5, random.uniform(3, 6),
                                       shade(self.cg1, 0.85)])
        self.update_particles(dt)

        # --- weather & clouds
        th = self.theme()
        if th["snow"] and len(self.snow) < 130 and random.random() < 0.8:
            self.snow.append([random.uniform(-20, W), -6, random.uniform(-14, 14),
                              random.uniform(70, 150), random.choice((1, 2, 2, 3))])
        for f in self.snow:
            f[0] += (f[2] + 20 * math.sin(self.t * 2 + f[1] * 0.02)) * dt
            f[1] += (f[3] + self.speed * 0.25) * dt
        self.snow = [f for f in self.snow if f[1] < H + 6]
        self.next_cloud -= dt
        if self.next_cloud <= 0 and self.stage % 4 == 0:
            self.clouds.append({"x": random.uniform(-80, W - 100), "y": -110,
                                "spr": self.art.scen["cloud"][0]})
            self.next_cloud = random.uniform(3.0, 6.0)
        for cl in self.clouds:
            cl["y"] += (self.speed * 0.5 + 18) * dt
        self.clouds = [c for c in self.clouds if c["y"] < H + 20]


# ----------------------------------------------------------------------------
# rendering
# ----------------------------------------------------------------------------
class Renderer:
    def __init__(self, g):
        self.g = g
        self.night = pygame.Surface((W, H), pygame.SRCALPHA)

    # ------------------------------------------------------------------
    def draw(self, s):
        g = self.g
        ox = oy = 0
        if g.shake > 0:
            m = g.shake * 14
            ox, oy = random.uniform(-m, m), random.uniform(-m, m)
        world = s
        if ox or oy:
            world = pygame.Surface((W, H))
        self.draw_world(world)
        if world is not s:
            s.fill((0, 0, 0))
            s.blit(world, (int(ox), int(oy)))
        if g.state == "play" and g.banner_t > 0 and g.countdown <= 0:
            self.draw_banner(s)                  # under the HUD so gauges stay clear
        if g.state in ("play", "pause", "over"):
            self.draw_hud(s)
        if g.state == "title":
            self.draw_title(s)
        elif g.state == "pause":
            self.draw_pause(s)
        elif g.state == "over":
            self.draw_over(s)
        elif g.state == "play":
            self.draw_overlays(s)

    # ------------------------------------------------------------------
    def draw_world(self, s):
        g = self.g
        th = g.theme()
        # grass stripes scrolling with the road
        stripe = 80
        off = g.scroll % (stripe * 2)
        s.fill(g.cg1)
        y = -stripe * 2 + off
        while y < H:
            pygame.draw.rect(s, g.cg2, (0, int(y), W, stripe))
            y += stripe * 2
        # desert dunes / snow drifts / city ground tint
        # scenery behind the road (left and right edges)
        for it in g.scenery:
            s.blit(it["spr"], (it["x"], int(it["y"])))
        # road
        rx = ROAD_X
        pygame.draw.rect(s, shade(g.croad, 0.55), (rx - 12, 0, ROAD_W + 24, H))
        pygame.draw.rect(s, g.croad, (rx, 0, ROAD_W, H))
        # subtle asphalt banding
        band = 120
        boff = g.scroll % (band * 2)
        y = -band * 2 + boff
        light = shade(g.croad, 1.07)
        while y < H:
            pygame.draw.rect(s, light, (rx, int(y), ROAD_W, band))
            y += band * 2
        # rumble strips (red/white) along both edges
        seg = 24
        roff = g.scroll % (seg * 2)
        y = -seg * 2 + roff
        while y < H:
            for k in (0, 1):
                col = (225, 225, 225) if k == 0 else (200, 40, 40)
                yy = int(y + k * seg)
                pygame.draw.rect(s, col, (rx - 8, yy, 8, seg))
                pygame.draw.rect(s, col, (rx + ROAD_W, yy, 8, seg))
            y += seg * 2
        pygame.draw.line(s, (240, 240, 240), (rx + 3, 0), (rx + 3, H), 2)
        pygame.draw.line(s, (240, 240, 240), (rx + ROAD_W - 4, 0), (rx + ROAD_W - 4, H), 2)
        # lane dashes
        dash, gap = 34, 34
        doff = g.scroll % (dash + gap)
        for i in range(1, LANES):
            x = int(ROAD_X + LANE_W * i)
            y = -dash - gap + doff
            while y < H:
                pygame.draw.rect(s, (236, 232, 200), (x - 2, int(y), 4, dash))
                y += dash + gap
        # oil slicks and pickups
        for it in g.items:
            k = it["kind"]
            if k == "coin":
                fr = g.art.pick["coin"][int(g.t * 10) % 6]
                s.blit(fr, (int(it["x"] - 13), int(it["y"] - 13)))
            elif k == "oil":
                spr = g.art.pick["oil"][0]
                s.blit(spr, (int(it["x"] - 35), int(it["y"] - 24)))
            else:
                bob = math.sin(g.t * 5 + it["x"]) * 3
                glow(s, it["x"], it["y"] + bob, 30, (255, 240, 140) if k == "fuel" else (255, 130, 170), 90)
                spr = g.art.pick[k][0]
                r = spr.get_rect(center=(int(it["x"]), int(it["y"] + bob)))
                s.blit(spr, r)
        # traffic (shadow is baked into sprite)
        for c in g.cars:
            r = c["spr"].get_rect(center=(int(c["x"]), int(c["y"])))
            s.blit(c["spr"], r)
            if th["night"]:                                  # tail-light glow
                glow(s, c["x"] - c["w"] / 2 + 8, c["y"] + c["h"] / 2, 14, (255, 40, 40), 90)
                glow(s, c["x"] + c["w"] / 2 - 8, c["y"] + c["h"] / 2, 14, (255, 40, 40), 90)
        # player
        if g.state != "title" and not (g.state == "play" and g.dead_t > 0 and g.hearts <= 0
                                       and g.dead_t < 1.0):
            self.draw_player(s)
        # particles
        for p in g.parts:
            f = clamp(p[4] / p[5], 0, 1)
            r = max(1, int(p[6] * (0.5 + 0.5 * f)))
            if p[7][0] > 230 or p[7][2] > 200:
                glow(s, p[0], p[1], r * 2, p[7], int(180 * f))
            else:
                pygame.draw.circle(s, p[7], (int(p[0]), int(p[1])), r)
        # clouds drift above everything
        for cl in g.clouds:
            s.blit(cl["spr"], (int(cl["x"]), int(cl["y"])))
        self.draw_darkness(s)
        # warm sunset tint
        if g.warm_a > 2:
            self.night.fill((255, 120, 40, int(g.warm_a)))
            s.blit(self.night, (0, 0))
        # snow
        for f in g.snow:
            pygame.draw.circle(s, (255, 255, 255), (int(f[0]), int(f[1])), f[4] if len(f) > 4 else 2)
        # speed lines when boosting
        if g.boosting:
            for i in range(14):
                x = (i * 97 + int(g.t * 900)) % W
                y = (i * 211 + int(g.t * 1900)) % H
                pygame.draw.line(s, (255, 255, 255), (x, y), (x, y + 60 + (i % 4) * 14), 1)

    def draw_player(self, s):
        g = self.g
        lean = clamp(g.pvx / 335.0, -1, 1)
        if g.invuln > 0 and int(g.t * 14) % 2 == 0 and g.dead_t <= 0:
            return
        spr = g.art.player(g.ci, lean, g.spin)
        s.blit(spr, spr.get_rect(center=(int(g.px), PLAYER_Y)))

    def draw_darkness(self, s):
        g = self.g
        a = int(g.night_a)
        if a < 3:
            return
        n = self.night
        n.fill((6, 4, 26, a))
        s.blit(n, (0, 0))
        # lights that cut through the dark
        for it in g.scenery:
            if it["kind"] == "lamp":
                glow(s, it["x"] + 40, it["y"] + 40, 46, (255, 210, 110), 110)
            elif it["kind"] in ("building", "sign"):
                glow(s, it["x"] + it["spr"].get_width() / 2, it["y"] + it["spr"].get_height() / 2,
                     40, (200, 90, 255), 50)
        if g.state != "title":
            cone = g.art.cone
            s.blit(cone, (int(g.px - cone.get_width() / 2), PLAYER_Y - 20 - cone.get_height()),
                   special_flags=0)
            for dx in (-10, 10):
                glow(s, g.px + dx, PLAYER_Y - 30, 20, (255, 250, 200), 140)

    # ------------------------------------------------------------------
    def draw_hud(self, s):
        g = self.g
        s.blit(g.art.topbar, (0, 0))
        text(s, "%06d" % int(g.score), 44, (255, 255, 255), (14, 14), "topleft")
        text(s, "BEST %d" % max(g.best, int(g.score)), 22, (255, 220, 120), (14, 46), "topleft")
        # hearts
        for i in range(3):
            col = (240, 60, 90) if i < g.hearts else (70, 60, 80)
            x = W // 2 - 38 + i * 38
            pygame.draw.circle(s, col, (x - 6, 24), 8)
            pygame.draw.circle(s, col, (x + 6, 24), 8)
            pygame.draw.polygon(s, col, [(x - 14, 28), (x + 14, 28), (x, 44)])
        # coins
        s.blit(g.art.pick["coin"][0], (W // 2 - 36, 52))
        text(s, "x%d" % g.coins, 26, (255, 230, 120), (W // 2 - 8, 66), "midleft")
        # pause button
        pygame.draw.circle(s, (20, 20, 30), PAUSE_C, 24)
        pygame.draw.circle(s, (230, 230, 240), PAUSE_C, 24, 2)
        for dx in (-6, 3):
            pygame.draw.rect(s, (240, 240, 250), (PAUSE_C[0] + dx, PAUSE_C[1] - 9, 5, 18))
        # fuel gauge (left, vertical) and stage/speed (right)
        gx, gy, gh = 16, 130, 280
        rrect(s, (16, 16, 26), (gx - 4, gy - 22, 34, gh + 52), 10)
        text(s, "FUEL", 18, (255, 150, 130), (gx + 13, gy - 10))
        rrect(s, (50, 50, 62), (gx + 2, gy + 6, 22, gh), 7)
        frac = clamp(g.fuel / 100.0, 0, 1)
        fcol = (80, 210, 90) if frac > 0.5 else ((250, 200, 50) if frac > 0.25 else (240, 60, 50))
        if frac < 0.25 and int(g.t * 4) % 2 == 0:
            fcol = (255, 255, 255)
        hh = int((gh - 4) * frac)
        if hh > 0:
            rrect(s, fcol, (gx + 4, gy + 6 + gh - 2 - hh, 18, hh), 5)
        # speedometer
        kmh = int(g.speed / 3.0 * 1.0)
        rrect(s, (16, 16, 26), (W - 98, 130, 84, 74), 10)
        text(s, str(kmh), 40, (255, 255, 255), (W - 56, 160))
        text(s, "KM/H", 18, (160, 170, 200), (W - 56, 188))
        # stage chip
        rrect(s, (16, 16, 26), (W - 98, 212, 84, 44), 10)
        text(s, "STAGE", 16, (160, 170, 200), (W - 56, 224))
        text(s, str(g.stage + 1), 28, (255, 220, 120), (W - 56, 244))
        # touch zones hint arrows (fade after a few seconds)
        if g.play_t < 6 and g.state == "play" and g.countdown <= 0:
            a = int(160 * (1 - g.play_t / 6))
            for sign in (-1, 1):
                ar = pygame.Surface((70, 70), pygame.SRCALPHA)
                pts = [(48, 14), (18, 35), (48, 56)] if sign < 0 else [(22, 14), (52, 35), (22, 56)]
                pygame.draw.polygon(ar, (255, 255, 255, a), pts)
                s.blit(ar, (60 if sign < 0 else W - 130, 450))
        # nitro button
        cx, cy = NITRO_C
        held = g.boosting
        glow(s, cx, cy, 70, (255, 160, 40) if held else (80, 150, 255), 90 if held else 40)
        pygame.draw.circle(s, (22, 22, 34), NITRO_C, NITRO_R)
        ring_progress(s, cx, cy, NITRO_R, 9, g.nitro / 100.0,
                      (255, 150, 40) if held else (70, 160, 255))
        pygame.draw.circle(s, (255, 190, 50) if held else (40, 46, 70), NITRO_C, NITRO_R - 14)
        bolt = [(cx + 6, cy - 22), (cx - 10, cy + 3), (cx, cy + 3), (cx - 6, cy + 22),
                (cx + 12, cy - 5), (cx + 2, cy - 5)]
        pygame.draw.polygon(s, (255, 255, 255), bolt)
        if g.nitro >= 100 and int(g.t * 3) % 2 == 0:
            text(s, "READY", 18, (255, 255, 255), (cx, cy - NITRO_R - 12))

    def draw_overlays(self, s):
        g = self.g
        if g.countdown > 0:
            n = int(math.ceil(g.countdown))
            frac = g.countdown - math.floor(g.countdown)
            lab = str(n) if n > 0 else "GO!"
            if g.countdown <= 0.2:
                lab = "GO!"
            sz = int(150 + 80 * frac)
            text(s, lab, sz, (255, 240, 120), (W // 2, 330), shadow=(120, 20, 20), sh=5)
        for q in g.popups:
            a = 1 - q["t"]
            text(s, q["txt"], 28, q["col"], (q["x"], q["y"]))
        if g.coasting and g.state == "play":
            text(s, "OUT OF FUEL!", 44, (255, 80, 70), (W // 2, 200), sh=3)
            text(s, "coasting to a stop...", 22, (255, 255, 255), (W // 2, 236))

    def draw_banner(self, s):
        g = self.g
        t = g.banner_t
        a = clamp(min(t, 3.4 - t) * 3, 0, 1)
        y = 170
        bar = pygame.Surface((W, 82), pygame.SRCALPHA)
        bar.fill((0, 0, 0, int(160 * a)))
        s.blit(bar, (0, y))
        text(s, "STAGE %d" % (g.stage + 1), 24, (255, 220, 120), (W // 2, y + 20), shadow=None)
        f = font(40).render(g.theme()["name"], True, (255, 255, 255))
        f.set_alpha(int(255 * a))
        s.blit(f, f.get_rect(center=(W // 2, y + 52)))

    def button(self, s, rect, label, col, sz=36):
        r = pygame.Rect(rect)
        rrect(s, shade(col, 0.55), (r.x, r.y + 5, r.w, r.h), 16)
        rrect(s, col, r, 16)
        rrect(s, shade(col, 1.3), r, 16, 2)
        text(s, label, sz, (255, 255, 255), r.center, sh=2)

    # ------------------------------------------------------------------
    def draw_title(self, s):
        g = self.g
        d = pygame.Surface((W, H), pygame.SRCALPHA)
        d.fill((8, 8, 20, 150))
        s.blit(d, (0, 0))
        # logo
        bob = math.sin(g.t * 2) * 4
        text(s, "HIGHWAY", 104, (255, 214, 70), (W // 2, 150 + bob), shadow=(150, 40, 30), sh=6)
        text(s, "CLASSIC", 104, (255, 255, 255), (W // 2, 232 + bob), shadow=(40, 90, 200), sh=6)
        pygame.draw.rect(s, (230, 60, 60), (70, 292, 340, 6))
        pygame.draw.rect(s, (255, 255, 255), (70, 302, 340, 3))
        text(s, "RETRO ARCADE RACER", 26, (200, 210, 240), (W // 2, 330))
        # showcase car
        car = g.art.car("player", CAR_COLORS[g.ci])
        big = pygame.transform.rotozoom(car, math.sin(g.t * 1.3) * 6, 1.55)
        glow(s, W // 2, 404, 80, CAR_COLORS[g.ci], 60)
        s.blit(big, big.get_rect(center=(W // 2, 404)))
        self.button(s, BTN_START, "TAP TO START", (46, 170, 80), 40)
        text(s, "Hold LEFT / RIGHT side of the screen to steer", 22, (255, 255, 255), (W // 2, 560))
        text(s, "Hold the bolt button for NITRO", 22, (255, 255, 255), (W // 2, 588))
        text(s, "Grab coins + fuel, dodge traffic and oil!", 22, (255, 220, 120), (W // 2, 616))
        text(s, "BEST: %d" % g.best, 34, (255, 220, 120), (W // 2, 668))
        text(s, "CHOOSE YOUR CAR", 20, (200, 210, 240), (W // 2, 708))
        for i, r in enumerate(SWATCH):
            pygame.draw.circle(s, CAR_COLORS[i], r.center, 17)
            pygame.draw.circle(s, (255, 255, 255) if i == g.ci else (30, 30, 40), r.center, 19, 3)
        b = BTN_SOUND
        rrect(s, (24, 24, 40), b, 10)
        text(s, "SOUND " + ("ON" if g.sfx.on and g.sfx.ok else "OFF"), 22, (255, 255, 255), b.center, shadow=None)

    def draw_pause(self, s):
        g = self.g
        d = pygame.Surface((W, H), pygame.SRCALPHA)
        d.fill((0, 0, 0, 170))
        s.blit(d, (0, 0))
        text(s, "PAUSED", 90, (255, 255, 255), (W // 2, 230), sh=5)
        self.button(s, BTN_RESUME, "RESUME", (46, 170, 80))
        self.button(s, BTN_SOUND_P, "SOUND " + ("ON" if g.sfx.on and g.sfx.ok else "OFF"), (70, 90, 150), 30)
        self.button(s, BTN_MENU_P, "MAIN MENU", (150, 70, 70), 30)

    def draw_over(self, s):
        g = self.g
        a = int(clamp(g.over_t * 400, 0, 185))
        d = pygame.Surface((W, H), pygame.SRCALPHA)
        d.fill((10, 0, 0, a))
        s.blit(d, (0, 0))
        k = clamp(g.over_t * 3, 0, 1)
        text(s, "GAME OVER", int(60 + 30 * k), (255, 80, 70), (W // 2, 170), sh=5)
        text(s, g.reason, 30, (255, 220, 200), (W // 2, 225))
        rrect(s, (16, 16, 30), (60, 262, 360, 240), 18)
        rrect(s, (90, 96, 140), (60, 262, 360, 240), 18, 2)
        rows = [("SCORE", "%d" % int(g.score), (255, 255, 255)),
                ("DISTANCE", "%d m" % int(g.dist), (180, 220, 255)),
                ("COINS", "%d" % g.coins, (255, 220, 100)),
                ("STAGE", "%d" % (g.stage + 1), (150, 255, 170))]
        for i, (a1, b1, c1) in enumerate(rows):
            y = 296 + i * 44
            text(s, a1, 26, (170, 180, 210), (90, y), "midleft", shadow=None)
            text(s, b1, 34, c1, (390, y), "midright")
        if g.new_best:
            if int(g.t * 4) % 2 == 0:
                text(s, "NEW BEST SCORE!", 38, (255, 230, 70), (W // 2, 482), sh=3)
        else:
            text(s, "BEST: %d" % g.best, 28, (255, 220, 120), (W // 2, 482))
        self.button(s, BTN_RETRY, "RACE AGAIN", (46, 170, 80), 38)
        self.button(s, BTN_MENU, "MAIN MENU", (70, 90, 150), 30)


# ----------------------------------------------------------------------------
# main loop with touch / mouse / keyboard input
# ----------------------------------------------------------------------------
class App:
    def __init__(self):
        pygame.init()
        flags = 0
        info = pygame.display.Info()
        if sys.platform.startswith("linux") and "ANDROID_ARGUMENT" not in os.environ \
                and not os.environ.get("ANDROID_ROOT"):
            self.win = pygame.display.set_mode((W, H))      # desktop test window
        else:
            try:
                self.win = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            except Exception:
                self.win = pygame.display.set_mode((info.current_w or W, info.current_h or H))
        pygame.display.set_caption("Highway Classic")
        self.screen = pygame.Surface((W, H))
        self.sfx = Sfx()
        self.game = GameLogic(self.sfx)
        self.rend = Renderer(self.game)
        self.clock = pygame.time.Clock()
        self.update_scale()
        self.fing = {}

    def update_scale(self):
        ww, wh = self.win.get_size()
        self.scale = min(ww / W, wh / H)
        self.ox = (ww - W * self.scale) / 2
        self.oy = (wh - H * self.scale) / 2

    def to_logical(self, px, py):
        return (px - self.ox) / self.scale, (py - self.oy) / self.scale

    def handle(self, e):
        g = self.game
        t = e.type
        FD = getattr(pygame, "FINGERDOWN", None)
        FM = getattr(pygame, "FINGERMOTION", None)
        FU = getattr(pygame, "FINGERUP", None)
        ww, wh = self.win.get_size()
        if t == pygame.QUIT:
            return False
        if t == pygame.KEYDOWN:
            g.key_down(e.key)
        elif t == pygame.KEYUP:
            g.key_up(e.key)
        elif FD is not None and t == FD:
            x, y = self.to_logical(e.x * ww, e.y * wh)
            g.touches[e.finger_id] = (x, y)
            g.tap(x, y)
        elif FM is not None and t == FM:
            x, y = self.to_logical(e.x * ww, e.y * wh)
            if e.finger_id in g.touches:
                g.touches[e.finger_id] = (x, y)
        elif FU is not None and t == FU:
            g.touches.pop(e.finger_id, None)
        elif t == pygame.MOUSEBUTTONDOWN and not getattr(e, "touch", False):
            x, y = self.to_logical(*e.pos)
            g.touches["m"] = (x, y)
            g.tap(x, y)
        elif t == pygame.MOUSEMOTION and "m" in g.touches and not getattr(e, "touch", False):
            g.touches["m"] = self.to_logical(*e.pos)
        elif t == pygame.MOUSEBUTTONUP and not getattr(e, "touch", False):
            g.touches.pop("m", None)
        elif t in (getattr(pygame, "WINDOWFOCUSLOST", -1), getattr(pygame, "APP_WILLENTERBACKGROUND", -1)):
            g.touches.clear()
            g.pause()
        elif t in (getattr(pygame, "VIDEORESIZE", -1), getattr(pygame, "WINDOWSIZECHANGED", -1)):
            self.update_scale()
        return True

    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 20.0)
            for e in pygame.event.get():
                if not self.handle(e):
                    running = False
            self.game.update(dt)
            self.rend.draw(self.screen)
            self.win.fill((0, 0, 0))
            if abs(self.scale - 1) < 0.001:
                self.win.blit(self.screen, (int(self.ox), int(self.oy)))
            else:
                size = (int(W * self.scale), int(H * self.scale))
                # plain scale is much faster than smoothscale on phones
                if SMOOTH_SCALE:
                    try:
                        sc = pygame.transform.smoothscale(self.screen, size)
                    except ValueError:
                        sc = pygame.transform.scale(self.screen, size)
                else:
                    sc = pygame.transform.scale(self.screen, size)
                self.win.blit(sc, (int(self.ox), int(self.oy)))
            pygame.display.flip()
        self.sfx.engine_stop()
        pygame.quit()


def main():
    App().run()


if __name__ == "__main__":
    main()
