#!/usr/bin/env python3
"""CDP hot-path benchmark: old implementation vs current implementation.

Runs a real headless Chromium through zendriver against a local fixture page
(benchmarks/fixtures/area_page.html) and times the operations the bot
performs on its 50ms main-loop tick and on the ticket critical path.

    python benchmarks/bench_cdp.py [--iterations 200] [--chrome /path/to/chrome]

Each scenario reports median / p95 latency per call and the number of CDP
messages sent per call (counted by wrapping tab.send). "old" is the frozen
copy in benchmarks/baseline.py, "new" is the live code in src/.
"""

import argparse
import asyncio
import http.server
import os
import shutil
import statistics
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import zendriver as uc  # noqa: E402
from zendriver import cdp  # noqa: E402
from zendriver.core.config import Config  # noqa: E402

import baseline  # noqa: E402
import nodriver_common as nc  # noqa: E402
from platforms import tixcraft  # noqa: E402


# ----------------------------------------------------------------------------
# infrastructure


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve_fixtures():
    fixtures = os.path.join(HERE, "fixtures")
    if not os.path.exists(os.path.join(fixtures, "area_page.html")):
        import subprocess

        subprocess.check_call([sys.executable, os.path.join(fixtures, "gen_fixture.py")])
    handler = lambda *a, **k: _Quiet(*a, directory=fixtures, **k)  # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/area_page.html"


def find_chrome(explicit):
    if explicit:
        return explicit
    for cand in (
        "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ):
        if cand and os.path.exists(cand):
            return cand
    return None


class SendCounter:
    """Wrap tab.send to count CDP messages issued during a measured call."""

    def __init__(self, tab):
        self.tab = tab
        self.count = 0
        self._orig = tab.send

    def __enter__(self):
        counter = self

        async def counted(cdp_obj, _is_update=False):
            counter.count += 1
            return await counter._orig(cdp_obj, _is_update)

        self.tab.send = counted
        return self

    def __exit__(self, *exc):
        self.tab.send = self._orig


async def timeit(fn, iterations):
    """Return (median_ms, p95_ms, cdp_msgs_per_call, last_result)."""
    # warm-up
    for _ in range(3):
        await fn()
    samples = []
    with SendCounter(_current_tab) as counter:
        result = None
        for _ in range(iterations):
            t0 = time.perf_counter()
            result = await fn()
            samples.append((time.perf_counter() - t0) * 1000.0)
    samples.sort()
    med = statistics.median(samples)
    p95 = samples[int(len(samples) * 0.95) - 1]
    return med, p95, counter.count / iterations, result


_current_tab = None

# ----------------------------------------------------------------------------
# scenarios: each returns (old_fn, new_fn, description)

SEL_ABSENT = "#onetrust-accept-btn-handler"
SEL_AREA = ".zone a"
SEL_TEXT = "#TicketForm_verifyCode"


def scenarios(tab, config_dict):
    async def old_tick():
        # what one main-loop tick on a tixcraft page cost before:
        # url poll + cookie banner probe (per tick until seen) + EPS block probe
        await baseline.baseline_current_url(tab)
        await baseline.baseline_exists(tab, SEL_ABSENT)
        await tixcraft.nodriver_ticketmaster_check_ip_block(tab, config_dict, "")

    async def new_tick():
        await nc.nodriver_current_url(tab, config_dict)
        await nc.nodriver_dom_click(tab, SEL_ABSENT)
        await tixcraft.nodriver_ticketmaster_check_ip_block(tab, config_dict, "")

    async def old_cf():
        try:
            await tab.send(cdp.target.get_targets())
        except Exception:
            pass
        return await baseline.baseline_cf_detect_layers_2_3(tab)

    async def new_cf():
        return await nc.detect_cloudflare_challenge(tab)

    async def old_area():
        return await baseline.baseline_area_select_and_click(tab, 3)

    async def new_area():
        # mirrors the new nodriver_tixcraft_area_auto_select fast path
        rows = await tixcraft.nodriver_tixcraft_scan_area_rows(tab)
        if not rows:
            return False
        return await nc.nodriver_dom_click(tab, SEL_AREA, rows[3]["index"])

    return [
        (
            "URL poll (every 50ms tick)",
            lambda: baseline.baseline_current_url(tab),
            lambda: nc.nodriver_current_url(tab, config_dict),
        ),
        (
            "Existence probe, selector absent",
            lambda: baseline.baseline_exists(tab, SEL_ABSENT),
            lambda: nc.nodriver_dom_exists(tab, SEL_ABSENT),
        ),
        (
            "Click first '.zone a'",
            lambda: baseline.baseline_click(tab, SEL_AREA),
            lambda: nc.nodriver_dom_click(tab, SEL_AREA),
        ),
        (
            "outerHTML of one element",
            lambda: baseline.baseline_outer_html(tab, SEL_TEXT),
            lambda: nc.nodriver_dom_outer_html(tab, SEL_TEXT),
        ),
        ("Cloudflare detect (on URL change)", old_cf, new_cf),
        ("TixCraft area stage: scan + click", old_area, new_area),
        ("Full main-loop tick on tixcraft page", old_tick, new_tick),
    ]


def fmt_row(name, old, new):
    speedup = old[0] / new[0] if new[0] > 0 else float("inf")
    return (
        f"| {name} | {old[0]:.2f} / {old[1]:.2f} | {old[2]:.1f} "
        f"| {new[0]:.2f} / {new[1]:.2f} | {new[2]:.1f} | {speedup:.1f}x |"
    )


async def main(args):
    global _current_tab
    chrome = find_chrome(args.chrome)
    if not chrome:
        print("No Chrome/Chromium found; pass --chrome", file=sys.stderr)
        return 2

    httpd, url = serve_fixtures()
    browser_args = nc.get_nodriver_browser_args() + [
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    conf = Config(browser_args=browser_args, sandbox=False, headless=True, browser_executable_path=chrome)
    browser = await uc.start(conf)
    try:
        tab = await browser.get(url)
        await tab.wait_for(".zone a", timeout=10)
        _current_tab = tab

        config_dict = {
            "advanced": {"verbose": False, "tixcraft_soft_block_delay": ""},
            "homepage": "https://tixcraft.com/activity/detail/bench",
        }
        node_count = await tab.evaluate("document.getElementsByTagName('*').length")
        print(f"fixture: {url}  DOM nodes: {node_count}  iterations: {args.iterations}\n")
        print("| Scenario | old median / p95 (ms) | old CDP msgs | new median / p95 (ms) | new CDP msgs | speedup |")
        print("|---|---|---|---|---|---|")
        for name, old_fn, new_fn in scenarios(tab, config_dict):
            old = await timeit(old_fn, args.iterations)
            new = await timeit(new_fn, args.iterations)
            if name.startswith("URL poll"):
                assert old[3] == new[3][0], (old[3], new[3])
            print(fmt_row(name, old, new), flush=True)
        clicks = await tab.evaluate("window.__clicks")
        print(f"\nsanity: fixture recorded {clicks} clicks (old and new click paths both fire the handler)")
    finally:
        await browser.stop()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=200)
    ap.add_argument("--chrome", default=None)
    sys.exit(asyncio.run(main(ap.parse_args())))
