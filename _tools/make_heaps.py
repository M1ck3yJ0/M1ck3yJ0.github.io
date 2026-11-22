"""Build panel 18's two heaps of food as mosaic, for the balance in IKEA's kitchens.

Usage:
    python3 -I _tools/make_heaps.py [--check] [--preview <file.svg>]

The 2017 pan holds a salmon fillet, half an avocado, two eggs and a head of broccoli. The
2022 pan holds the same food cut down: the salmon and broccoli each cut straight through and
the avocado half quartered, each keeping the same share of its area, and one egg taken away. That share is
solved so the 2022 heap's visible area is exactly what's left of 2017's by the data file's
"examples" -> "ikea" -> "food_waste_cut".

Each food is terrazzo, as the ring's center is: shards random in shape, size and placement,
each in one of the food's shades, from its lit side to its dark side, with fine lines of
background between them. Each part of a food (a floret, the skin, a fat line) is tiled on
its own: Voronoi cells of seeds spaced by sizes drawn across a 16-fold range of area, about
half of them cracked along random lines. Foods in front hide the parts of foods behind
them, so only visible parts get shards. A heap's area is the area its foods cover, lines
included; the check also reports the shards' area alone.

Everything is built at one size, then drawn GROW times as large, pans included, so the
heaps fill the frame and keep their ratio and their look.

Writes the heaps into the data file under "food_heaps": the pan's size, the share kept,
and for each heap one path per tone, in the pan's coordinates (x right, y down, the
middle of the pan's top at 0, 0), rounded to 0.1. With --check, writes nothing and
re-measures the heaps already in the data file. With --preview, also saves both heaps
side by side as an SVG.
"""
import json
import os
import re
import sys

import numpy as np
import shapely
import shapely.ops
from scipy.optimize import brentq
from shapely import affinity
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "projects", "far_from_full_circle", "far_from_full_circle_data.js")
PAGE = os.path.join(ROOT, "projects", "far_from_full_circle", "a_circularity_story.html")
PREFIX = "window.FAR_FROM_FULL_CIRCLE_DATA = "

PAN = {"rx": 72.0, "ry": 6.5}        # the pan's top, an ellipse; food sits inside it
SIZES = (1.2, 4.8)                   # half-sizes of shards, smallest to largest
LINE = 0.4                           # the fine line between shards
LIGHT = np.array([-0.55, -0.83])     # from the upper left
GROW = 1.28                          # both heaps and their pans, drawn this many times the size built
SEED = 20171122

# Tones, light to dark. Names match the page's CSS variables.
RAMPS = {
    "salmon": 6, "fat": 3, "salmon-side": 3,
    "floret": 6, "stalk": 3,
    "flesh": 5, "skin": 2, "pit": 4,
    "egg": 5,
}


def spline(pts, n=10):
    """A closed Catmull-Rom curve through pts, as a polygon."""
    P = np.asarray(pts, float)
    m = len(P)
    out = []
    for i in range(m):
        p0, p1, p2, p3 = P[(i - 1) % m], P[i], P[(i + 1) % m], P[(i + 2) % m]
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3))
    return Polygon(out).buffer(0)


def clean(g):
    """g as a valid polygon or multipolygon on a 0.001 grid, dropping stray lines and points."""
    g = shapely.set_precision(shapely.make_valid(g), 1e-3)
    polys = [x for x in getattr(g, "geoms", [g]) if x.geom_type in ("Polygon", "MultiPolygon")]
    return unary_union(polys).buffer(0) if polys else Polygon()


def circle(x, y, r):
    return Point(x, y).buffer(r, quad_segs=16)


def shade(rng, v, spread=0.2):
    """A value from 0 (lit) to 1 (dark), with the jitter that keeps tiles apart."""
    return float(np.clip(v + rng.normal(0, spread), 0, 0.999))


