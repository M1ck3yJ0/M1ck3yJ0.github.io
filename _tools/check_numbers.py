"""Check every figure a page states against the analysis repo's tables, in one command.

Usage:
    python3 -I _tools/check_numbers.py <page.html> <analysis repo> [d3.min.js] [--all]

Opens the page in headless Chromium, with reduced motion, and reads every figure a reader can
see: cards, section titles, the closer, every note (the collapsed notes included), table cells
(each cell apart), the head's descriptions, aria-labels and chart labels in every card's state,
20a's and 20b's text and charts for every country, and the game's text, and its numbers and
ending at the end of two routes, each taking the heaviest material first (recycling held at
2022's level, and at 70%). Axis ticks (three or more evenly spaced bare numbers at one x) are
a scale, not figures.

Each figure is matched to a named row by its place, unit and words as well as its value:
- its section (the id of the section or note it sits in) sets which rows it may come from
  (SCOPES): the EU's rows, the examples' (examples.csv) or both, and, for a country picked in an
  explorer or named in the figure's sentence, that country's rows. two_levers gives only the
  rows the page states (2022's recycling and 70%, at the page's replacement), the trend table
  only rates, ceilings, tonnes and shares;
- its unit must agree with the row's: a percentage, "times", tonnes and kilograms at any scale,
  square meters, kilometers, counts or a year;
- its value must round to the row's at the decimals the page shows (tables carry three, so a
  value on the rounding boundary fits either way), or else fit its hedge: "about" allows one or
  two significant figures, "more than" up to a quarter more, "less than" down to half, "nearly"
  a tenth less, and "a quarter of 1%" about 12% either way;
- among rows with different values that fit, the one whose name best fits the words around the
  figure wins (score below); a tie is reported as ambiguous.

_tools/check_numbers_by_hand.csv holds what the tables can't settle, keyed on a section (an
explorer's may add a country code, "explore-ring DE") and a figure, optionally with a word that
must be in the figure's clause (near): a row picks one among several that fit (reported as
matched, or as rounding if it no longer fits); no row means the figure is sourced and checked by
hand (quotes and figures from research.md, policy dates, the terrazzo note, page settings), with
its F number and a one-line reason.

Years from 2004 to three years past the data year, 2030 and 2050 are read as times, not
figures; other years need a row or an entry. References (sections, pages, figures, tables,
articles, report numbers, day-and-month dates) and spelled-out numbers aren't checked.

Prints only the problems: figures with no row and no entry (with any research.md entries that
hold the same number), ambiguous matches, rounding that disagrees with the nearest row, a row
that fits only by a rounded value and shares no word with the figure's paragraph, and entries
in the by-hand file the page no longer uses. --all also lists every match with its row.

For a page that loads D3 from cdn.jsdelivr.net, pass a local copy of the same version, e.g.
    npm install --prefix <dir> d3@7.9.0
then <dir>/node_modules/d3/dist/d3.min.js; without it the page loads D3 from the web.
Needs Python Playwright with Chromium.
"""
import asyncio
import csv
import functools
import glob
import http.server
import json
import math
import os
import re
import sys
import threading
import urllib.parse

from playwright.async_api import async_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SHOW_ALL = "--all" in sys.argv
PAGE, REPO = os.path.abspath(ARGS[0]), os.path.abspath(ARGS[1])
D3 = ARGS[2] if len(ARGS) > 2 else None
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "processed")
SOURCED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_numbers_by_hand.csv")
YEAR = max(re.search(r"(\d{4})", os.path.basename(p)).group(1)
           for p in glob.glob(os.path.join(OUT, "headline_numbers_*.csv")))
EU = "EU27_2020"

# Which rows each section may draw on, by its id: prefixes of row names for the EU's rows and for the
# rows of a country picked in an explorer or named in the figure's sentence. A section not listed is
# checked against every row, and named in the output.
EU_ROWS = ("headline.", "ceilings.", "two_levers.", "trend", "weight_mix.", "loop.", "waste_by_material.",
           "flows_by_material.", "levers.", "unrecycled_waste.", "materials.", "footprint.", "weight_vs_climate.", "data.")
COUNTRY_ROWS = ("headline.", "ceilings.", "trend", "weight_mix.", "loop.", "waste_by_material.", "flows_by_material.",
                "levers.", "unrecycled_waste.", "materials.")
