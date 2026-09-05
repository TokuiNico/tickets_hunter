#!/usr/bin/env python3
"""Generate a realistic-size ticket page fixture for the CDP benchmarks.

The page mimics a TixCraft /ticket/area/ page: a header, a cookie banner
placeholder that is NOT present (so existence checks miss, like production
after the banner is dismissed), ~40 area links under .zone with <font>
seat counters, and a few thousand filler nodes so DOM.getDocument has a
realistic payload. Deterministic output.
"""

import os

AREA_COUNT = 40
FILLER_BLOCKS = 600  # each block = 5 nodes -> ~3000 filler nodes


def build():
    parts = [
        "<!doctype html><html lang='zh-TW'><head><meta charset='utf-8'>",
        "<title>Bench area page</title><style>.zone a{display:block}</style></head><body>",
        "<div id='header'><nav>",
    ]
    for i in range(30):
        parts.append(f"<a href='/nav/{i}'>nav item {i}</a>")
    parts.append("</nav></div>")

    parts.append("<div id='filler'>")
    for i in range(FILLER_BLOCKS):
        parts.append(
            f"<div class='card' data-i='{i}'><span class='t'>title {i}</span>"
            f"<p class='d'>description text number {i} lorem ipsum dolor</p>"
            f"<small>meta {i}</small></div>"
        )
    parts.append("</div>")

    parts.append("<div class='zone'>")
    for i in range(AREA_COUNT):
        seats = "熱賣中" if i % 3 else str((i % 9) + 1)
        price = 1800 + (i % 6) * 400
        parts.append(
            f"<a href='#' id='area_{i}' data-id='{i}'>{i + 1}F 區域 {chr(65 + i % 26)} "
            f"{price} <font color='red'>{seats}</font></a>"
        )
    parts.append("</div>")

    parts.append(
        "<form id='TicketForm'><select id='TicketForm_ticketPrice_01' class='mobile-select'>"
        "<option value='0'>0</option><option value='1'>1</option><option value='2'>2</option>"
        "<option value='3'>3</option><option value='4'>4</option></select>"
        "<input type='checkbox' id='TicketForm_agree'>"
        "<input type='text' id='TicketForm_verifyCode'>"
        "<img id='TicketForm_verifyCode-image' alt='captcha'></form>"
    )
    parts.append(
        "<script>window.__clicks=0;document.querySelectorAll('.zone a')"
        ".forEach(a=>a.addEventListener('click',e=>{e.preventDefault();window.__clicks++;}));</script>"
    )
    parts.append("</body></html>")
    return "".join(parts)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "area_page.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build())
    print(out, os.path.getsize(out), "bytes")