def dome(c, r, p):
    """How dark a point is on a dome of radius r at c, lit from LIGHT."""
    d = (np.asarray(p) - np.asarray(c)) / r
    return 0.5 - 0.5 * float(d @ LIGHT) + 0.18 * float(np.hypot(*d))


# ---------- The foods: each a list of zones (shape, ramp, how a tile there is shaded) ----------

def salmon(L=120.0):
    def back(x):
        u = x / L
        return -(12 + 5 * np.sin(np.pi * u / 1.4)) * max(0.0, 1 - u ** 3) ** 0.7

    def front(x):
        return 1.5 * np.sin(np.pi * x / L)

    def thick(x):
        return 7.5 * max(0.0, 1 - (x / L) ** 2) ** 0.8

    xs = np.linspace(0, L, 60)
    top = Polygon([(x, back(x)) for x in xs] + [(x, front(x)) for x in xs[::-1]]).buffer(0)
    side = Polygon([(x, front(x)) for x in xs] + [(x, front(x) + thick(x)) for x in xs[::-1]]).buffer(0)
    stripes = []
    for x0 in np.arange(8, L - 10, 9.5):
        a = (x0, back(x0) - 2)
        b = (x0 + 11, front(x0 + 11) + 1)
        mid = ((a[0] + b[0]) / 2 - 3.5, (a[1] + b[1]) / 2 + 0.5)
        stripes.append(LineString([a, mid, b]).buffer(0.85, quad_segs=4))
    fat = unary_union(stripes).intersection(top)
    flesh = top.difference(fat)
    span = L

    def lit(p, rng, ramp):
        x, y = p
        v = 0.12 + 0.5 * (x / span) + 0.3 * (y + 14) / 15
        if ramp == "salmon-side":
            v = 0.2 + 0.6 * (x / span)
        return shade(rng, v, 0.17)

    return [(flesh, "salmon", lit), (fat, "fat", lit), (side, "salmon-side", lit)], [top.boundary]


def broccoli(s=0.95):
    florets = [  # top rows first: lower florets sit in front
        (2, -58, 11), (-27, -42, 12), (-8, -47, 13), (12, -46, 12), (28, -39, 10),
        (-38, -24, 11), (-20, -26, 13), (0, -28, 14), (20, -26, 13), (36, -24, 10),
        (-30, -8, 12), (-10, -5, 13), (11, -6, 12), (29, -10, 11),
    ]
    zones, outlines = [], []
    stalk = spline([(-13, -6), (13, -6), (10, 10), (13, 22), (8, 27), (-8, 27), (-13, 22), (-10, 10)])
    stalk = affinity.scale(stalk, s, s, origin=(0, 0))
    shapes = []
    for k, (cx, cy, r) in enumerate(florets):
        parts = [circle(cx, cy, 0.86 * r)]
        for a in np.linspace(np.radians(150), np.radians(390), 8):
            parts.append(circle(cx + 0.62 * r * np.cos(a), cy + 0.62 * r * np.sin(a), 0.38 * r))
        shapes.append((affinity.scale(unary_union(parts), s, s, origin=(0, 0)), (cx * s, cy * s), r * s, k))
    covered = Polygon()
    for shape, c, r, k in reversed(shapes):     # front florets claim their area first
        part = shape.difference(covered)
        covered = covered.union(shape)
        row = 0.0 if c[1] < -40 * s else 0.12 if c[1] < -20 * s else 0.24

        def lit(p, rng, ramp, c=c, r=r, row=row):
            return shade(rng, 0.55 * dome(c, r, p) + row + 0.05, 0.13)

        zones.append((part, "floret", lit))
        outlines.append(shape.boundary)
    zones.insert(0, (stalk.difference(covered), "stalk",
                     lambda p, rng, ramp: shade(rng, 0.25 + 0.5 * (p[0] + 12 * s) / (24 * s), 0.12)))
    return zones, outlines