EXAMPLES = ("examples.",)
SCOPES = {
    "head": (EU_ROWS + EXAMPLES, COUNTRY_ROWS),
    "sec-ring": (EU_ROWS, COUNTRY_ROWS), "sec-waterfall": (EU_ROWS, COUNTRY_ROWS), "sec-ribbon": (EU_ROWS, COUNTRY_ROWS),
    "sec-zin": (EU_ROWS + EXAMPLES, ()), "sec-ikea": (EXAMPLES, ()),
    "explore-ring": (("headline.step_", "headline.target", "headline.eea_", "headline.countries_", "headline.eu_countries",
                      "ceilings.EU.waste_treated_per_consumption"),
                     ("headline.", "ceilings.", "materials.", "weight_mix.", "trend")),
    "explore-waterfall": (("headline.countries_", "headline.eu_countries", "headline.target", "headline.eea_"),
                          ("headline.", "ceilings.", "trend", "waste_by_material.", "unrecycled_waste.")),
    "game": (EU_ROWS, ()), "sec-closer": (EU_ROWS + EXAMPLES, COUNTRY_ROWS),
    "notes-method": (EU_ROWS, COUNTRY_ROWS), "notes-ring": (EU_ROWS, COUNTRY_ROWS),
    "notes-waterfall": (EU_ROWS, COUNTRY_ROWS), "notes-ribbon": (EU_ROWS, COUNTRY_ROWS),
    "notes-zin": (EU_ROWS + EXAMPLES, ()), "notes-ikea": (EXAMPLES, ()),
    "notes-explore": (EU_ROWS, COUNTRY_ROWS), "notes-explore-waterfall": (EU_ROWS, COUNTRY_ROWS), "notes-game": (EU_ROWS, ()),
    "notes-closer": (EU_ROWS + EXAMPLES, COUNTRY_ROWS), "notes-drawings": ((), ()), "notes": (EU_ROWS, COUNTRY_ROWS), "method": (EU_ROWS, COUNTRY_ROWS),
}
CONSTANTS = {100.0: "a whole (100%)"}
# Sections whose figures are the data year's unless a year is named: a row of the trend tables
# fits only if one of its years other than the data year is in the figure's clause or the one before
STRICT_YEARS = {"explore-ring"}


# ---------- The page, as a reader sees it ----------

STATIC_JS = r"""() => {
  const out = [], counts = {};
  const BLOCK = 'title,h1,h2,h3,h4,p,li,dt,dd,tr,caption,summary,button,figcaption,label,blockquote';
  const secOf = el => { const s = el.closest('section[id], details[id]'); return s ? s.id : (el.closest('head') ? 'head' : 'page'); };
  const where = el => {
    const sec = secOf(el), card = el.closest('.card[data-state]');
    if (!card) return sec;
    const cards = [...document.querySelectorAll('.card[data-state]')].filter(c => secOf(c) === sec);
    return sec + ' card ' + (cards.indexOf(card) + 1) + ' (' + card.dataset.state + ')';
  };
  const push = (el, text, label, ctx) => {
    text = (text || '').replace(/\s+/g, ' ').trim();
    if (!/\d/.test(text)) return;
    const w = where(el), k = w + ' ' + label;
    counts[k] = (counts[k] || 0) + 1;
    out.push({ section: secOf(el), where: k + counts[k], text: text, ctx: (ctx || '').replace(/\s+/g, ' ').trim() });
  };
  document.querySelectorAll(BLOCK).forEach(el => {
    if (el.closest('svg, script, style, select, template, .game-end, .explore-text')) return;
    if (el.querySelector(BLOCK)) return;
    let ctx = '';
    if (el.tagName === 'TR') {
      const t = el.closest('table');
      ctx = [t.querySelector('caption'), t.querySelector('thead')].filter(Boolean).map(x => x.textContent).join(' ');
    }
    const text = el.tagName === 'TR' ? [...el.children].map(c => c.textContent).join(' | ') : el.textContent;
    push(el, text, el.tagName.toLowerCase(), ctx);
  });
  document.querySelectorAll('meta[name="description"], meta[property="og:description"], meta[property="og:title"]')
    .forEach(m => out.push({ section: 'head', where: 'head ' + (m.getAttribute('name') || m.getAttribute('property')), text: m.content, ctx: '' }));
  document.querySelectorAll('[aria-label]').forEach(el => {
    if (el.closest('svg') && el.tagName !== 'svg') return;
    if (el.closest('#explore-ring, #explore-waterfall, .burst')) return;   // read with their charts
    push(el, el.getAttribute('aria-label'), 'aria-label (' + (el.id || el.className.baseVal || el.className || el.tagName) + ')');
  });
  return out;
}"""

CHART_JS = r"""(sel) => {
  // A chart's labels and aria-label. Axis ticks, three or more bare numbers at one x and anchor,
  // evenly spaced, are left out: they are a scale, not figures.
  const fig = document.querySelector(sel);
  if (!fig) return [];
  const all = [...fig.querySelectorAll('svg text')].map(t => ({
    text: [...t.childNodes].map(n => n.textContent).join(' ').replace(/\s+/g, ' ').trim(),
    key: t.getAttribute('x') + '|' + (t.getAttribute('text-anchor') || '') + '|' + (t.parentNode.getAttribute('transform') || '')
  }));
  const bare = /^[-\u2212]?\d+(\.\d+)?\s?%?$/;
  const groups = {};
  all.filter(a => bare.test(a.text)).forEach(a => (groups[a.key] = groups[a.key] || []).push(a));
  const ticks = new Set();
  Object.values(groups).forEach(g => {
    const v = g.map(a => parseFloat(a.text.replace('\u2212', '-'))).sort((x, y) => x - y);
    const d = v.slice(1).map((x, i) => +(x - v[i]).toFixed(6));
    if (v.length >= 3 && d.every(x => x === d[0])) g.forEach(a => ticks.add(a));
  });
  const texts = all.filter(a => !ticks.has(a)).map(a => a.text);
  const svg = fig.querySelector('svg');
  if (svg && svg.getAttribute('aria-label')) texts.push(svg.getAttribute('aria-label'));
  return texts.filter(t => /\d/.test(t));
}"""

CARDS_JS = r"""() => [...document.querySelectorAll('.card[data-state]')].map(c => {
  const b = c.closest('.burst');
  return { state: c.dataset.state, section: b ? b.id : '', fig: b && b.querySelector('figure') ? '#' + b.querySelector('figure').id : '' };
})"""

