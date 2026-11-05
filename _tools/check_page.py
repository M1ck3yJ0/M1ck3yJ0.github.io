"""Check a page at phone (390 px) and desktop (1280 px) widths before committing it.

Usage:
    python3 -I _tools/check_page.py <page.html> <outdir> [d3.min.js]

Prints a report for each width: sideways overflow in px (should be 0), elements
wider than the screen, script errors, and each figure's count of drawn chart
marks (0 means a chart didn't draw). Saves phone_sheet.png and desktop_sheet.png
in <outdir>: the top of the page plus every figure, to look over.

Outside requests are blocked, so text falls back to system fonts and the home
icon shows as a broken image; both load normally on the live site. For a page
that loads D3 from cdn.jsdelivr.net, pass a local copy of the same version, e.g.
    npm install --prefix <dir> d3@7.9.0
then <dir>/node_modules/d3/dist/d3.min.js as the third argument.

Needs Python Playwright with Chromium, and Pillow.
"""
import asyncio
import json
import os
import sys

from PIL import Image
from playwright.async_api import async_playwright

PAGE = os.path.abspath(sys.argv[1])
OUT = sys.argv[2]
D3 = sys.argv[3] if len(sys.argv) > 3 else None

INFO_JS = """() => {
  const vw = document.documentElement.clientWidth;
  const figs = [...document.querySelectorAll('figure')].map(f => ({
    id: f.id || '(no id)',
    svgs: f.querySelectorAll('svg').length,
    marks: f.querySelectorAll('svg rect, svg path, svg circle, svg line, svg polygon').length,
  }));
  const wide = [...document.querySelectorAll('body *')]
    .filter(e => getComputedStyle(e).position !== 'fixed' && e.getBoundingClientRect().right > vw + 1)
    .slice(0, 5).map(e => e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ')[0] : ''));
  return {overflow_px: document.documentElement.scrollWidth - vw, figures: figs, wider_than_screen: wide};
}"""


async def check(p, width, height, tag):
    browser = await p.chromium.launch()
    ctx = await browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1)
    errors = []

    async def route(r):
        url = r.request.url
        if url.startswith('file://'):
            await r.continue_()
        elif D3 and 'cdn.jsdelivr.net/npm/d3' in url:
            await r.fulfill(path=D3, content_type='application/javascript')
        else:
            await r.abort()

    await ctx.route('**/*', route)
    page = await ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'net::ERR_FAILED' not in m.text else None)
    await page.goto('file://' + PAGE)
    await page.wait_for_timeout(800)
    total = await page.evaluate('document.body.scrollHeight')
    for y in range(0, total, height // 2):          # scroll through so charts drawn on view get drawn
        await page.evaluate(f'window.scrollTo(0, {y})')
        await page.wait_for_timeout(50)
    await page.wait_for_timeout(800)
    info = await page.evaluate(INFO_JS)
    shots = []
    for i, f in enumerate(await page.query_selector_all('figure')):
        await f.scroll_into_view_if_needed()
        await page.wait_for_timeout(150)
        path = os.path.join(OUT, f'{tag}_fig{i}.png')
        await f.screenshot(path=path)
        shots.append(path)
    top = os.path.join(OUT, f'{tag}_top.png')
    await page.evaluate('window.scrollTo(0, 0)')
    await page.wait_for_timeout(200)
    await page.screenshot(path=top)
    await browser.close()
    return info, errors, [top] + shots


def sheet(paths, out, cols, cell_w):
    ims = [Image.open(p).convert('RGB') for p in paths]
    ims = [im.resize((cell_w, round(im.height * cell_w / im.width))) for im in ims]
    rows = [ims[i:i + cols] for i in range(0, len(ims), cols)]
    gap = 12
    W = cols * cell_w + (cols + 1) * gap
    H = sum(max(im.height for im in r) for r in rows) + (len(rows) + 1) * gap
    canvas = Image.new('RGB', (W, H), (120, 120, 120))
    y = gap
    for r in rows:
        x = gap
        for im in r:
            canvas.paste(im, (x, y))
            x += cell_w + gap
        y += max(im.height for im in r) + gap
    canvas.save(out)


async def main():
    os.makedirs(OUT, exist_ok=True)
    report = {}
    async with async_playwright() as p:
        for tag, w, h, cols, cell in [('phone', 390, 844, 6, 300), ('desktop', 1280, 900, 3, 520)]:
            info, errors, shots = await check(p, w, h, tag)
            sheet(shots, os.path.join(OUT, f'{tag}_sheet.png'), cols, cell)
            report[tag] = {**info, 'errors': errors[:5]}
    print(json.dumps(report, indent=1))

asyncio.run(main())
