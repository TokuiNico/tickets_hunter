#!/usr/bin/env python3
"""Start-up benchmark.

Measures time-to-ready with the real universal OCR model in
src/assets/model/universal:

  1. sequential (old main()): browser start -> homepage -> OCR model load.
  2. overlapped (new main()): OCR load in a worker thread while the browser
     starts.

    python benchmarks/bench_startup.py [--rounds 3] [--chrome PATH]
"""

import argparse
import asyncio
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
sys.path.insert(0, SRC)
sys.path.insert(0, HERE)

import zendriver as uc  # noqa: E402
from zendriver.core.config import Config  # noqa: E402

import nodriver_common as nc  # noqa: E402
from bench_cdp import find_chrome, serve_fixtures  # noqa: E402


def make_conf(chrome):
    args = nc.get_nodriver_browser_args() + ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
    return Config(browser_args=args, sandbox=False, headless=True, browser_executable_path=chrome)


async def stop_quietly(browser):
    # Chrome may close the CDP socket before zendriver's stop() finishes
    # draining it; that teardown race is not what we are measuring.
    try:
        await browser.stop()
    except Exception:
        pass


async def run_sequential(chrome, url, config_dict):
    t0 = time.perf_counter()
    browser = await uc.start(make_conf(chrome))
    tab = await browser.get(url)
    await tab.wait_for(".zone a", timeout=10)
    ocr = nc.create_ocr_instance(config_dict)  # old: after browser, blocking
    assert ocr is not None
    ready = time.perf_counter() - t0
    await stop_quietly(browser)
    return ready


async def run_overlapped(chrome, url, config_dict):
    t0 = time.perf_counter()
    ocr_task = asyncio.ensure_future(nc.create_ocr_instance_async(config_dict))
    browser = await uc.start(make_conf(chrome))
    tab = await browser.get(url)
    await tab.wait_for(".zone a", timeout=10)
    ocr = await ocr_task  # new: already loaded
    assert ocr is not None
    ready = time.perf_counter() - t0
    await stop_quietly(browser)
    return ready


async def main(args):
    chrome = find_chrome(args.chrome)
    if not chrome:
        print("No Chrome/Chromium found; pass --chrome", file=sys.stderr)
        return 2
    httpd, url = serve_fixtures()
    config_dict = {
        "homepage": "https://tixcraft.com/activity/detail/bench",
        "ocr_captcha": {"enable": True, "beta": True, "use_universal": True, "path": "assets/model/universal"},
        "advanced": {"verbose": False},
    }
    seq, ovl = [], []
    try:
        for _ in range(args.rounds):
            seq.append(await run_sequential(chrome, url, config_dict))
            ovl.append(await run_overlapped(chrome, url, config_dict))
    finally:
        httpd.shutdown()

    a = statistics.median(seq) * 1000
    b = statistics.median(ovl) * 1000
    print(f"rounds: {args.rounds}\n")
    print("| Metric | old (sequential) | new (overlapped) | delta |")
    print("|---|---|---|---|")
    print(f"| Time to bot ready (browser + page + OCR) | {a:.0f} ms | {b:.0f} ms | -{a - b:.0f} ms |")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--chrome", default=None)
    sys.exit(asyncio.run(main(ap.parse_args())))