def avocado():
    out = unary_union([circle(0, 3, 23), circle(0, -22, 15)]).convex_hull
    out = out.buffer(2, quad_segs=8).buffer(-2, quad_segs=8)
    out = affinity.scale(out, 1.12, 1.12, origin=(0, 2))
    pit = circle(0, 2, 14)
    inner = out.buffer(-3)
    skin = out.difference(inner)
    flesh = inner.difference(pit)

    def lit_flesh(p, rng, ramp):
        q = Point(p)
        a, b = q.distance(pit.boundary), q.distance(inner.boundary)
        return shade(rng, 0.85 * a / (a + b + 1e-9) + 0.12 * (0.5 - 0.5 * float(np.asarray(p) / 30 @ LIGHT)), 0.1)

    zones = [
        (skin, "skin", lambda p, rng, ramp: shade(rng, 0.5 - 0.4 * float(np.asarray(p) / 30 @ LIGHT), 0.15)),
        (flesh, "flesh", lit_flesh),
        (pit, "pit", lambda p, rng, ramp: shade(rng, dome((0, 2), 14, p), 0.12)),
    ]
    return zones, [out.boundary, pit.boundary]


def quarter():
    """A quarter of an avocado: the half cut down its length, lying on its skin with the cut
    edge up and the neck to the right, the pit kept in its hollow, as it stays in one quarter."""
    zones, _ = avocado()
    half = box(0, -999, 999, 999)                  # the half's right side, before turning

    def turn(g):
        return clean(affinity.rotate(g, 90, origin=(0, 0)))   # left edge up, neck to the right

    skin = turn(zones[0][0].intersection(half))
    flesh = turn(zones[1][0].intersection(half))
    pit = turn(zones[2][0])
    pc = np.array(pit.centroid.coords[0])

    def lit_flesh(p, rng, ramp):                   # pale by the pit, greener toward the skin
        q = Point(p)
        a, b = q.distance(pit.boundary), q.distance(skin)
        return shade(rng, 0.85 * a / (a + b + 1e-9) + 0.12 * (0.5 - 0.5 * float(np.asarray(p) / 30 @ LIGHT)), 0.1)

    out = [
        (skin, "skin", lambda p, rng, ramp: shade(rng, 0.5 - 0.4 * float(np.asarray(p) / 30 @ LIGHT), 0.15)),
        (flesh, "flesh", lit_flesh),
        (pit, "pit", lambda p, rng, ramp: shade(rng, dome(pc, 14, p), 0.12)),
    ]
    return out, [unary_union([skin, flesh, pit]).boundary]


def egg():
    t = np.linspace(0, 2 * np.pi, 64, endpoint=False)
    shape = Polygon(np.c_[12.5 * np.cos(t) * (1 + 0.09 * np.sin(t)), 15.5 * np.sin(t)])
    return [(shape, "egg", lambda p, rng, ramp: shade(rng, 0.85 * dome((0, 0), 15, p) - 0.05, 0.08))], [shape.boundary]


# ---------- Placing, cutting and stacking ----------

def place(food, dx, dy, rot=0.0, origin=(0, 0)):
    zones, outlines = food

    def move(g):
        return affinity.translate(affinity.rotate(g, rot, origin=origin), dx, dy)

    out = []
    for g, ramp, lit in zones:
        def moved_lit(p, rng, ramp, lit=lit):
            q = affinity.translate(affinity.rotate(Point(p), -rot, origin=(origin[0] + dx, origin[1] + dy)), -dx, -dy)
            return lit((q.x, q.y), rng, ramp)
        out.append((clean(move(g)), ramp, moved_lit))
    return out, [move(o) for o in outlines]


def area(zones):
    return unary_union([g for g, _, _ in zones]).area