EXPLORER_JS = r"""async ([sec, code]) => {
  const box = document.getElementById(sec), sel = box.querySelector('select');
  if (code === null) return [...sel.options].map(o => o.value);
  sel.value = code;
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  let last = '', same = 0;
  for (let k = 0; k < 60 && same < 3; k++) {                 // until the text and labels settle
    await new Promise(r => setTimeout(r, 80));
    const now = box.textContent + [...box.querySelectorAll('svg text')].map(t => t.textContent).join('|');
    same = now === last ? same + 1 : 0;
    last = now;
  }
  const texts = [...box.querySelectorAll('.explore-text p')].map(p => p.textContent);
  return texts;
}"""

GAME_JS = r"""async (recycle) => {
  const G = window.FFC.game;
  G.reset();
  if (recycle) G.recycle(recycle);
  for (const m of [0, 1, 2, 3]) {
    for (let k = 0; k < 40 && !G.state().closed; k++) {
      const before = G.state().weight;
      G.tap(m);
      if (G.state().weight === before) break;
    }
  }
  await new Promise(r => setTimeout(r, 400));
  const box = document.getElementById('game');
  return [...box.querySelectorAll('.game-end p, .game-nums div')].map(e =>
    e.children.length ? [...e.children].map(c => c.textContent).join(' ') : e.textContent);
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


async def read_page():
    """Every place on the page that states a figure: (section, where, text, context, country)."""
    serve_root = os.path.commonpath([ROOT, PAGE]) if PAGE.startswith(ROOT) else os.path.dirname(PAGE)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=serve_root))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    url = base + urllib.parse.quote(os.path.relpath(PAGE, serve_root))
    places, errors = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800}, reduced_motion="reduce")

        async def route(r):
            u = r.request.url
            if D3 and "cdn.jsdelivr.net/npm/d3" in u:
                await r.fulfill(path=D3, content_type="application/javascript")
            elif u.startswith(base) or "cdn.jsdelivr.net" in u:
                await r.continue_()
            else:
                await r.abort()

        await ctx.route("**/*", route)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(url)
        await page.wait_for_timeout(800)
        for s in await page.evaluate(STATIC_JS):
            places.append((s["section"], s["where"], s["text"], s["ctx"], None))

        # The pinned charts, in every card's state
        cards = await page.evaluate(CARDS_JS)
        seen = set()
        for i, c in enumerate(cards):
            await page.evaluate("(i) => window.FFC.show(i, 0)", i)
            await page.wait_for_timeout(120)
            texts = await page.evaluate(CHART_JS, c["fig"])
            for t in texts:
                if (c["fig"], t) not in seen:
                    seen.add((c["fig"], t))
                    places.append((c["section"], f"{c['section']} chart ({c['state']})", t, " ".join(texts), None))

        # The explorers, country by country
        for sec, fig in [("explore-ring", "#explore-ring-chart"), ("explore-waterfall", "#explore-waterfall-chart")]:
            await page.evaluate("(s) => { const b = document.getElementById(s), d = b.querySelector('details');"
                                " if (d) d.open = true; b.scrollIntoView(); }", sec)
            await page.wait_for_timeout(400)
            for code in await page.evaluate(EXPLORER_JS, [sec, None]):
                for k, t in enumerate(await page.evaluate(EXPLORER_JS, [sec, code])):
                    places.append((sec, f"{sec} {code} text p{k + 1}", t, "", code))
                texts = await page.evaluate(CHART_JS, fig)
                for t in texts:
                    places.append((sec, f"{sec} {code} chart", t, " ".join(texts), code))

        # The game, at the end of two routes
        await page.evaluate("() => document.getElementById('game').scrollIntoView()")
        await page.wait_for_timeout(400)
        for name, rec in [("recycling held", 0), ("70% recycled", 70)]:
            for k, t in enumerate(await page.evaluate(GAME_JS, rec)):
                places.append(("game", f"game, {name}, heaviest first, end {k + 1}", t, "", None))
        await browser.close()
    server.shutdown()
    return places, errors


# ---------- The rows ----------

def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def read(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def unit_of(name, unit=""):
    """A row's unit class and its factor to tonnes, from its unit or its column name."""
    u = (unit or "").strip()
    if u.startswith("%") or u.startswith("change in rate") or (not u and name.endswith(("_pct", "_pts"))):
        return "pct", 1
    if u in ("times",) or (not u and ("multiple" in name or name.endswith("_times"))):
        return "times", 1
    if u == "year":
        return "year", 1
    if u.startswith("Mt") or (not u and name.endswith("_mt")):
        return "mass", 1e6
    if u.startswith("kt") or (not u and name.endswith("_kt")):
        return "mass", 1e3
    if u.startswith("kg"):
        return "mass", 1e-3
    if u.startswith("t") and not u.startswith("times"):
        return "mass", 1
    if u.startswith("m2"):
        return "area", 1
    if u.startswith("km"):
        return "km", 1
    return "count", 1


class Row:
    __slots__ = ("name", "value", "cls", "factor", "geo", "group", "words")

    def __init__(self, name, value, cls, factor, geo, group):
        self.name, self.value, self.cls, self.factor, self.geo, self.group = name, value, cls, factor, geo, group
        self.words = stems(name.replace("_", " ").replace(".", " ")) | ({geo.lower()} if geo else set())
        if name.startswith(("headline.", "ceilings.", "two_levers.", "weight_mix.", "loop.", "waste_by_material.",
                            "flows_by_material.", "levers.", "materials.", "unrecycled_waste.")):
            self.words.add(YEAR)                           # tables for the data year


