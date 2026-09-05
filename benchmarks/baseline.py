#!/usr/bin/env python3
"""Frozen copies of the pre-optimization implementations.

These are verbatim (modulo imports) snapshots of the code paths that were
replaced, kept here so the benchmark can compare old vs new on the same
browser session without checking out the old commit.
"""

import asyncio

from zendriver import cdp


async def baseline_current_url(tab):
    """Old nodriver_current_url: js_dumps('window.location.href') + rebuild."""
    url = ""
    url_dict = {}
    try:
        url_dict = await asyncio.wait_for(tab.js_dumps("window.location.href"), timeout=5.0)
    except Exception:
        return url
    url_array = []
    if url_dict:
        for k in url_dict:
            if k.isnumeric():
                if "0" in url_dict[k]:
                    url_array.append(url_dict[k]["0"])
        url = "".join(url_array)
    return url


async def baseline_exists(tab, selector):
    """Old pattern: tab.query_selector(sel) truthiness."""
    try:
        el = await tab.query_selector(selector)
        return el is not None
    except Exception:
        return False


async def baseline_click(tab, selector):
    """Old pattern: tab.query_selector(sel) then Element.click()."""
    try:
        el = await tab.query_selector(selector)
        if el:
            await el.click()
            return True
    except Exception:
        pass
    return False


async def baseline_outer_html(tab, selector):
    """Old nodriver_get_text_by_selector: query_selector + get_html."""
    try:
        el = await tab.query_selector(selector)
        if el:
            return await el.get_html()
    except Exception:
        pass
    return ""


async def baseline_cf_detect_layers_2_3(tab):
    """Old detect_cloudflare_challenge layers 2+3 (layer 1 unchanged)."""
    try:
        cf_dom = await tab.evaluate(
            "!!(document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')"
            " || document.querySelector('.cf-turnstile'))"
        )
        if cf_dom:
            return True
    except Exception:
        pass
    html_content = await tab.get_content()
    if not html_content:
        return False
    html_lower = html_content.lower()
    indicators = [
        "cf-browser-verification",
        "cf-challenge-running",
        "cf-spinner-allow-5-secs",
        "checking your browser",
        "please wait while we verify",
        "verify you are human",
    ]
    return any(i in html_lower for i in indicators)


async def baseline_area_scan(tab):
    """Old nodriver_tixcraft_area_auto_select pre-fetch: .zone element,
    then el.query_selector_all('a'), then the batch evaluate."""
    el = await tab.query_selector(".zone")
    if not el:
        return None, None
    area_list = await el.query_selector_all("a")
    area_text = await tab.evaluate("""
        Array.from(document.querySelectorAll('.zone a')).map(a => ({
            text: a.innerText.trim(),
            fontText: a.querySelector('font')?.textContent?.trim() ?? ''
        }))
    """)
    return area_list, area_text


async def baseline_area_select_and_click(tab, index):
    """Old area stage: scan + Element.click() on the chosen row."""
    area_list, area_text = await baseline_area_scan(tab)
    if not area_list:
        return False
    await area_list[index].click()
    return True