def cut(food, keep):
    """The left part of a food in its own frame, cut straight down to keep of its area."""
    zones, outlines = food
    whole = unary_union([g for g, _, _ in zones])
    x0, _, x1, _ = whole.bounds
    xc = brentq(lambda x: whole.intersection(box(x0 - 1, -999, x, 999)).area - keep * whole.area, x0, x1)
    left = box(x0 - 1, -999, xc, 999)
    return [(clean(g.intersection(left)), ramp, lit) for g, ramp, lit in zones], [o.intersection(left) for o in outlines]


def inside_pan():
    t = np.linspace(0, 2 * np.pi, 120, endpoint=False)
    return Polygon(np.c_[(PAN["rx"] - 2) * np.cos(t), (PAN["ry"] - 0.8) * np.sin(t)]).union(
        box(-(PAN["rx"] - 2), -400, PAN["rx"] - 2, 0))


def stack(items):
    """items back to front, each (kind, (zones, outlines)): the visible part of every zone."""
    pan = inside_pan()
    out, covered = [], Polygon()
    for kind, (zones, outlines) in reversed(items):
        whole = clean(unary_union([g for g, _, _ in zones]).intersection(pan))
        whole = clean(whole.buffer(0.05, join_style="mitre").buffer(-0.05, join_style="mitre"))   # no hairline gaps
        vis = [(clean(g.intersection(pan).difference(covered)), ramp, lit) for g, ramp, lit in zones]
        vis = [z for z in vis if not z[0].is_empty and z[0].area > 0.01]
        out.append((kind, vis, [o.intersection(pan.buffer(1)) for o in outlines], clean(whole.difference(covered))))
        covered = covered.union(whole)
    return out[::-1], covered


def heap_2017():
    return [
        ("broccoli", place(broccoli(), -18, -32)),
        ("avocado", place(avocado(), 30, -40, 14, origin=(0, 26))),
        ("salmon", place(salmon(), -70, -4, -2)),
        ("egg", place(egg(), 58, -16)),
        ("egg", place(egg(), 43, -12)),
    ]


def bounds(piece):
    return unary_union([g for g, _, _ in piece[0]]).bounds


HALF_AVOCADO = unary_union([g for g, _, _ in avocado()[0]]).area
QUARTER = unary_union([g for g, _, _ in quarter()[0]]).area


def heap_2022(keep):
    """The same food cut down: the broccoli half lies on its cut face and the avocado
    quarter on its skin, its pit kept, sized to keep the same share of the half's area."""
    broc = cut(broccoli(), keep)
    x0, y0, x1, y1 = bounds(broc)
    broc = place(broc, 0, 0, 90, origin=(x1, y1))           # the cut face down
    k = np.sqrt(keep * HALF_AVOCADO / QUARTER)
    avo = ([(affinity.scale(g, k, k, origin=(0, 0)), r,
             (lambda p, rng, ramp, lit=lit: lit((p[0] / k, p[1] / k), rng, ramp))) for g, r, lit in quarter()[0]], [])
    fish = place(cut(salmon(), keep), 0, -4, -2)
    b, a, f = bounds(broc), bounds(avo), bounds(fish)
    items = [
        ("broccoli", place(broc, -42 - b[0], -3 - b[3])),
        ("avocado", place(avo, 30 - a[0], 5 - a[3], -6, origin=(a[0], a[3]))),
        ("egg", place(egg(), 13, -14, 14, origin=(0, 15))),
        ("salmon", place(fish, -44 - f[0], 0)),
    ]
    x0 = min(bounds(p)[0] for _, p in items)
    x1 = max(bounds(p)[2] for _, p in items)
    return [(k, place(p, -(x0 + x1) / 2, 0)) for k, p in items]


# ---------- Shards ----------

SCALE = {"salmon": 1.0, "broccoli": 0.85, "avocado": 1.0, "egg": 1.5}   # shard size, by food