STOP = set("the a an of in on at to and or for by from with as is are was were it its that this be not than per pct "
           "eu27 headline ceilings levers trend steps drivers mix table".split())
SYN = {"k05": "half", "k0": "none", "k1": "whole", "dmc": "material use", "consumption": "material use",
       "consumed": "material use", "consumes": "material use", "used": "use", "using": "use", "uses": "use",
       "pts": "", "kt": "", "mt": "", "everything": "every", "recycled": "recyc circu",
       "recycling": "recyc circu", "recycles": "recyc circu", "recycle": "recyc circu", "circular": "circu recyc", "go": "gone", "went": "gone",
       "fall": "change", "fell": "change", "rise": "change", "rose": "change", "drop": "change", "outside": "impor",
       "removed": "less cut", "removes": "less cut", "remove": "less cut"}


def stems(text):
    """A text's words, cut to their first five letters, with plural and past endings and stop words dropped."""
    out = set()
    for w in re.findall(r"[a-z]+\d*|\d+", text.lower()):
        for x in SYN.get(w, w).split():
            if len(x) > 4 and not x[-1].isdigit():
                x = re.sub(r"(ing|ed|es|s)$", "", x)
            if x not in STOP and len(x) > 1:
                out.add(x[:5])
    return out


TREND_KEEP = re.compile(r"^(rate_pct|consumption_kt|waste_\w+_kt|soil_rock_\w+_kt|circular_use_kt|ceiling\w*|"
                        r"rate_with_backfilling_pct|waste_treated_per_consumption_pct|share_\w+)$")


