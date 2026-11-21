"""Check the numbers a page states against the analysis repo's tables.

Usage:
    python3 -I _tools/check_numbers.py <page.html> <analysis repo> [year]

Collects every percentage and "N times" in the page's text: card and note text, chart
labels and other strings in its scripts. Each counts as matched if some figure in the repo
rounds to it at the number of decimals the page shows (headline_numbers_<year>.csv,
examples.csv, and the EU's row of ceilings_<year>.csv). Prints the unmatched ones with their
context, to review by hand: targets, scenarios and figures from outside sources show up
here too, apart from the targets and scenario shares in KNOWN. year defaults to the newest
headline table in the repo.
"""
import csv
import glob
import html
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

values = []
for name in [f"headline_numbers_{YEAR}.csv", "examples.csv", f"weight_vs_climate_{YEAR}.csv"]:
    with open(os.path.join(OUT, name), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for k, v in row.items():
                if k in ("value", "share_of_weight_pct", "share_of_climate_impact_pct"):
                    try:
                        values.append(float(v))
                    except ValueError:
                        pass
with open(os.path.join(OUT, f"ceilings_{YEAR}.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["geo"] == "EU27_2020":
            for v in row.values():
                try:
                    values.append(float(v))
                except ValueError:
                    pass
# shares stated as fractions in the tables (ring_closed is 0.475) also appear as percents
values += [v * 100 for v in values if 0 < abs(v) < 1]
values = [abs(v) for v in values]                    # falls are stored as negative changes

text = open(PAGE, encoding="utf-8").read()
parts = []
for m in re.finditer(r"<script[^>]*>(.*?)</script>", text, re.S):
    code = re.sub(r"/\*.*?\*/", " ", m.group(1), flags=re.S)
    code = re.sub(r"(?m)^\s*//.*$|\s//[^\"'\n]*$", " ", code)
    code = re.sub(r'\.(attr|style)\("[^"]*",\s*"[^"]*"\)', " ", code)   # styling, not text
    parts += re.findall(r'"((?:[^"\\\n]|\\.)*)"', code)
body = re.sub(r"<script.*?</script>|<style.*?</style>|<head>.*?</head>", " ", text, flags=re.S)
body = re.sub(r"<[^>]+>", " ", re.sub(r'aria-label="([^"]*)"', r" \1 ", body))
parts.append(html.unescape(body))

NUM = re.compile(r"(\d+(?:\.\d+)?)(%| times|×)(?!\s*-?\d+px)")


def matched(token):
    d = len(token.split(".")[1]) if "." in token else 0
    x = float(token)
    if x in KNOWN:
        return True
    return any(abs(round(v, d) - x) < 1e-9 for v in values)


misses = []
for part in parts:
    for m in NUM.finditer(part):
        if not matched(m.group(1)):
            a, b = max(0, m.start() - 50), min(len(part), m.end() + 30)
            misses.append((m.group(1) + m.group(2), " ".join(part[a:b].split())))

print(f"{len(misses)} numbers not found in the {YEAR} tables:")
for token, ctx in misses:
    print(f"  {token:>9}  ...{ctx}...")
