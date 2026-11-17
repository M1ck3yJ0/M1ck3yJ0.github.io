/* Far from Full Circle: the ring's center as terrazzo, solved in the page.

   The solver of _tools/make_shards.py, ported to JavaScript for the ring game and for panel 5's
   in-between layouts. build() makes a disc of shards, one material per shard, each material's
   shards covering its share of the shards' area. remove() takes whole shards out and re-solves the
   disc from its current layout, so the neighbors close over the gap and the rest barely move.

   Load it with <script src="far_from_full_circle_shards.js"> before the page's own script, or with
   importScripts() in a Web Worker; either sets FAR_FROM_FULL_CIRCLE_SHARDS. In Node, require() it.

     const S = FAR_FROM_FULL_CIRCLE_SHARDS;
     const disc = S.build([52.3, 22.7, 19.5, 5.5]);  // shares in make_shards.py's MATERIALS order:
                                                     // minerals, biomass, fossil fuels, metal ores
     S.remove(disc, [id1, id2]);                     // whole shards out; the disc is re-solved in place
     disc.shards      // Map: shard id -> polygon [[x, y], ...] on a disc of radius 1, SVG's y down
     disc.mats[id]    // the shard's material index; disc.sizes[id], its share of the starting material
     disc.remaining   // share of the starting material left
     disc.radius      // radius to draw at, relative to the starting disc
     S.measure(disc)  // each material's share of the shards' area, and the slivers' share of the disc

   How the shards are made is described in _tools/make_shards.py, and this follows it step for step,
   except:
   - Its own random numbers, so a seed here doesn't give the Python layout. A seed that fails to
     solve moves on to the next; build() records the seed used in disc.seed, so a layout can be
     kept by storing its seed.
   - Looser default tolerances: every cell within 1e-4 of its area and cracks placed to 1e-9.
     Pass tol and crackTol to tighten them; make_shards.py uses 1e-10 and 1e-15.
   - Shares of zero or less get no shards. Shares are scaled to sum to one.

   The gap between shards keeps a fixed width on screen: remove() sets it to the starting gap over
   the square root of the material left, unless a gap is passed. The slivers' share of the disc then
   drifts with the mix of shard sizes left, so draw the disc at disc.radius, which keeps the shards'
   area in proportion to the material left; the square root of the material left does not.

   fromState() rebuilds a full disc from its solver state: sites P, weights W, groups (the shards in
   each cell), sizes, mats, crack angles and gap, as make_shards.py's make() holds them.
*/
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FAR_FROM_FULL_CIRCLE_SHARDS = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const K = 256;                                   // vertices on the disc's edge
  const CIRCLE = Array.from({ length: K }, (_, k) => [Math.cos(2 * Math.PI * k / K), Math.sin(2 * Math.PI * k / K)]);
  const DEFAULTS = { seed: 23, tries: 20, nPieces: 115, ratio: 14, gap: 0.015, jitter: 0.8,
                     groupP: [0.2, 0.5, 0.3], minW: 0.06, tol: 1e-4, crackTol: 1e-9 };
  let CTOL = DEFAULTS.crackTol;
  const sum = a => { let s = 0; for (const x of a) s += x; return s; };

  // ---------- Polygons ----------

  function area(V) {
    const n = V.length;
    if (n < 3) return 0;
    let s = 0;
    for (let k = 0; k < n; k++) { const a = V[k], b = V[(k + 1) % n]; s += a[0] * b[1] - a[1] * b[0]; }
    return Math.abs(s) / 2;
  }

  function width(V) {
    let best = Infinity;
    for (let k = 0; k < V.length; k++) {
      const e0 = V[(k + 1) % V.length][0] - V[k][0], e1 = V[(k + 1) % V.length][1] - V[k][1], L = Math.hypot(e0, e1);
      if (L <= 1e-9) continue;
      let lo = Infinity, hi = -Infinity;
      for (const v of V) { const p = (-e1 * v[0] + e0 * v[1]) / L; lo = Math.min(lo, p); hi = Math.max(hi, p); }
      best = Math.min(best, hi - lo);
    }
    return best;
  }

  function clip(V, E, a, b, label) {               // the part of convex V with a.x <= b; E[k] names edge k's source
    const n = V.length, s = new Float64Array(n), outV = [], outE = [];
    for (let k = 0; k < n; k++) s[k] = V[k][0] * a[0] + V[k][1] * a[1] - b;
    const cut = (k, k1) => { const f = s[k] / (s[k] - s[k1]); return [V[k][0] + f * (V[k1][0] - V[k][0]), V[k][1] + f * (V[k1][1] - V[k][1])]; };
    for (let k = 0; k < n; k++) {
      const k1 = (k + 1) % n;
      if (s[k] <= 0) {
        outV.push(V[k]); outE.push(E[k]);
        if (s[k1] > 0) { outV.push(cut(k, k1)); outE.push(label); }
      } else if (s[k1] <= 0) { outV.push(cut(k, k1)); outE.push(E[k]); }
    }
    return outV.length < 3 ? [[], []] : [outV, outE];
  }

  // ---------- Power diagram, gaps taken out ----------

  function cell(i, P, W, gap) {
    const n = P.length, dist = new Float64Array(n), A = [], B = new Float64Array(n);
    const pi2 = P[i][0] ** 2 + P[i][1] ** 2;
    for (let j = 0; j < n; j++) {
      const dx = P[j][0] - P[i][0], dy = P[j][1] - P[i][1];
      dist[j] = Math.hypot(dx, dy); A.push([2 * dx, 2 * dy]);
      B[j] = P[j][0] ** 2 + P[j][1] ** 2 - pi2 - (W[j] - W[i]) - gap * dist[j];
    }
    let V = CIRCLE, E = new Array(K).fill(-1);
    while (V.length) {
      let best = -Infinity, bj = -1;
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        let m = -Infinity;
        for (const v of V) { const s = v[0] * A[j][0] + v[1] * A[j][1] - B[j]; if (s > m) m = s; }
        if (m > best) { best = m; bj = j; }
      }
      if (best <= 1e-13) break;
      [V, E] = clip(V, E, A[bj], B[bj], bj);
    }
    return [V, E, dist];
  }

  function diagram(P, W, gap) {
    const n = P.length, cells = [], J = Array.from({ length: n }, () => new Float64Array(n));
    for (let i = 0; i < n; i++) {
      const [V, E, dist] = cell(i, P, W, gap);
      cells.push(V);
      for (let k = 0; k < V.length; k++) {         // d(area)/d(weight) along a shared edge
        const e = E[k];
        if (e < 0) continue;
        const k1 = (k + 1) % V.length, l = Math.hypot(V[k1][0] - V[k][0], V[k1][1] - V[k][1]);
        J[i][i] += l / (2 * dist[e]); J[i][e] -= l / (2 * dist[e]);
      }
    }
    return [cells, J];
  }

  // ---------- Cracks ----------

  function halves(Q, nrm, b, gap) {
    const E = new Array(Q.length).fill(-1);
    return [clip(Q, E, nrm, b - gap / 2, -2)[0], clip(Q, E, [-nrm[0], -nrm[1]], -(b + gap / 2), -2)[0]];
  }

  function brent(f, a, b, tol) {                   // Brent's method, as scipy's brentq
    let fa = f(a), fb = f(b);
    if (fa * fb > 0) throw new Error('crack not bracketed');
    if (Math.abs(fa) < Math.abs(fb)) { [a, b] = [b, a]; [fa, fb] = [fb, fa]; }
    let c = a, fc = fa, d = b - a, mflag = true;
    for (let it = 0; it < 200; it++) {
      if (fb === 0 || Math.abs(b - a) < tol) return b;
      let s = fa !== fc && fb !== fc
        ? a * fb * fc / ((fa - fb) * (fa - fc)) + b * fa * fc / ((fb - fa) * (fb - fc)) + c * fa * fb / ((fc - fa) * (fc - fb))
        : b - fb * (b - a) / (fb - fa);
      if ((s - (3 * a + b) / 4) * (s - b) >= 0 || (mflag && Math.abs(s - b) >= Math.abs(b - c) / 2) ||
          (!mflag && Math.abs(s - b) >= Math.abs(c - d) / 2) || (mflag && Math.abs(b - c) < tol) || (!mflag && Math.abs(c - d) < tol)) {
        s = (a + b) / 2; mflag = true;
      } else mflag = false;
      const fs = f(s);
      d = c; c = b; fc = fb;
      if (fa * fs < 0) { b = s; fb = fs; } else { a = s; fa = fs; }
      if (Math.abs(fa) < Math.abs(fb)) { [a, b] = [b, a]; [fa, fb] = [fb, fa]; }
    }
    return b;
  }

  function span(Q, nrm) {
    let lo = Infinity, hi = -Infinity;
    for (const v of Q) { const p = v[0] * nrm[0] + v[1] * nrm[1]; lo = Math.min(lo, p); hi = Math.max(hi, p); }
    return [lo, hi];
  }

  function crackTo(Q, theta, frac, gap) {          // crack Q so the first piece holds frac of the two pieces' area
    const nrm = [Math.cos(theta), Math.sin(theta)], [lo, hi] = span(Q, nrm);
    const f = b => { const [h1, h2] = halves(Q, nrm, b, gap), a1 = area(h1), a2 = area(h2); return (a1 + a2 > 0 ? a1 / (a1 + a2) : 0) - frac; };
    return halves(Q, nrm, brent(f, lo - gap, hi + gap, CTOL), gap);
  }

  function split(V, members, sizes, angles, gap) { // a cell's shards, each with its exact share of the cell
    const a = members.map(k => sizes[k]), tot = sum(a);
    if (members.length === 1) return [V];
    if (members.length === 2) return crackTo(V, angles[0], a[0] / tot, gap);
    const nrm = [Math.cos(angles[0]), Math.sin(angles[0])], [lo, hi] = span(V, nrm);
    let out = null;
    const f = b => {
      const [first, rest] = halves(V, nrm, b, gap);
      if (rest.length === 0) return 1.0;
      out = [first, ...crackTo(rest, angles[1], a[1] / (a[1] + a[2]), gap)];
      const a1 = area(first);
      return a1 / (a1 + area(out[1]) + area(out[2])) - a[0] / tot;
    };
    f(brent(f, lo - gap, hi + gap, CTOL));
    return out;
  }

  function shardsOf(cells, groups, sizes, angles, gap) {
    const shards = new Map(), A = new Float64Array(cells.length);
    cells.forEach((V, u) => {
      const pcs = split(V, groups[u], sizes, angles[u], gap);
      groups[u].forEach((k, j) => { shards.set(k, pcs[j]); A[u] += area(pcs[j]); });
    });
    return [shards, A];
  }

  // ---------- Solving ----------

  function gauss(M, r) {                           // dense solve with partial pivoting
    const n = r.length, A = M.map(row => Float64Array.from(row)), b = Float64Array.from(r);
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let i = c + 1; i < n; i++) if (Math.abs(A[i][c]) > Math.abs(A[p][c])) p = i;
      [A[c], A[p]] = [A[p], A[c]]; [b[c], b[p]] = [b[p], b[c]];
      for (let i = c + 1; i < n; i++) {
        const f = A[i][c] / A[c][c];
        if (!f) continue;
        for (let j = c; j < n; j++) A[i][j] -= f * A[c][j];
        b[i] -= f * b[c];
      }
    }
    const x = new Float64Array(n);
    for (let i = n - 1; i >= 0; i--) { let s = b[i]; for (let j = i + 1; j < n; j++) s -= A[i][j] * x[j]; x[i] = s / A[i][i]; }
    return x;
  }

  function solve(P, W, t, gap, groups, sizes, angles, tol) {
    // damped Newton on the weights until every cell's shard area is proportional to t
    const n = P.length;
    const evaluate = W => {
      const [cells, J] = diagram(P, W, gap);
      if (!cells.every(V => V.length)) return null;
      if (!groups) return { cells, J, shards: null, A: Float64Array.from(cells, V => area(V)) };
      const [shards, A] = shardsOf(cells, groups, sizes, angles, gap);
      return { cells, J, shards, A };
    };
    const error = A => {
      const S = sum(A);
      let m = 0;
      for (let i = 0; i < n; i++) m = Math.max(m, Math.abs(A[i] - t[i] * S) / (t[i] * S));
      return m;
    };
    let cur = evaluate(W);
    if (!cur) throw new Error('a cell is empty');
    for (let it = 0; it < 100; it++) {
      const err = error(cur.A);
      if (err < tol) return Object.assign({ W, err }, cur);
      const S = sum(cur.A), col = new Float64Array(n);
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) col[j] += cur.J[i][j];
      // the Jacobian's rows sum to zero, so its last row gives way to the weights summing to zero,
      // which gives the same step as make_shards.py's least squares
      const M = Array.from({ length: n }, (_, i) => i < n - 1
        ? Float64Array.from({ length: n }, (_, j) => cur.J[i][j] - t[i] * col[j]) : new Float64Array(n).fill(1));
      const dW = gauss(M, Float64Array.from({ length: n }, (_, i) => i < n - 1 ? -(cur.A[i] - t[i] * S) : 0));
      let lam = 1, ok = false;
      while (lam > 1e-6) {
        const Wn = Array.from(W, (w, i) => w + lam * dW[i]), res = evaluate(Wn);
        if (res && res.A.every(a => a > 0) && error(res.A) < err) { W = Wn; cur = res; ok = true; break; }
        lam /= 2;
      }
      if (!ok) throw new Error('Newton step failed');
    }
    throw new Error('did not converge');
  }

  // ---------- Discs ----------

  function rng(seed) {                             // mulberry32
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function finish(d, s) {
    Object.assign(d, s);
    let a = 0;
    for (const V of d.shards.values()) a += area(V);
    d.shardShare = a / Math.PI;
    if (d.shardShare0 === undefined) d.shardShare0 = d.shardShare;
    d.radius = d.shardShare > 0 ? Math.sqrt(d.remaining * d.shardShare0 / d.shardShare) : 0;
    return d;
  }

  function make(shares, seed, o) {
    const rnd = rng(seed), mats = [], sizes = [];
    shares.forEach((s, m) => {                     // stratified draws, scaled to the share
      if (!(s > 0)) return;
      const n = Math.max(5, Math.round(s * o.nPieces));
      const a = Array.from({ length: n }, (_, i) => o.ratio ** ((i + rnd()) / n)), as = sum(a);
      a.forEach(v => { mats.push(m); sizes.push(v * s / as); });
    });
    const order = [...sizes.keys()];
    for (let i = order.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
    const groups = [];
    for (let k = 0; k < order.length;) {
      const x = rnd(), g = x < o.groupP[0] ? 1 : x < o.groupP[0] + o.groupP[1] ? 2 : 3;
      groups.push(order.slice(k, k + g)); k += g;
    }
    const usize = groups.map(g => sum(g.map(i => sizes[i]))), U = sum(usize);
    const r = usize.map(u => Math.sqrt(u / U * 0.86) * 0.92);
    const P = usize.map(() => [0, 0]), placed = [];
    for (const i of [...usize.keys()].sort((a, b) => usize[b] - usize[a])) {
      // random packing, biggest first, easing the clearance when a spot is hard to find
      for (let slack = 1; ; slack *= 0.95) {
        let found = false;
        for (let c = 0; c < 3000 && !found; c++) {
          const rho = (1 - 0.25 * r[i]) * Math.sqrt(rnd()), th = 2 * Math.PI * rnd();
          const x = rho * Math.cos(th), y = rho * Math.sin(th);
          if (placed.every(j => Math.hypot(x - P[j][0], y - P[j][1]) >= slack * (r[i] + r[j]))) { P[i] = [x, y]; found = true; }
        }
        if (found) break;
      }
      placed.push(i);
    }
    P.forEach((p, i) => {                          // sites off their circles' middles
      const th = 2 * Math.PI * rnd(), m = o.jitter * r[i] * Math.sqrt(rnd());
      p[0] += m * Math.cos(th); p[1] += m * Math.sin(th);
      const h = Math.hypot(p[0], p[1]);
      if (h > 0.995) { p[0] *= 0.995 / h; p[1] *= 0.995 / h; }
    });
    const t = usize.map(u => u / U);
    let res = solve(P, r.map(x => x * x), t, o.gap, null, null, null, o.tol);
    const angles = res.cells.map((V, u) => {       // crack angles that leave every shard wide
      let best = null, bestW = -1;
      for (let k = 0; k < 80; k++) {
        const th = rnd() * Math.PI, ang = [th, th + (45 + 90 * rnd()) * Math.PI / 180];
        const pcs = split(V, groups[u], sizes, ang, o.gap);
        const w = pcs.every(p => p.length) ? Math.min(...pcs.map(width)) : -1;
        if (w > bestW) { best = ang; bestW = w; }
        if (w >= 1.3 * o.minW) break;
      }
      return best;
    });
    res = solve(P, res.W, t, o.gap, groups, sizes, angles, o.tol);
    return finish({ seed, sizes, mats, gap0: o.gap },
                  { P, W: Array.from(res.W), groups, angles, remaining: 1, gap: o.gap, shards: res.shards });
  }

  function build(shares, opts = {}) {
    const o = Object.assign({}, DEFAULTS, opts), tot = sum(shares.filter(s => s > 0));
    CTOL = o.crackTol;
    for (let seed = o.seed; seed < o.seed + o.tries; seed++) {
      try { return make(shares.map(s => s > 0 ? s / tot : 0), seed, o); } catch (e) { /* next seed */ }
    }
    throw new Error(`no layout solved in ${o.tries} seeds from ${o.seed}`);
  }

  function remove(d, ids, opts = {}) {
    const o = Object.assign({}, DEFAULTS, opts);
    CTOL = o.crackTol;
    const P = d.P.map(p => p.slice()), W = Array.from(d.W), groups = d.groups.map(g => g.slice()), angles = d.angles.slice();
    let remaining = d.remaining;
    for (const k of [].concat(ids)) {
      const u = groups.findIndex(g => g.includes(k));
      if (u < 0) throw new Error(`no shard ${k} in the disc`);
      const g = groups[u].filter(x => x !== k);
      if (g.length) groups[u] = g;
      else { groups.splice(u, 1); angles.splice(u, 1); P.splice(u, 1); W.splice(u, 1); }
      remaining -= d.sizes[k];
    }
    if (!groups.length) return finish(d, { P, W, groups, angles, remaining: 0, shards: new Map() });
    const gap = opts.gap !== undefined ? opts.gap : d.gap0 / Math.sqrt(remaining);
    const usize = groups.map(g => sum(g.map(k => d.sizes[k]))), U = sum(usize), t = usize.map(x => x / U);
    let res;
    try {
      res = solve(P, W, t, gap, groups, d.sizes, angles, o.tol);
    } catch (e) {                                  // as make() does: the cells first, then the cracks
      const r0 = solve(P, W, t, gap, null, null, null, o.tol);
      res = solve(P, r0.W, t, gap, groups, d.sizes, angles, o.tol);
    }
    return finish(d, { P, W: Array.from(res.W), groups, angles, remaining, gap, shards: res.shards });
  }

  function fromState(st, opts = {}) {
    const o = Object.assign({}, DEFAULTS, opts);
    CTOL = o.crackTol;
    const P = st.P.map(p => p.slice()), groups = st.groups.map(g => g.slice()), angles = st.angles.map(a => a.slice());
    const usize = groups.map(g => sum(g.map(k => st.sizes[k]))), U = sum(usize);
    const res = solve(P, Array.from(st.W), usize.map(x => x / U), st.gap, groups, st.sizes, angles, o.tol);
    return finish({ sizes: st.sizes.slice(), mats: st.mats.slice(), gap0: st.gap },
                  { P, W: Array.from(res.W), groups, angles, remaining: U, gap: st.gap, shards: res.shards });
  }

  function measure(d) {
    const by = [];
    let all = 0;
    for (const [k, V] of d.shards) { const a = area(V); by[d.mats[k]] = (by[d.mats[k]] || 0) + a; all += a; }
    return { shares: Array.from(by, a => all > 0 ? 100 * (a || 0) / all : 0), slivers: 100 * (1 - all / Math.PI) };
  }

  return { build, remove, fromState, measure, area };
});