def load_rows():
    """Every named row, tagged with its country (geo) and group ("eu" or "examples")."""
    rows, names = [], {}
    add = lambda *a: rows.append(Row(*a))
    codes = {r["geo"].lower(): r["geo"] for r in read(f"ceilings_{YEAR}.csv") if r["geo"] != EU}
    codes["ireland"] = "IE"
    for r in read(f"headline_numbers_{YEAR}.csv"):
        v = num(r["value"])
        if v is None:
            continue
        geo = codes.get(r["metric"].split("_")[0])
        cls, f = unit_of(r["metric"], r["unit"])
        add(f"headline.{r['metric']}", v, cls, f, geo, "eu")
    for r in read("examples.csv"):
        v = num(r["value"])
        if v is not None:
            cls, f = unit_of(r["metric"], r["unit"])
            add(f"examples.{r['example']}.{r['metric']}", v, cls, f, None, "examples")
    shares = [r["recycled_share_pct"] for r in read(f"two_levers_{YEAR}.csv")]
    k_key = {0.5: "k05", 0.0: "k0", 1.0: "k1"}[next(float(r["value"]) for r in read(f"headline_numbers_{YEAR}.csv")
                                                    if r["metric"] == "replacement")]
    for r in read(f"two_levers_{YEAR}.csv"):            # the rows the page states: 2022's recycling and 70%, at its replacement
        if r["recycled_share_pct"] not in (shares[0], "70.0") or r["replacement"] != k_key:
            continue
        key = f"two_levers.{r['replacement']}.{float(r['recycled_share_pct']):g}"
        for k, v in r.items():
            if k not in ("replacement",) and num(v) is not None:
                cls, f = unit_of(k)
                add(f"{key}.{k}", num(v), cls, f, None, "eu")
    for r in read(f"weight_vs_climate_{YEAR}.csv"):
        for k in ("share_of_weight_pct", "share_of_climate_impact_pct"):
            add(f"weight_vs_climate.{r['material_group']}.{k}", num(r[k]), "pct", 1, None, "eu")
        add(f"weight_vs_climate.{r['material_group']}.impact_per_weight", num(r["impact_per_weight"]), "times", 1, None, "eu")
        add(f"weight_vs_climate.{r['material_group']}.impact_per_tonne_vs_minerals",
            num(r["impact_per_tonne_vs_minerals"]), "times", 1, None, "eu")
    for r in read(f"footprint_{YEAR}.csv"):
        for k, v in r.items():
            if k.endswith("_pct"):
                add(f"footprint.{r['group']}.{k}", num(v), "pct", 1, None, "eu")
    # Tables with a row per country (and year, step or material)
    per_geo = [(f"ceilings_{YEAR}.csv", ()), ("trend.csv", ("year",)), ("trend_steps.csv", ("from_year", "to_year")),
               ("trend_drivers.csv", ("from_year", "to_year")), (f"weight_mix_{YEAR}.csv", ()),
               (f"loop_{YEAR}.csv", ()), (f"waste_by_material_{YEAR}.csv", ("material",)),
               (f"flows_by_material_{YEAR}.csv", ("material",)), (f"levers_{YEAR}.csv", ()),
               (f"unrecycled_waste_{YEAR}.csv", ("kind",)), (f"materials_{YEAR}.csv", ())]
    for name, keys in per_geo:
        table = name.split("_20")[0].replace(".csv", "")
        for r in read(name):
            g = r["geo"]
            names[g] = r["country"]
            tag = ".".join([table, "EU" if g == EU else g] + [r[k] for k in keys])
            for k, v in r.items():
                x = num(v)
                if x is None or k in keys or k in ("geo", "country") or k.endswith(("_source", "_flag")):
                    continue
                if table == "trend" and not TREND_KEEP.match(k):   # scenarios are ceilings' (the data year)
                    continue
                if "ireland" in k:                    # Ireland's own target isn't on the page
                    continue
                if table == "materials":
                    add(f"{tag}.{k}_kg_a_day", x, "mass", 1e-3, None if g == EU else g, "eu")
                    add(f"{tag}.{k}_t_a_year", x * 365 / 1000, "mass", 1, None if g == EU else g, "eu")
                    continue
                cls, f = unit_of(k)
                add(f"{tag}.{k}", x, cls, f, None if g == EU else g, "eu")
            if table == "trend_steps":            # "x times as much", as the cards say a change
                for k in ("consumption_change_pct", "circular_use_change_pct"):
                    if num(r[k]) is not None:
                        add(f"{tag}.{k[:-11]}_multiple", 1 + num(r[k]) / 100, "times", 1, None if g == EU else g, "eu")
            if table == "trend_steps":            # the rate the step would have reached had circular use held
                rr, c = num(r["rate_from_pct"]), num(r["consumption_change_pct"])
                if rr is not None and c is not None:
                    rr /= 100
                    add(f"{tag}.rate_had_circular_use_held_pct", 100 * rr / ((1 - rr) * (1 + c / 100) + rr), "pct", 1,
                        None if g == EU else g, "eu")
    # Waste over all four material groups (env_wassd's totals)
    sums = {}
    for r in read(f"waste_by_material_{YEAR}.csv"):
        for k in ("treated_kt", "recycled_kt", "imported_for_recycling_kt", "exported_for_recycling_kt"):
            if num(r[k]) is not None:
                sums[(r["geo"], k)] = sums.get((r["geo"], k), 0) + num(r[k])
    for (g, k), v in sums.items():
        add(f"waste_by_material.{'EU' if g == EU else g}.all_groups.{k}", v, "mass", 1e3, None if g == EU else g, "eu")
    # 20a's arithmetic on each country's figures, as the page does it
    for r in read(f"ceilings_{YEAR}.csv"):
        g = None if r["geo"] == EU else r["geo"]
        mat = {m["geo"]: num(m["total"]) for m in read(f"materials_{YEAR}.csv")}.get(r["geo"])
        share = num(r["share_recycled_pct"])
        if share:
            add(f"ceilings.{r['geo']}.recycling_multiple_to_70pct", 70 / share, "times", 1, g, "eu")
        for key in ("k0", "k05", "k1"):
            rep = num(r[f"replaced_by_recycling_for_eu_target_70pct_recycled_{key}_pct"])
            gone = num(r[f"gone_without_for_eu_target_70pct_recycled_{key}_pct"])
            if rep is None or gone is None or mat is None:
                continue
            tpp = mat * 365 / 1000
            cut = max(0, rep) + max(0, gone)
            add(f"ceilings.{r['geo']}.less_new_material_at_70pct_{key}_t_per_person", tpp * cut / 100, "mass", 1, g, "eu")
            add(f"ceilings.{r['geo']}.replaced_at_70pct_{key}_t_per_person", tpp * max(0, rep) / 100, "mass", 1, g, "eu")
    # The page's data file: the disc's shares and imports
    js = open(os.path.join(os.path.dirname(PAGE), "far_from_full_circle_data.js"), encoding="utf-8").read()
    data = json.loads(js[js.index("{"):js.rindex("}") + 1])
    for k, v in data["center_shards"]["shares_pct"].items():
        add(f"data.center_shards.{k}_share_pct", v, "pct", 1, None, "eu")
    add("data.imports.imports_kt", data["imports"]["imports_kt"], "mass", 1e3, None, "eu")
    for m in data["imports"]["materials"]:
        for k, v in m.items():
            if num(v) is not None:
                cls, f = unit_of(k)
                add(f"data.imports.{m['material_group']}.{k}", num(v), cls, f, None, "eu")
    return rows, names


# ---------- The figures on the page ----------

FIG = re.compile(r"(?<![\w.\-/])(?<!\w\()(?<!\d,)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(s?)(?![\w/]|\(\d|-\d|\.\d)")
UNIT = re.compile(
    r"\s?(?P<u>%|percent\b|×|x\b|\s?times\b|(?:\s?(?P<mul>thousand|million|billion))?\s?(?P<w>tonnes?|t\b|Mt\b|Gt\b|kt\b|"
    r"kilograms?|kilometers?|kilos?|kg\b|square meters|m²|m2\b|km\b)|\s?(?P<mul2>million|billion)\b)")
MULT = {"thousand": 1e3, "million": 1e6, "billion": 1e9}
WEIGHT = {"tonne": 1, "tonnes": 1, "t": 1, "mt": 1e6, "gt": 1e9, "kt": 1e3, "kilogram": 1e-3, "kilograms": 1e-3,
          "kilo": 1e-3, "kilos": 1e-3, "kg": 1e-3}
REF = re.compile(r"\b(?:sections?|figures?|fig\.|tables?|pages?|pp?\.|articles?|annex(?:es)?|paragraphs?|books?|"
                 r"chapters?|panels?|cards?|modules?|points?|steps?|regulation|directive|decision|document|report|"
                 r"edition|no\.|PE|EUR|ISBN|COM|SWD|indicators?|objectives?|priority)\s*(?:\(\w+\)\s*)?"
                 r"\d[\w.\-/()]*(?:\s*(?:,|and|to|or)\s*\d[\w.\-/()]*)*|\b(?:January|February|March|April|May|June|July|"
                 r"August|September|October|November|December)\s+\d{1,2}\b", re.I)
