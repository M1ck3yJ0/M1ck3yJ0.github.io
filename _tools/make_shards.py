"""Build the ring's center as terrazzo: shards in one blue per kind of material, each
material's shards covering exactly its share of the EU's material use by weight.

Usage:
    python3 -I _tools/make_shards.py [--check]

Takes the weight shares from the data file's "weight_vs_climate" block (ETC CE Report
2025/3, Figure 3-4, EU 2022), the same shares the ribbon chart draws, and writes the shards
into the data file under "center_shards". With --check, writes nothing and re-measures the
shards already in the data file.

It also writes panel 4's disc under "center_shards" -> "recycle": recycling raised until the
ring closes, each extra recycled tonne replacing part of a new one of the same material (the
data file's "replacement"; the share replaced is build_data.py's "less_new_material_to_close"),
the tonnes replaced split across materials by each one's share of the waste not
yet recycled (the data file's "not_recycled_mix"), taken out as whole shards as below, with
a share for each material.

And it writes panel 5's disc under "center_shards" -> "less": the same disc with the
material taken out that closes the ring at 24% with recycling held at its 2022 level, as
the page computes it, taken out of every material alike as whole shards. For each
material, about that share of its shards goes at every size, then swaps between shards
close in size bring the area taken out to the share. Of many such picks, the one that
leaves the disc most evenly covered is kept. The shards left are resized so every
material keeps its exact share, and the disc is re-solved from its current layout, with
the gap set so the slivers keep their share of the disc. The page draws it at the square
root of the material left.

How the shards are made: shard sizes for each material are drawn across a 14-fold range
(so every material gets small and large shards) and scaled to its exact share. Shards are
grouped one to three to a cell, the cells placed by a random packing, and a power diagram
(a weighted Voronoi diagram) clipped to the disc gives each cell's shape. A cell holding
two or three shards is cracked along random lines, each crack placed so every shard gets
its exact area. Every shared edge sits half a gap in from the line between cells, so a
sliver of background separates all shards. Newton's method on the diagram's weights makes
every shard's final area, gaps taken out, proportional to its target. Coordinates use SVG's
convention (x right, y down) on a disc of radius 1, rounded to 5 decimals; the check
measures the rounded shards, which is what the page draws.
"""
import json
import os
import sys

import numpy as np
from scipy.optimize import brentq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "projects", "far_from_full_circle", "far_from_full_circle_data.js")
PREFIX = "window.FAR_FROM_FULL_CIRCLE_DATA = "
MATERIALS = [("minerals", "Non-metallic minerals"), ("biomass", "Biomass"), ("fossil", "Fossil fuels"),
             ("metals", "Metal ores")]
SETTINGS = dict(seed=23, n_pieces=115, ratio=14.0, gap=0.015, jitter=0.8, group_p=(0.2, 0.5, 0.3))
LESS_SETTINGS = dict(seed=12, tries=3000)
TARGET = 0.24                                        # the EU's circularity target for 2030
K = 256                                             # vertices on the disc's edge
CIRCLE = np.stack([np.cos(t := np.linspace(0, 2 * np.pi, K, endpoint=False)), np.sin(t)], 1)


# ---------- Polygons ----------

