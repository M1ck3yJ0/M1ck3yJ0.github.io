"""Check the numbers a page states against the analysis repo's tables.

Usage:
    python3 -I _tools/check_numbers.py <page.html> <analysis repo> [year]

Collects every percentage and "N times" in the page's text: card and note text, chart
labels and other strings in its scripts. Each counts as matched if some figure rounds to it
at the number of decimals the page shows. A number after "about", "roughly", "nearly",
"almost" or "around" also matches at one significant figure.

Figures it matches against:
- everywhere: headline_numbers_<year>.csv, examples.csv, weight_vs_climate_<year>.csv, the
  example's own figures in data/examples/examples_input.csv (not its context), the EU's rows of
  ceilings_<year>.csv, weight_mix_<year>.csv, trend.csv, trend_steps.csv and trend_drivers.csv,
  and the page's data file (far_from_full_circle_data.js next to the page): the disc's shares
  (center_shards) and the imports block;
- in a script's per-country text (a line starting "XX:", as in 20a's warning lines and 20b's
  cards), only that country's rows of ceilings_<year>.csv, weight_mix_<year>.csv and the trend
  tables, plus, for each of its steps, the rate it would have reached had circular use held
  (consumption changing alone). From the trend and ceilings tables it reads rates, ceilings,
  shares and changes in percent, not the scenario columns;
- research.md: listed apart, with the register's F-number, to check by hand.

Prints the unmatched numbers with their context, to review by hand: targets and scenarios in
KNOWN are skipped. year defaults to the newest headline table in the repo.
"""
import csv
import glob
import html
import json
import math
import os
import re
import sys

PAGE, REPO = sys.argv[1], sys.argv[2]
KNOWN = {24, 70, 90, 100}   # the EU's target, the EEA's recycling scenarios, and a whole
OUT = os.path.join(REPO, "data", "processed")
if len(sys.argv) > 3:
    YEAR = sys.argv[3]
else:
    YEAR = max(re.search(r"(\d{4})", os.path.basename(p)).group(1)
               for p in glob.glob(os.path.join(OUT, "headline_numbers_*.csv")))
EU = "EU27_2020"


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# Columns of the trend and ceilings tables a country's text states: rates, ceilings, shares
# and changes in percent, not the scenario columns (cuts for a target, replaced, gone without)
TREND_COLS = re.compile(r"^(rate|ceiling|share_|consumption_change|circular_use_change|"
                        r"waste_recycled_change|waste_treated_change|waste_treated_per_)"
                        r"(?!.*(_for_|_to_close_|_pts$)).*_pct$")


def row_values(row, every_pct=False):
    """A row's figures: every percent column, or only those in TREND_COLS."""
    return [x for k, v in row.items()
            if (k.endswith("_pct") if every_pct else TREND_COLS.match(k))
            for x in [num(v)] if x is not None]


def held_rates(row):
    """The rate a step would have reached had circular use held: r / ((1 - r)(1 + c) + r)."""
    r, c = num(row.get("rate_from_pct")), num(row.get("consumption_change_pct"))
    if r is None or c is None:
        return []
    r /= 100
    return [100 * r / ((1 - r) * (1 + c / 100) + r)]


def widen(values):
    # shares stated as fractions in the tables (ring_closed is 0.475) also appear as percents;
    # falls are stored as negative changes
    values = values + [v * 100 for v in values if 0 < abs(v) < 1]
    return [abs(v) for v in values]


# Everywhere
values = []
for name in [f"headline_numbers_{YEAR}.csv", "examples.csv", f"weight_vs_climate_{YEAR}.csv"]:
    for row in rows(os.path.join(OUT, name)):
        for k in ("value", "share_of_weight_pct", "share_of_climate_impact_pct"):
            if num(row.get(k)) is not None:
                values.append(num(row[k]))
for row in rows(os.path.join(REPO, "data", "examples", "examples_input.csv")):
    if row["state"] in ("is", "will_be") and num(row["value"]) is not None:
        values.append(num(row["value"]))

# The EU's rows and each country's rows
for row in rows(os.path.join(OUT, f"ceilings_{YEAR}.csv")):
    if row["geo"] == EU:
        values += [x for v in row.values() for x in [num(v)] if x is not None]