FRACTION = re.compile(r"\b(?:(a|an|one|two|three|four|nine)\s+(half|third|quarter|fifth|eighth|tenth)s?|(half))\s+of\s+$")
FRAC = {"half": 1 / 2, "third": 1 / 3, "quarter": 1 / 4, "fifth": 1 / 5, "eighth": 1 / 8, "tenth": 1 / 10}
COUNT = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "nine": 9}
HEDGE = re.compile(r"\b(about|roughly|around|approximately|some|close to|nearly|almost|just under|just over|"
                   r"more than|over|at least|above|less than|under|below|fewer than|up to)\s+(?:a\s+|an\s+)?$", re.I)
JOIN = re.compile(r"^\s*(?:to|and|or|-|of(?:\s+(?:its|those|the|their|his|her))?)\s+$")


class Figure:
    __slots__ = ("token", "value", "dec", "place", "cls", "factor", "hedge", "start", "end", "year", "frac")


def figures(text):
    """Every figure in a text, with its unit, decimals and hedge, skipping references."""
    refs = [m.span() for m in REF.finditer(text)]
    out = []
    for m in FIG.finditer(text):
        if any(a <= m.start() < b for a, b in refs):
            continue
        if re.search(r"(?:COM|SWD)\s*\(\d{4}\)\s*$", text[:m.start()]) or re.match(r"(?:st|nd|rd|th)\b", text[m.end():]):
            continue
        f = Figure()
        digits = m.group(1).replace(",", "")
        f.token, f.start, f.end = m.group(0), m.start(), m.end()
        f.value = float(digits + (m.group(2) or ""))
        f.dec = len(m.group(2)) - 1 if m.group(2) else 0
        f.place, f.frac = 0, False
        if not m.group(2) and f.value >= 1000 and "," in m.group(1):
            z = len(digits) - len(digits.rstrip("0"))
            f.place = min(z, len(digits) - 1)
        f.cls, f.factor, f.year = "count", 1, False
        u = UNIT.match(text, m.end())
        if m.group(3):                              # "1920s"
            f.cls, f.year = "year", True
        elif u:
            f.end = u.end()
            f.token = text[m.start():u.end()].strip()
            g = u.group("u").strip().lower()
            if g in ("%", "percent"):
                f.cls = "pct"
            elif g in ("×", "x", "times"):
                f.cls = "times"
            elif u.group("w"):
                w = u.group("w").lower()
                if w in ("square meters", "m²", "m2"):
                    f.cls = "area"
                elif w in ("km", "kilometer", "kilometers"):
                    f.cls = "km"
                else:
                    f.cls, f.factor = "mass", WEIGHT[w] * MULT.get((u.group("mul") or "").lower(), 1)
            else:
                f.cls, f.factor = "big", MULT[u.group("mul2").lower()]
        before = text[max(0, m.start() - 40):m.start()]
        fr = FRACTION.search(before)
        if fr:
            k = FRAC[fr.group(2) or "half"] * COUNT.get(fr.group(1) or "a", 1)
            f.value *= k
            f.dec, f.frac = max(f.dec, 2), True
            before = before[:fr.start()]
        h = HEDGE.search(before)
        f.hedge = h.group(1).lower() if h else ("about" if fr else None)
        if f.cls == "count" and not f.dec and 1000 <= f.value <= 2100 and "," not in m.group(1):
            f.cls, f.year = "year", True
        out.append(f)
    # a bare number joined to the next figure ("5 to 15%", "17.2 to 33.9 million tonnes") takes its unit
    for a, b in zip(out, out[1:]):
        if a.cls == "count" and b.cls not in ("count", "year") and JOIN.match(text[a.end:b.start]):
            a.cls, a.factor = b.cls, b.factor
    return out


def near_words(text, f):
    """The words right around a figure: three before it and four after, within its clause."""
    s = sentence(text, f)
    a, b = s.find(f.token), s.find(f.token) + len(f.token)
    left = re.findall(r"[\w']+", s[:max(0, a)])[-3:]
    right = re.findall(r"[\w']+", s[b:])[:4]
    return " ".join(left + right)


def sentence(text, f, before=0):
    """The sentence a figure sits in, and before= sentences ahead of it."""
    a = f.start
    for _ in range(before + 1):
        a = max([text.rfind(s, 0, a) for s in (". ", "; ", ": ")] + [-2])
    a += 2
    b = min([x for x in (text.find(s, f.end) for s in (". ", "; ", ": ")) if x >= 0] or [len(text)])
    return text[a:b + 1]


# ---------- Matching ----------

def in_unit(row, f):
    """A row's value in the page figure's unit."""
    if f.cls == "mass" or (f.cls == "big" and row.cls == "mass"):
        return row.value * row.factor / f.factor
    if f.cls == "big":
        return row.value / f.factor
    return row.value