def area(V):
    if len(V) < 3:
        return 0.0
    x, y = V[:, 0], V[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def width(V):
    e = np.roll(V, -1, 0) - V
    L = np.hypot(*e.T)
    n = np.stack([-e[L > 1e-9, 1], e[L > 1e-9, 0]], 1) / L[L > 1e-9, None]
    p = V @ n.T
    return float((p.max(0) - p.min(0)).min())


def clip(V, E, a, b, label):
    """The part of convex polygon V with a.x <= b. E[k] names the source of edge k."""
    s = V @ a - b
    outV, outE = [], []
    for k in range(len(V)):
        k1 = (k + 1) % len(V)
        if s[k] <= 0:
            outV.append(V[k]); outE.append(E[k])
            if s[k1] > 0:
                outV.append(V[k] + s[k] / (s[k] - s[k1]) * (V[k1] - V[k])); outE.append(label)
        elif s[k1] <= 0:
            outV.append(V[k] + s[k] / (s[k] - s[k1]) * (V[k1] - V[k])); outE.append(E[k])
    if len(outV) < 3:
        return np.zeros((0, 2)), np.zeros(0, int)
    return np.array(outV), np.array(outE)


# ---------- Power diagram, gaps taken out ----------

def cell(i, P, W, gap):
    d = P - P[i]
    dist = np.hypot(*d.T)
    A, B = 2 * d, (P ** 2).sum(1) - (P[i] ** 2).sum() - (W - W[i]) - gap * dist
    idx = np.array([j for j in range(len(P)) if j != i])
    V, E = CIRCLE.copy(), np.full(K, -1)
    while len(V):
        viol = (V @ A[idx].T - B[idx]).max(0)
        k = int(np.argmax(viol))
        if viol[k] <= 1e-13:
            break
        V, E = clip(V, E, A[idx[k]], B[idx[k]], idx[k])
    return V, E, dist


def diagram(P, W, gap):
    n = len(P)
    cells, J = [], np.zeros((n, n))
    for i in range(n):
        V, E, dist = cell(i, P, W, gap)
        cells.append(V)
        if len(V):
            for e, l in zip(E, np.hypot(*(np.roll(V, -1, 0) - V).T)):
                if e >= 0:                      # d(area)/d(weight) along a shared edge
                    J[i, i] += l / (2 * dist[e]); J[i, e] -= l / (2 * dist[e])
    return cells, J


# ---------- Cracks ----------

def halves(Q, nrm, b, gap):
    E = np.full(len(Q), -1)
    return clip(Q, E, nrm, b - gap / 2, -2)[0], clip(Q, E, -nrm, -(b + gap / 2), -2)[0]


def crack_to(Q, theta, frac, gap):
    """Crack Q at angle theta so the first piece holds frac of the two pieces' area."""
    nrm = np.array([np.cos(theta), np.sin(theta)])
    p = Q @ nrm
    def f(b):
        a1, a2 = (area(h) for h in halves(Q, nrm, b, gap))
        return (a1 / (a1 + a2) if a1 + a2 > 0 else 0.0) - frac
    return halves(Q, nrm, brentq(f, p.min() - gap, p.max() + gap, xtol=1e-15, rtol=1e-15), gap)


def split(V, members, sizes, angles, gap):
    """A cell's shards, each with its exact share of the cell. With three, the first crack
    sits so the first shard keeps its share after the second crack takes its sliver."""
    a = sizes[members]
    if len(members) == 1:
        return [V]
    if len(members) == 2:
        return list(crack_to(V, angles[0], a[0] / a.sum(), gap))
    nrm = np.array([np.cos(angles[0]), np.sin(angles[0])])
    p, out = V @ nrm, {}
    def f(b):
        first, rest = halves(V, nrm, b, gap)
        if len(rest) == 0:
            return 1.0
        out["s"] = [first, *crack_to(rest, angles[1], a[1] / a[1:].sum(), gap)]
        a1 = area(first)
        return a1 / (a1 + area(out["s"][1]) + area(out["s"][2])) - a[0] / a.sum()
    f(brentq(f, p.min() - gap, p.max() + gap, xtol=1e-15, rtol=1e-15))
    return out["s"]


def shards_of(cells, groups, sizes, angles, gap):
    shards, A = {}, np.zeros(len(cells))
    for u, (V, members) in enumerate(zip(cells, groups)):
        for k, s in zip(members, split(V, members, sizes, angles[u], gap)):
            shards[k] = s
            A[u] += area(s)
    return shards, A


def solve(P, W, t, gap, groups=None, sizes=None, angles=None, tol=1e-10):
    """Damped Newton on the weights until every cell's shard area is proportional to t."""
    def evaluate(W):
        cells, J = diagram(P, W, gap)
        if not all(len(V) for V in cells):
            return None
        if groups is None:
            return cells, J, None, np.array([area(V) for V in cells])
        shards, A = shards_of(cells, groups, sizes, angles, gap)
        return cells, J, shards, A
    def error(A):
        return np.max(np.abs(A - t * A.sum()) / (t * A.sum()))
    cells, J, shards, A = evaluate(W)
    for _ in range(100):
        err = error(A)
        if err < tol:
            return W, cells, shards, err
        F = A - t * A.sum()
        DF = J - np.outer(t, J.sum(0))
        dW = np.linalg.lstsq(np.vstack([DF, np.ones(len(P))]), np.r_[-F, 0.0], rcond=None)[0]
        lam = 1.0
        while lam > 1e-6:
            res = evaluate(W + lam * dW)
            if res and np.all(res[3] > 0) and error(res[3]) < err:
                W = W + lam * dW
                cells, J, shards, A = res
                break
            lam /= 2
        else:
            raise RuntimeError("Newton step failed; try another seed")
    raise RuntimeError("did not converge")


# ---------- The mosaic ----------

def make(shares, seed, n_pieces, ratio, gap, jitter, group_p, min_w=0.06):
    rng = np.random.default_rng(seed)
    mats, sizes = [], []
    for m, s in enumerate(shares):                   # stratified draws, scaled to the share
        n = max(5, int(round(s * n_pieces)))
        a = ratio ** ((np.arange(n) + rng.uniform(0, 1, n)) / n)
        mats += [m] * n
        sizes += list(a * s / a.sum())
    mats, sizes = np.array(mats), np.array(sizes)
    order, groups = rng.permutation(len(sizes)), []
    while sum(map(len, groups)) < len(order):
        k = sum(map(len, groups))
        groups.append(list(order[k:k + int(rng.choice([1, 2, 3], p=group_p))]))
    usize = np.array([sizes[g].sum() for g in groups])
    # random packing, biggest first, easing the clearance when a spot is hard to find
    r = np.sqrt(usize / usize.sum() * 0.86) * 0.92
    P, placed = np.zeros((len(usize), 2)), []
    for i in np.argsort(-usize):
        slack = 1.0
        while True:
            rho = (1 - 0.25 * r[i]) * np.sqrt(rng.uniform(size=3000))
            th = rng.uniform(0, 2 * np.pi, 3000)
            cand = np.stack([rho * np.cos(th), rho * np.sin(th)], 1)
            if not placed:
                P[i] = cand[0]; break
            gap_ok = (np.hypot(*(cand[:, None, :] - P[placed][None, :, :]).transpose(2, 0, 1))
                      - slack * (r[i] + r[placed])[None, :]).min(1) >= 0
            if gap_ok.any():
                P[i] = cand[np.argmax(gap_ok)]; break
            slack *= 0.95
        placed.append(i)
    off = rng.normal(0, 1, P.shape)                  # sites off their circles' middles
    off /= np.hypot(*off.T)[:, None]
    P = P + off * (jitter * r * np.sqrt(rng.uniform(size=len(P))))[:, None]
    P *= np.minimum(1, 0.995 / np.hypot(*P.T))[:, None]
    t = usize / usize.sum()
    W, cells, _, _ = solve(P, r ** 2, t, gap)
    angles = []                                      # crack angles that leave every shard wide
    for V, members in zip(cells, groups):
        best, best_w = None, -1.0
        for _ in range(80):
            th = rng.uniform(0, np.pi)
            ang = [th, th + np.radians(rng.uniform(45, 135))]
            pcs = split(V, members, sizes, ang, gap)
            w = min(width(p) for p in pcs) if all(len(p) for p in pcs) else -1.0
            if w > best_w:
                best, best_w = ang, w
            if w >= 1.3 * min_w:
                break
        angles.append(best)
    W, cells, shards, err = solve(P, W, t, gap, groups, sizes, angles)
    state = dict(P=P, W=W, groups=groups, angles=angles, sizes=sizes, mats=mats)
    return [(int(mats[k]), shards[k]) for k in sorted(shards)], err, state


# ---------- Using less: panel 5's disc ----------

def unevenness(shards, gone, less):
    """How unevenly the shards left cover the disc: over 17 regions (a middle, a ring of 6 and
    a ring of 10), the area-weighted root mean square of each region's share left, against the
    share left overall."""
    C = np.array([V.mean(0) for _, V in shards])
    A = np.array([area(V) for _, V in shards])
    r, th = np.hypot(*C.T), np.arctan2(C[:, 1], C[:, 0]) % (2 * np.pi)
    reg = np.where(r < 0.4, 0, np.where(r < 0.75, 1 + np.minimum(th // (np.pi / 3), 5),
                                        7 + np.minimum(th // (np.pi / 5), 9))).astype(int)
    left = A * ~np.isin(np.arange(len(A)), list(gone))
    tot, kept = np.bincount(reg, A, 17), np.bincount(reg, left, 17)
    if np.ndim(less):                                # a share for each material: each region against its own mix
        M = np.array([m for m, _ in shards])
        due = np.divide(np.bincount(reg, A * (1 - np.asarray(less)[M]), 17), tot, out=np.zeros(17), where=tot > 0)
        share = np.divide(kept, tot, out=due.copy(), where=tot > 0)
        return np.sqrt(np.sum(tot * (share - due) ** 2) / tot.sum())
    share = np.divide(kept, tot, out=np.full(17, 1 - less), where=tot > 0)
    return np.sqrt(np.sum(tot * (share - (1 - less)) ** 2) / tot.sum())


def pick(rng, sizes, mats, less):
    """Whole shards to take out: for each material, its shards in order of size, in fives (threes
    for a material with under ten), each five giving up its share of shards, carried over, at
    random; then swaps within a five bring the area taken out closest to `less` of the material's.
    `less` is one share for every material, or a list with one per material."""
    gone, shares = [], less
    for m in range(len(MATERIALS)):
        less = shares[m] if np.ndim(shares) else shares
        ids = sorted((int(k) for k in np.flatnonzero(mats == m)), key=lambda k: sizes[k])
        w = 5 if len(ids) >= 10 else 3
        acc, out = rng.uniform(), []
        for s in (ids[i:i + w] for i in range(0, len(ids), w)):
            acc += less * len(s)
            c = int(acc)
            acc -= c
            out += [int(k) for k in rng.choice(s, size=min(c, len(s)), replace=False)]
        five = {k: i // w for i, k in enumerate(ids)}
        target = less * sizes[ids].sum()
        while True:
            now = sizes[out].sum()
            moves = [(abs(now - sizes[a] + sizes[b] - target), a, b)
                     for a in out for b in ids if b not in out and five[a] == five[b]]
            if not moves or min(moves)[0] >= abs(now - target) - 1e-15:
                break
            _, a, b = min(moves)
            out.remove(a)
            out.append(b)
        gone += out
    return set(gone)


def remove(state, gone, sizes, gap):
    """The disc re-solved from its current layout with whole shards taken out, so the shards
    left close over the gaps; sizes gives each shard left its target."""
    keep = [(p, w, [k for k in g if k not in gone], a)
            for p, w, g, a in zip(state["P"], state["W"], state["groups"], state["angles"])]
    keep = [c for c in keep if c[2]]
    P, W = np.array([c[0] for c in keep]), np.array([c[1] for c in keep])
    groups, angles = [c[2] for c in keep], [c[3] for c in keep]
    usize = np.array([sizes[g].sum() for g in groups])
    t = usize / usize.sum()
    try:
        return solve(P, W, t, gap, groups, sizes, angles)
    except RuntimeError:                             # as make() does: the cells first, then the cracks
        return solve(P, solve(P, W, t, gap)[0], t, gap, groups, sizes, angles)


def use_less(shards, state, less, seed, tries):
    """Panel 5's disc: `less` of every material taken out as whole shards, the most even of
    `tries` picks; the shards left resized so every material keeps its exact share, and the gap
    set so the slivers keep their share of the disc. Returns the gap and the shards left.
    `less` may be a list with one share per material, as for panel 4's disc."""
    rng = np.random.default_rng(seed)
    sizes0, mats = state["sizes"], state["mats"]
    gone = min((pick(rng, sizes0, mats, less) for _ in range(tries)),
               key=lambda g: unevenness(shards, g, less))
    sizes = sizes0.copy()
    out = np.isin(np.arange(len(sizes)), list(gone))
    for m in range(len(MATERIALS)):
        mine, left = mats == m, (mats == m) & ~out
        lm = less[m] if np.ndim(less) else less
        sizes[left] *= (1 - lm) * sizes0[mine].sum() / sizes0[left].sum()
    slivers = 1 - sum(area(V) for _, V in shards) / np.pi
    found = {}
    def miss(gap):
        if gap not in found:
            found[gap] = remove(state, gone, sizes, gap)[2]
        return 1 - sum(area(V) for V in found[gap].values()) / np.pi - slivers
    kept = sizes[~out].sum() / sizes0.sum() if np.ndim(less) else 1 - less   # share of the material left
    g0 = SETTINGS["gap"] / np.sqrt(kept)             # a gap of the same width on screen
    gap = brentq(miss, 0.6 * g0, 1.4 * g0, xtol=1e-7)
    miss(gap)
    return gap, found[gap]


# ---------- Measuring ----------

def measure(shards):
    a = np.array([area(V) for _, V in shards])
    m = np.array([k for k, _ in shards])
    return [100 * a[m == k].sum() / a.sum() for k in range(len(MATERIALS))], a, m


def report(shards, shares, label):
    got, a, m = measure(shards)
    print(f"{label}: {len(shards)} shards; gaps take {100 * (1 - a.sum() / np.pi):.1f}% of the disc")
    for k, (name, _) in enumerate(MATERIALS):
        sel = a[m == k]
        print(f"  {name:9s} target {shares[k]:8.4f}%  shards {got[k]:8.4f}%  "
              f"diff {got[k] - shares[k]:+.5f} pt  ({len(sel)} shards, {sel.min() / sel.max() * 100:.0f}% to 100% of its largest)")
    return got


def shares_from(data):
    rows = {r["material_group"]: r["share_of_weight_pct"] for r in data["weight_vs_climate"]}
    return [rows[group] for _, group in MATERIALS]


def main():
    with open(DATA, encoding="utf-8") as f:
        text = f.read()
    tail = text[text.rindex(";"):]
    data = json.loads(text[len(PREFIX):text.rindex(";")])
    if "--check" in sys.argv:
        cs = data["center_shards"]
        shards = [(s["m"], np.array(s["p"]).reshape(-1, 2)) for s in cs["shards"]]
        shares = [cs["shares_pct"][name] for name, _ in MATERIALS]
        report(shards, shares, "In the data file")
        if "less" in cs:
            left = [(cs["shards"][s["k"]]["m"], np.array(s["p"]).reshape(-1, 2)) for s in cs["less"]["shards"]]
            report(left, shares, f"Panel 5, {cs['less']['less_pct']}% less, in the data file")
        if "recycle" in cs:
            rc = cs["recycle"]
            left = [(cs["shards"][s["k"]]["m"], np.array(s["p"]).reshape(-1, 2)) for s in rc["shards"]]
            due = [sh * (100 - rc["less_pct"][name]) / (100 - rc["replaced_pct"]) for (name, _), sh in zip(MATERIALS, shares)]
            report(left, due, f"Panel 4, {rc['replaced_pct']}% replaced, in the data file")
        return
    shares = shares_from(data)
    shards, err, state = make(np.array(shares) / 100, **SETTINGS)
    rounded = [(m, np.round(V, 5)) for m, V in shards]
    report(shards, shares, f"Solved (largest error in a cell {err:.0e})")
    report(rounded, shares, "Rounded to 5 decimals, as stored")
    eu = data["countries"]["EU27_2020"]                # as the page: the cut that closes the ring
    u, dmc = eu["circular_use_kt"], eu["consumption_kt"]
    less = 1 - (u / TARGET - u) / dmc
    gap, left = use_less(rounded, state, less, **LESS_SETTINGS)
    left = {k: np.round(V, 5) for k, V in sorted(left.items())}
    report([(int(state["mats"][k]), V) for k, V in left.items()], shares,
           f"Panel 5, {100 * less:.1f}% less, rounded as stored")
    # Panel 4's disc: recycling raised until the ring closes, each extra recycled tonne replacing
    # part of a new one of the same material, split across materials by their waste not yet recycled
    x = eu["less_new_material_to_close"] / 100        # new material replaced, as a share of all of it (build_data.py)
    nrm = eu["not_recycled_mix"]
    rec = [x * nrm[name] / s for (name, _), s in zip(MATERIALS, shares)]
    rgap, rleft = use_less(rounded, state, rec, **LESS_SETTINGS)
    rleft = {k: np.round(V, 5) for k, V in sorted(rleft.items())}
    rem = 1 - x
    report([(int(state["mats"][k]), V) for k, V in rleft.items()],
           [s * (1 - r) / rem for s, r in zip(shares, rec)], f"Panel 4, {100 * x:.1f}% replaced, rounded as stored")
    data["center_shards"] = {
        "source": "weight_vs_climate: ETC CE Report 2025/3, Figure 3-4, EU 2022",
        "materials": [name for name, _ in MATERIALS],
        "shares_pct": {name: round(s, 4) for (name, _), s in zip(MATERIALS, shares)},
        "gap": SETTINGS["gap"],
        "shards": [{"m": m, "p": [float(x) for x in V.ravel()]} for m, V in rounded],
        "less": {"less_pct": round(100 * less, 4), "gap": round(gap, 6),
                 "shards": [{"k": int(k), "p": [float(x) for x in V.ravel()]} for k, V in left.items()]},
        "recycle": {"replaced_pct": round(100 * x, 4),
                    "less_pct": {name: round(100 * r, 4) for (name, _), r in zip(MATERIALS, rec)},
                    "gap": round(rgap, 6),
                    "shards": [{"k": int(k), "p": [float(v) for v in V.ravel()]} for k, V in rleft.items()]},
    }
    out = PREFIX + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + tail
    with open(DATA, "w", encoding="utf-8") as f:
        f.write(out)
    print("Wrote", len(rounded), "shards, panel 4's", len(rleft), "and panel 5's", len(left), "to", os.path.relpath(DATA, ROOT))


if __name__ == "__main__":
    main()
