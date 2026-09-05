"""Integration tests for the single-round-trip DOM helpers against a real
headless Chromium (skipped when no browser is available).

These pin the semantics the platform modules rely on: existence probes,
JS clicks by index, outerHTML fetch, the URL poll, the fast wait, the
TixCraft area scan, and Cloudflare detection on both a clean page and a
page carrying interstitial markers.
"""

import asyncio
import http.server
import logging
import os
import shutil
import sys
import threading

import pytest

import nodriver_common as nc
from platforms import tixcraft

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURES = os.path.join(ROOT, "benchmarks", "fixtures")


def _find_chrome():
    for cand in (
        os.environ.get("TICKETS_HUNTER_E2E_CHROMIUM"),
        "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ):
        if cand and os.path.exists(cand):
            return cand
    return None


CHROME = _find_chrome()
pytestmark = pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium binary available")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def server():
    if not os.path.exists(os.path.join(FIXTURES, "area_page.html")):
        import subprocess

        subprocess.check_call([sys.executable, os.path.join(FIXTURES, "gen_fixture.py")])
    cf_page = os.path.join(FIXTURES, "cf_page.html")
    with open(cf_page, "w", encoding="utf-8") as fh:
        fh.write(
            "<html><body><div id='cf-challenge-running'>Checking your browser before "
            "accessing the site.</div></body></html>"
        )
    handler = lambda *a, **k: _Quiet(*a, directory=FIXTURES, **k)  # noqa: E731
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    os.remove(cf_page)


@pytest.fixture(scope="module")
def browser():
    import zendriver as uc
    from zendriver.core.config import Config

    # zendriver logs the browser's stderr at INFO when the CDP handshake fails;
    # keep it so a CI failure shows the real cause instead of the generic hint.
    logging.getLogger("zendriver").setLevel(logging.INFO)

    async def start():
        args = nc.get_nodriver_browser_args() + ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"]
        conf = Config(
            browser_args=args,
            sandbox=False,
            headless=True,
            browser_executable_path=CHROME,
            # A cold Chrome start on a CI runner can take several seconds; the
            # zendriver default (0.25s x 10 tries) gives up too early.
            browser_connection_timeout=1.0,
            browser_connection_max_tries=30,
        )
        return await uc.start(conf)

    loop = asyncio.new_event_loop()
    b = loop.run_until_complete(start())
    yield loop, b
    loop.run_until_complete(b.stop())
    loop.close()


@pytest.fixture
def tab(browser, server):
    loop, b = browser

    async def go():
        t = await b.get(server + "/area_page.html")
        await t.wait_for(".zone a", timeout=10)
        return t

    return loop, loop.run_until_complete(go())


def run(loop, coro):
    return loop.run_until_complete(coro)


def test_current_url_matches_location(tab):
    loop, t = tab
    url, quit_flag = run(loop, nc.nodriver_current_url(t, {"advanced": {"verbose": False}}))
    assert url.endswith("/area_page.html")
    assert quit_flag is False
    assert url == run(loop, t.evaluate("location.href"))


def test_current_url_tracks_hash_navigation(tab):
    loop, t = tab
    run(loop, t.evaluate("location.hash = '#/booking'"))
    url, _ = run(loop, nc.nodriver_current_url(t))
    assert url.endswith("#/booking")


def test_dom_exists(tab):
    loop, t = tab
    assert run(loop, nc.nodriver_dom_exists(t, ".zone a")) is True
    assert run(loop, nc.nodriver_dom_exists(t, "#onetrust-accept-btn-handler")) is False
    assert run(loop, nc.nodriver_dom_exists(t, "#TicketForm_agree")) is True
    # a broken selector must not raise
    assert run(loop, nc.nodriver_dom_exists(t, "div[")) is False
    assert run(loop, nc.nodriver_dom_exists(None, "div")) is False


def test_dom_click_by_index_fires_handler(tab):
    loop, t = tab
    before = run(loop, t.evaluate("window.__clicks"))
    assert run(loop, nc.nodriver_dom_click(t, ".zone a", 5)) is True
    assert run(loop, t.evaluate("window.__clicks")) == before + 1
    assert run(loop, nc.nodriver_dom_click(t, ".zone a", 9999)) is False
    assert run(loop, nc.nodriver_dom_click(t, "#does-not-exist")) is False


def test_dom_click_checkbox_toggles(tab):
    loop, t = tab
    assert run(loop, t.evaluate("document.querySelector('#TicketForm_agree').checked")) is False
    assert run(loop, nc.nodriver_dom_click(t, "#TicketForm_agree")) is True
    assert run(loop, t.evaluate("document.querySelector('#TicketForm_agree').checked")) is True


def test_dom_outer_html_and_text_helper(tab):
    loop, t = tab
    html = run(loop, nc.nodriver_dom_outer_html(t, "#area_0"))
    assert html.startswith("<a ") and "1F 區域 A" in html
    assert run(loop, nc.nodriver_dom_outer_html(t, "#nope")) == ""
    text = run(loop, nc.nodriver_get_text_by_selector(t, "#area_0", "innerText"))
    assert "<" not in text and "1F 區域 A" in text


def test_modal_dialog_probe(tab):
    loop, t = tab
    assert run(loop, nc.nodriver_check_modal_dialog_popup(t)) is False
    run(
        loop,
        t.evaluate(
            "document.body.insertAdjacentHTML('beforeend',"
            '\'<div class="modal-dialog"><div class="modal-content">x</div></div>\')'
        ),
    )
    assert run(loop, nc.nodriver_check_modal_dialog_popup(t)) is True


def test_wait_for_selector_reacts_within_poll_interval(tab):
    loop, t = tab
    assert run(loop, nc.nodriver_wait_for_selector(t, ".zone a", timeout=1)) is True
    assert run(loop, nc.nodriver_wait_for_selector(t, "#late", timeout=0.2)) is False

    async def appear_later():
        await t.evaluate(
            "setTimeout(() => { const d = document.createElement('div');"
            " d.id = 'late'; document.body.appendChild(d); }, 300)"
        )
        loop_ = asyncio.get_running_loop()
        t0 = loop_.time()
        ok = await nc.nodriver_wait_for_selector(t, "#late", timeout=3)
        return ok, loop_.time() - t0

    ok, elapsed = run(loop, appear_later())
    assert ok is True
    assert 0.25 < elapsed < 0.6  # old tab.wait_for would land at >= 0.5s granularity


def test_scan_area_rows(tab):
    loop, t = tab
    rows = run(loop, tixcraft.nodriver_tixcraft_scan_area_rows(t))
    assert isinstance(rows, list) and len(rows) == 40
    assert rows[0]["index"] == 0
    assert rows[0]["text"].startswith("1F 區域 A")
    # fixture: i % 3 == 0 -> numeric seat count (i % 9) + 1, else "熱賣中"
    assert rows[0]["fontText"] == "1"
    assert rows[1]["fontText"] == "熱賣中"
    assert rows[3]["fontText"] == "4"
    assert [r["index"] for r in rows] == list(range(40))


def test_scan_area_rows_absent_zone(browser, server):
    loop, b = browser

    async def go():
        t = await b.get(server + "/cf_page.html")
        await t.wait_for("#cf-challenge-running", timeout=10)
        return await tixcraft.nodriver_tixcraft_scan_area_rows(t)

    assert run(loop, go()) is None


def test_get_tixcraft_target_area_filters(tab):
    loop, t = tab
    rows = run(loop, tixcraft.nodriver_tixcraft_scan_area_rows(t))
    cfg = {
        "area_auto_select": {"mode": "from top to bottom"},
        "keyword_exclude": "",
        "ticket_number": 2,
        "tixcraft": {"allow_less_tickets": False},
    }

    need_refresh, matched = run(loop, tixcraft.nodriver_get_tixcraft_target_area(rows, cfg, "區域 B"))
    assert need_refresh is False
    assert matched and all("區域 B" in r["text"] for r in matched)
    # rows whose <font> shows 1-9 seats are skipped when ticket_number > 1
    assert all(r["fontText"] == "熱賣中" for r in matched)

    need_refresh, matched = run(loop, tixcraft.nodriver_get_tixcraft_target_area(rows, cfg, "不存在的關鍵字"))
    assert need_refresh is True and matched is None

    cfg["keyword_exclude"] = '"區域"'
    need_refresh, matched = run(loop, tixcraft.nodriver_get_tixcraft_target_area(rows, cfg, ""))
    assert need_refresh is True and matched is None


def test_cloudflare_detect(browser, server, tab):
    loop, b = browser
    _, clean_tab = tab
    assert run(loop, nc.detect_cloudflare_challenge(clean_tab)) is False

    async def go():
        t = await b.get(server + "/cf_page.html")
        await t.wait_for("#cf-challenge-running", timeout=10)
        return await nc.detect_cloudflare_challenge(t)

    assert run(loop, go()) is True