def fits(v, f, loose=False, hedged=True):
    """Whether a row's value v gives the figure: rounded at the page's decimals (tables carry three,
    so a value on the rounding boundary fits either way), or within its hedge."""
    v = abs(v)
    x = f.value
    q = 10 ** f.place if f.place else 10 ** -f.dec
    if abs(v - x) <= q / 2 + 5e-4 + 1e-9 * x:
        return True
    if f.frac and abs(v - x) <= 0.12 * x:
        return True
    if not hedged or (not f.hedge and not loose):
        return False
    h = f.hedge or "about"
    if h in ("about", "roughly", "around", "approximately", "some", "close to") or loose:
        for s in (1, 2):
            if v > 0 and abs(round(v, s - 1 - int(math.floor(math.log10(v)))) - x) < 1e-9:
                return True
        return loose and abs(v - x) <= 0.1 * x
    if h in ("nearly", "almost", "just under"):
        return 0.9 * x <= v <= x
    if h in ("more than", "over", "at least", "above", "just over"):
        return x <= v <= 1.25 * x
    if h in ("less than", "under", "below", "fewer than", "up to"):
        return 0.5 * x <= v <= x
    return False


def classes(f):
    if f.cls == "big":
        return ("mass", "count")
    if f.cls == "count":
        return ("count", "mass", "area", "km", "times")
    if f.cls == "year":
        return ("year",)
    return (f.cls,)


DERIVED = re.compile(r"had_circular_use_held|_multiple$|all_groups|_t_per_person|_to_70pct$|_t_a_year")


def score(r, words):
    """How well a row's name fits the figure's words: each word it shares counts 1 in the figure's own
    clause (2 within a few words of it), a half in the one before and a quarter elsewhere in its
    paragraph, table or chart. The rows
    meant for the page's cards (headline_numbers, examples) count 1.5 more in a card, an explorer or the
    closer and a half more elsewhere; rows the check works out itself 1.5 less; rows of the same record as another figure in the clause 1 more; an explorer's own
    country's rows a half more; and each year in a row's name that isn't the data year and isn't named
    nearby, a half less."""
    s = sum(x for w in r.words for x in [words.get(w, 0)] if isinstance(x, (int, float)))
    if r.name.startswith(("headline.", "examples.")):
        s += words.get("", 0.5)
    if DERIVED.search(r.name):
        s -= 1.5
    if r.geo and "@" + r.geo in words:
        s += words["@" + r.geo]
    if r.name.rsplit(".", 1)[0] in words.get("~", ()) and not DERIVED.search(r.name):
        s += 1
    if "=" in words and abs(abs(r.value) * r.factor - words["="]) < 1e-9 * max(1, words["="]):
        s += 0.5                                       # equal to the figure, not just rounding to it
    years = [w for w in r.words if re.fullmatch(r"(19|20)\d\d", w) and w != YEAR]
    s -= 0.5 * sum(y not in words for y in years)
    return s


def match(f, words, pool):
    """The rows a figure fits: matched (one figure), ambiguous (several) or rounding (none, but near).
    Rows that round to it come before rows within its hedge. The rate a step would have reached had
    circular use held fits only a clause that says "held"."""
    pool = [r for r in pool if r.cls in classes(f) and ("held" in r.name) <= (words.get("held", 0) >= 1)]
    cands = [r for r in pool if fits(in_unit(r, f), f, hedged=False)] or [r for r in pool if fits(in_unit(r, f), f)]
    if not cands and f.cls == "year":
        return "unmatched", []
    if not cands:
        near = [r for r in pool if fits(in_unit(r, f), f, loose=True) and score(r, words) > 0]
        near.sort(key=lambda r: (-score(r, words), abs(abs(in_unit(r, f)) - f.value)))
        return ("rounding", near[:1]) if near else ("unmatched", [])
    groups = []
    for r in sorted(cands, key=lambda r: abs(r.value) * r.factor):   # rows within the tables' rounding state one figure
        v = abs(r.value) * r.factor
        if groups and v - groups[-1][0] <= 2e-3 * r.factor + 1e-9 * v:
            groups[-1][1].append(r)
        else:
            groups.append([v, [r]])
    groups = {v: g for v, g in groups}
    best = sorted(((max(score(r, words) for r in g), g) for g in groups.values()), key=lambda t: -t[0])
    if len(best) == 1 or best[0][0] > best[1][0]:
        return "matched", sorted(best[0][1], key=lambda r: -score(r, words))[:1]
    top = [g for s, g in best if s == best[0][0]]
    return "ambiguous", [max(g, key=lambda r: score(r, words)) for g in top][:4]


