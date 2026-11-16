"""Render each scroll step of a page at phone (390 px) and desktop (1280 px) widths.

Usage:
    python3 -I _tools/check_steps.py <page.html> <outdir> [d3.min.js] [scrollama.min.js]

Serves the repo on a local server, so the page's own fonts and images load.
Scrolls each step (any element with a data-state attribute) until its top sits
at 60% of the screen, then screenshots the screen. Prints, for each width, the
steps not marked active (class is-active) when shown, and any errors. Saves
phone_steps.png and desktop_steps.png in <outdir>, one numbered tile per step.

Outside requests are blocked. For a page that loads D3 or Scrollama from
cdn.jsdelivr.net, pass local copies of the same versions, e.g.
    npm install --prefix <dir> d3@7.9.0 scrollama@3.2.0
then <dir>/node_modules/d3/dist/d3.min.js and
<dir>/node_modules/scrollama/build/scrollama.min.js.

Needs Python Playwright with Chromium, and Pillow.
"""
import asyncio
import functools
import http.server
import io
import json
import os
import sys
import threading
import urllib.parse

from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = urllib.parse.quote(os.path.relpath(os.path.abspath(sys.argv[1]), ROOT))
OUT = sys.argv[2]
D3 = sys.argv[3] if len(sys.argv) > 3 else None
SCROLLAMA = sys.argv[4] if len(sys.argv) > 4 else None
STEP = '[data-state]'
WIDTHS = {'phone': (390, 844, 4, 300), 'desktop': (1280, 800, 3, 420)}

SCROLL_JS = """([sel, i]) => {
  const s = document.querySelectorAll(sel)[i];
  scrollTo(0, Math.max(0, s.getBoundingClientRect().top + scrollY - innerHeight * 0.6));
}"""
ACTIVE_JS = """([sel, i]) => {
  if (!document.querySelector(sel + '.is-active')) return null;
  return document.querySelectorAll(sel)[i].classList.contains('is-active');
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def sheet(tiles, cols, width, path):
    tiles = [t.resize((width, round(t.height * width / t.width))) for t in tiles]
    height = max(t.height for t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new('RGB', (8 + cols * (width + 8), 8 + rows * (height + 8)), '#888888')
    draw = ImageDraw.Draw(out)
    for k, t in enumerate(tiles):
        x, y = 8 + (k % cols) * (width + 8), 8 + (k // cols) * (height + 8)
        out.paste(t, (x, y))
        draw.rectangle([x, y, x + 24, y + 16], fill='#000000')
        draw.text((x + 5, y + 3), str(k + 1), fill='#ffffff')
    out.save(path)


async def check(browser, base, name, width, height, cols, tile):
    ctx = await browser.new_context(viewport={'width': width, 'height': height})

    async def route(r):
        url = r.request.url
        if url.startswith(base):
            await r.continue_()
        elif D3 and 'cdn.jsdelivr.net/npm/d3' in url:
            await r.fulfill(path=D3, content_type='application/javascript')
        elif SCROLLAMA and 'cdn.jsdelivr.net/npm/scrollama' in url:
            await r.fulfill(path=SCROLLAMA, content_type='application/javascript')
        else:
            await r.abort()

    await ctx.route('**/*', route)
    page = await ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    await page.goto(base + PAGE)
    await page.wait_for_timeout(800)
    n = await page.evaluate('(sel) => document.querySelectorAll(sel).length', STEP)
    tiles, inactive = [], []
    for i in range(n):
        await page.evaluate(SCROLL_JS, [STEP, i])
        await page.wait_for_timeout(400)
        if await page.evaluate(ACTIVE_JS, [STEP, i]) is False:
            inactive.append(i + 1)
        tiles.append(Image.open(io.BytesIO(await page.screenshot())))
    if tiles:
        sheet(tiles, cols, tile, os.path.join(OUT, f'{name}_steps.png'))
    await ctx.close()
    return {'steps': n, 'not_active_when_shown': inactive, 'errors': errors}


async def main():
    os.makedirs(OUT, exist_ok=True)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_address[1]}/'
    report = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, (width, height, cols, tile) in WIDTHS.items():
            report[name] = await check(browser, base, name, width, height, cols, tile)
        await browser.close()
    server.shutdown()
    print(json.dumps(report, indent=1))


asyncio.run(main())