def seeds(region, rng, k=1.0):
    """Seeds spaced by random sizes over a region, so shards come in a wide range of sizes."""
    x0, y0, x1, y1 = region.bounds
    lo, hi = np.log(k * SIZES[0]), np.log(k * SIZES[1])
    grid, pts = {}, []
    xs = rng.uniform(x0, x1, int(region.area) + 300)
    ys = rng.uniform(y0, y1, len(xs))
    inside = shapely.contains_xy(region, xs, ys)
    for x, y, ok in zip(xs, ys, inside):
        if not ok:
            continue
        r = float(np.exp(rng.uniform(lo, hi)))
        gx, gy = int(x // (k * SIZES[1])), int(y // (k * SIZES[1]))
        if all((x - q[0]) ** 2 + (y - q[1]) ** 2 >= (0.8 * (r + q[2])) ** 2
               for a in range(-2, 3) for b in range(-2, 3) for q in grid.get((gx + a, gy + b), ())):
            grid.setdefault((gx, gy), []).append((x, y, r))
            pts.append((x, y))
    return pts


def crack(piece, rng, times):
    """A piece split along random lines through it, as terrazzo chips break."""
    out = [piece]
    for _ in range(times):
        big = max(out, key=lambda g: g.area)
        if big.area < 10 or rng.random() < 0.45:
            continue
        c = big.centroid
        size = np.sqrt(big.area)
        p = np.array([c.x, c.y]) + rng.uniform(-0.25, 0.25, 2) * size
        a = rng.uniform(0, np.pi)
        d = np.array([np.cos(a), np.sin(a)]) * 4 * size
        parts = list(shapely.ops.split(big, LineString([p - d, p + d])).geoms)
        if len(parts) > 1 and min(g.area for g in parts) > 1.2:
            out.remove(big)
            out.extend(parts)
    return out


def shards(stacked, rng):
    """Each zone of each food tiled on its own, so a fine line runs along every edge between zones."""
    by_tone, covered = {}, []
    for kind, zones, outlines, visible in stacked:
        if visible.is_empty:
            continue
        covered.append(visible)
        for g, ramp, lit in zones:
            for zone in getattr(g, "geoms", [g]):
                if zone.geom_type != "Polygon" or zone.area < 0.2:
                    continue
                pieces = [zone]
                if zone.area > 6:
                    pts = seeds(zone, rng, SCALE[kind])
                    if len(pts) > 1:
                        cells = shapely.voronoi_polygons(MultiPoint(pts), extend_to=zone.envelope.buffer(12))
                        pieces = [q for cell in cells.geoms for q in getattr(cell.intersection(zone), "geoms",
                                  [cell.intersection(zone)]) if q.geom_type == "Polygon"]
                for piece in pieces:
                    for c in crack(piece, rng, 2):
                        t = c.buffer(-LINE / 2, join_style="mitre", mitre_limit=2).simplify(0.06)
                        for bit in getattr(t, "geoms", [t]):
                            if bit.geom_type != "Polygon" or bit.area < 0.1:
                                continue
                            m = bit.centroid
                            tone = f"{ramp}-{1 + int(lit((m.x, m.y), rng, ramp) * RAMPS[ramp])}"
                            by_tone.setdefault(tone, []).append(bit)
    drawn = unary_union([g.buffer(LINE / 2 + 0.05, join_style="mitre") for v in by_tone.values() for g in v])
    gaps = unary_union(covered).difference(drawn)
    worst = max((g.area for g in getattr(gaps, "geoms", [gaps])), default=0.0)
    return by_tone, worst


def path(geoms):
    """Polygons as one SVG path, grown by GROW, in tenths of a unit, each ring's points relative to the last."""
    out = []
    for g in geoms:
        for poly in getattr(g, "geoms", [g]):
            if poly.geom_type != "Polygon" or poly.is_empty:
                continue
            for ring in [poly.exterior, *poly.interiors]:
                xy = np.round(np.asarray(ring.coords)[:-1] * 10 * GROW).astype(int)
                d = np.diff(xy, axis=0)
                out.append(f"M{xy[0][0]},{xy[0][1]}l" + " ".join(f"{x},{y}" for x, y in d) + "z")
    return "".join(out)


def measure(heap):
    """The area of a heap's shards, from its stored paths."""
    total = 0.0
    for d in heap["shards"].values():
        for sub in d.split("M")[1:]:
            start, rel = sub.rstrip("z").split("l")
            xy = np.cumsum([list(map(int, start.split(",")))] +
                           [list(map(int, q.split(","))) for q in rel.split(" ")], axis=0) / 10
            x, y = xy[:, 0], xy[:, 1]
            total += 0.5 * (x @ np.roll(y, -1) - np.roll(x, -1) @ y)
    return abs(total)


def main():
    with open(DATA, encoding="utf-8") as f:
        text = f.read()
    body, tail = text[len(PREFIX):], ""
    if body.rstrip().endswith(";"):
        body, tail = body.rstrip()[:-1], ";\n"
    data = json.loads(body)
    keep_total = 1 - data["examples"]["ikea"]["food_waste_cut"] / 100

    if "--check" in sys.argv:
        h = data["food_heaps"]["heaps"]
        a, s = [x["area"] for x in h], [measure(x) for x in h]
        print(f"2022's heap covers {100 * a[1] / a[0]:.3f}% of 2017's area (target {100 * keep_total:.3f}%); "
              f"its shards, {100 * s[1] / s[0]:.3f}% of 2017's shards")
        return

    _, left = stack(heap_2017())
    target = keep_total * left.area
    keep = brentq(lambda k: stack(heap_2022(k))[1].area - target, 0.2, 0.7, xtol=1e-7)
    rng = np.random.default_rng(SEED)
    heaps = []
    for items in (heap_2017(), heap_2022(keep)):
        stacked, covered = stack(items)
        by_tone, worst = shards(stacked, rng)
        print(f"Largest gap left by the shards: {worst:.2f} square units")
        heaps.append({"area": round(covered.area * GROW ** 2, 3), "shards": {k: path(v) for k, v in sorted(by_tone.items())}})
    a, sh = [x["area"] for x in heaps], [measure(x) for x in heaps]
    print(f"Cut share {100 * keep:.2f}%; 2022's heap covers {100 * a[1] / a[0]:.3f}% of 2017's area "
          f"(target {100 * keep_total:.3f}%), shards {100 * sh[1] / sh[0]:.3f}%, "
          f"count {[sum(d.count('M') for d in h['shards'].values()) for h in heaps]}")

    if "--preview" in sys.argv:
        out = sys.argv[sys.argv.index("--preview") + 1]
        with open(PAGE, encoding="utf-8") as f:   # the page's own colors
            css = ":root{" + "".join(f"--{k}:{v};" for k, v in re.findall(r"--([a-z0-9-]+): (#[0-9A-Fa-f]{6})", f.read())) + "}"
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-100 -150 400 170" width="1600" height="680">'
                 f'<style>{css}</style><rect x="-100" y="-150" width="400" height="170" fill="#fff"/>']
        for i, h in enumerate(heaps):
            parts.append(f'<g transform="translate({i * 200},0) scale(0.1)">')
            parts.append(f'<ellipse rx="{PAN["rx"] * GROW * 10}" ry="{PAN["ry"] * GROW * 10}" fill="#C9D0D6"/>')
            for k, d in h["shards"].items():
                parts.append(f'<path d="{d}" style="fill:var(--{k})"/>')
            parts.append("</g>")
        parts.append("</svg>")
        with open(out, "w") as f:
            f.write("".join(parts))

    data["food_heaps"] = {
        "pan": {k: round(v * GROW, 2) for k, v in PAN.items()}, "keep_pct": round(100 * keep, 3),
        "heaps": heaps,
    }
    with open(DATA, "w", encoding="utf-8") as f:
        f.write(PREFIX + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + tail)
    print("Wrote", os.path.relpath(DATA, ROOT), f"({os.path.getsize(DATA) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