def load_sourced():
    out = []
    if not os.path.exists(SOURCED):
        return out
    with open(SOURCED, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            fs = figures(r["figure"])
            if fs:
                out.append(dict(r, fig=fs[0], used=0))
    return out


def register():
    """research.md's figures, by F number, as hints for unmatched figures."""
    out = []
    for line in open(os.path.join(REPO, "research.md"), encoding="utf-8"):
        m = re.match(r"- \*\*(F\d+)\.\*\*", line)
        if m:
            out += [(m.group(1), f) for f in figures(line)]
    return out


def main():
    places, errors = asyncio.run(read_page())
    rows, names = load_rows()
    eu = [r for r in rows if r.geo is None and r.group == "eu"]
    ex = [r for r in rows if r.group == "examples"]
    by_geo = {}
    for r in rows:
        if r.geo:
            by_geo.setdefault(r.geo, []).append(r)
    name_of = {re.compile(r"\b" + re.escape(n) + r"\b"): g for g, n in names.items() if g != EU}
    sourced, reg = load_sourced(), register()
    by_name = {r.name: r for r in rows}
    problems, matched, dates, unscoped = [], [], 0, set()
    n_fig = n_src = 0
    seen = set()
    for section, where, text, ctx, code in places:
        scope = SCOPES.get(section)
        if scope is None:
            scope = (EU_ROWS + EXAMPLES, COUNTRY_ROWS)
            unscoped.add(section)
        base = [r for r in eu + ex if r.name.startswith(scope[0])]
        for f in figures(text):
            if f.value == 0:
                continue
            key = (where.split(" chart")[0] if " chart" in where else where, f.token, round(f.value, 6), sentence(text, f),
                   text.count(f.token, 0, f.start))
            if key in seen:
                continue
            seen.add(key)
            s = sentence(text, f)
            s_at = text.find(s)
            if f.year and (2004 <= f.value <= int(YEAR) + 3 or f.value in (2030, 2050)):
                dates += 1
                continue
            n_fig += 1
            if f.cls == "pct" and f.value in CONSTANTS and not f.dec:
                continue
            geos = {code} if code else set()
            geos |= {g for rx, g in name_of.items() if rx.search(s)}
            pool = base + [r for g in geos for r in by_geo.get(g, []) if r.name.startswith(scope[1])]
            if section in STRICT_YEARS:
                named = set(re.findall(r"\b(?:19|20)\d\d\b", sentence(text, f, 1)))
                pool = [r for r in pool if not r.name.startswith("trend")
                        or named & {w for w in r.words if re.fullmatch(r"(19|20)\d\d", w)} - {YEAR}]
            words = dict.fromkeys(stems(text + " " + ctx), 0.25)
            words.update(dict.fromkeys(stems(sentence(text, f, 1)), 0.5))
            words.update(dict.fromkeys(stems(s) | {g.lower() for g in geos}, 1))
            words.update(dict.fromkeys(stems(near_words(text, f)), 2))
            words[""] = 1.5 if section.startswith(("sec-", "head", "game", "explore-")) else 0.5   # cards draw on the card rows
            if code:
                words["@" + code] = 0.5                 # an explorer's own country first
            ok = [e for e in sourced if e["section"] in (section, f"{section} {code}") and e["fig"].cls in classes(f)
                  and abs(e["fig"].value - f.value) < 1e-9 and (not e["near"] or e["near"].lower() in s.lower())]
            for e in ok:
                e["used"] += 1
            pin = [e for e in ok if e["row"]]
            if ok and not pin:
                n_src += 1
                continue
            if pin:                                     # a row chosen by hand among several that fit
                r = by_name.get(pin[0]["row"])
                kind, hits = ("matched", [r]) if r and fits(in_unit(r, f), f) else ("rounding", [r] if r else [])
            else:
                words["="] = f.value * f.factor if f.cls in ("mass", "big") else f.value
                # rows of the same record as the clause's other figures ("5.8% to 3.0%, recycled 42% less")
                words["~"] = {r.name.rsplit(".", 1)[0] for g in figures(s) if g.start != f.start - s_at and g.value
                              for r in pool if r.cls in classes(g) and fits(in_unit(r, g), g, hedged=False)}
                kind, hits = match(f, words, pool)
            ctx_txt = " ".join(text[max(0, f.start - 60):f.end + 40].split())
            if kind == "matched" and not pin and not hits[0].words & {w for w, x in words.items() if isinstance(x, (int, float)) and 0 < x <= 2} \
                    and abs(abs(in_unit(hits[0], f)) - f.value) > 1e-9 * max(1, f.value):
                kind = "weak"
            if kind == "matched":
                matched.append((where, f.token, hits[0]))
            else:
                hint = sorted({fn for fn, g in reg if g.cls in classes(f) and fits(g.value, f)},
                              key=lambda x: int(x[1:])) if kind == "unmatched" else []
                problems.append((kind, where, f.token, hits, ctx_txt, hint))

    print(f"check_numbers: {os.path.relpath(PAGE)} against {os.path.basename(REPO)}'s {YEAR} tables")
    print(f"{n_fig} figures in {len(places)} places: {len(matched)} matched a row, {n_src} sourced by hand "
          f"({os.path.basename(SOURCED)}); {dates} dates read as times, not checked.")
    for s in sorted(unscoped):
        print(f"Note: section {s} has no scope in SCOPES; checked against every row.")
    for e in errors:
        print(f"Page error: {e}")
    unused = [e for e in sourced if not e["used"]]
    if not problems and not unused:
        print("No problems.")
    labels = {"unmatched": "No row and no entry", "ambiguous": "Ambiguous: several rows fit",
              "rounding": "Rounding disagrees with the nearest row",
              "weak": "Only a rounded value fits, and the row shares no word with the figure's paragraph"}
    for kind in ("unmatched", "ambiguous", "rounding", "weak"):
        ps = [p for p in problems if p[0] == kind]
        if not ps:
            continue
        print(f"\n{labels[kind]} ({len(ps)}):")
        for _, where, token, hits, ctx_txt, hint in ps:
            print(f"  {where}: {token}")
            print(f"      ...{ctx_txt}...")
            for r in hits:
                print(f"      row {r.name} = {r.value:g}")
            if hint:
                print(f"      research.md has it: {', '.join(hint)}")
    if unused:
        print(f"\nEntries in {os.path.basename(SOURCED)} the page no longer uses ({len(unused)}):")
        for e in unused:
            print(f"  {e['section']}: {e['figure']} ({e['row'] or e['f']})")
    if SHOW_ALL:
        print("\nMatched:")
        for where, token, r in matched:
            print(f"  {where}: {token} = {r.name} ({r.value:g})")


main()