by_geo = {}
for name in [f"ceilings_{YEAR}.csv", f"weight_mix_{YEAR}.csv", "trend.csv", "trend_steps.csv",
             "trend_drivers.csv"]:
    for row in rows(os.path.join(OUT, name)):
        vals = row_values(row, every_pct=name.startswith("weight_mix"))
        if name == "trend_steps.csv":
            vals += held_rates(row)
        by_geo.setdefault(row["geo"], []).extend(vals)
        if row["geo"] == EU and not name.startswith("ceilings"):
            values.extend(vals)

# The page's data file
data_path = os.path.join(os.path.dirname(os.path.abspath(PAGE)), "far_from_full_circle_data.js")
js = open(data_path, encoding="utf-8").read()
DATA = json.loads(js[js.index("{"):js.rindex("}") + 1])
values += list(DATA["center_shards"]["shares_pct"].values())
for m in DATA["imports"]["materials"]:
    values += [num(v) for v in m.values() if num(v) is not None]

values = widen(values)
by_geo = {g: widen(v) for g, v in by_geo.items()}

# The research register, figure by figure
register = []
for line in open(os.path.join(REPO, "research.md"), encoding="utf-8"):
    m = re.match(r"- \*\*(F\d+)\.\*\*", line)
    if m:
        for x in re.findall(r"(\d+(?:\.\d+)?)(?:%| times)", line):
            register.append((m.group(1), float(x)))

# The page's text, each script string with its country, if any
text = open(PAGE, encoding="utf-8").read()
parts = []                                           # (text, country code or None)
for m in re.finditer(r"<script[^>]*>(.*?)</script>", text, re.S):
    code = re.sub(r"/\*.*?\*/", " ", m.group(1), flags=re.S)
    code = re.sub(r"(?m)^\s*//.*$|\s//[^\"'\n]*$", " ", code)
    code = re.sub(r'\.(attr|style)\("[^"]*",\s*"[^"]*"\)', " ", code)   # styling, not text
    keys = [(k.start(), k.group(1)) for k in re.finditer(r"(?m)^\s*([A-Z]{2}):\s", code)]
    ends = [e.start() for e in re.finditer(r"(?m)^\s*\};?\s*$", code)]
    for s in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', code):
        scope = None
        before = [(p, k) for p, k in keys if p < s.start()]
        if before:
            p, k = before[-1]
            if not any(p < e < s.start() for e in ends):
                scope = k
        parts.append((s.group(1), scope))
body = re.sub(r"<script.*?</script>|<style.*?</style>|<head>.*?</head>", " ", text, flags=re.S)
body = re.sub(r"<[^>]+>", " ", re.sub(r'aria-label="([^"]*)"', r" \1 ", body))
parts.append((html.unescape(body), None))

NUM = re.compile(r"(\d+(?:\.\d+)?)(%| times|×)(?!\s*-?\d+px)")
HEDGE = re.compile(r"\b(about|roughly|nearly|almost|around)\s+$")


def rounds_to(v, x, d, hedged):
    if abs(round(v, d) - x) < 1e-9:
        return True
    if hedged and d == 0 and v > 0:
        sig = round(v, -int(math.floor(math.log10(v))))
        return abs(sig - x) < 1e-9
    return False


def matched(token, pool, hedged):
    d = len(token.split(".")[1]) if "." in token else 0
    x = float(token)
    return x in KNOWN or any(rounds_to(v, x, d, hedged) for v in pool)


misses, in_register, scoped = [], [], 0
for part, scope in parts:
    if scope and scope not in by_geo:
        print(f"Warning: no rows for {scope}")
    pool = by_geo.get(scope, []) if scope else values
    for m in NUM.finditer(part):
        hedged = bool(HEDGE.search(part[max(0, m.start() - 12):m.start()]))
        scoped += bool(scope)
        if matched(m.group(1), pool, hedged):
            continue
        a, b = max(0, m.start() - 50), min(len(part), m.end() + 30)
        ctx = (f"[{scope}] " if scope else "") + " ".join(part[a:b].split())
        token = m.group(1) + m.group(2)
        fs = sorted({f for f, v in register if matched(m.group(1), [v], hedged)},
                    key=lambda f: int(f[1:]))
        if fs:
            in_register.append((token, ",".join(fs), ctx))
        else:
            misses.append((token, ctx))

print(f"{scoped} numbers checked against their own country's rows.")
print(f"{len(in_register)} numbers found only in research.md, to check against the entry:")
for token, fs, ctx in in_register:
    print(f"  {token:>9}  {fs:<8} ...{ctx}...")
print(f"{len(misses)} numbers not found in the {YEAR} tables or research.md:")
for token, ctx in misses:
    print(f"  {token:>9}  ...{ctx}...")
