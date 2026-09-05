# Benchmarks

Reproducible measurements behind the hot-path optimisations in
`src/nodriver_common.py`, `src/util.py`, `src/platforms/tixcraft.py` and
`src/platforms/kktix.py`.

## Why these paths

The bot is a 50ms polling loop over the Chrome DevTools Protocol (CDP). Every
CDP command is a WebSocket round-trip plus JSON encode/decode on both sides,
so the cost that matters is **round-trips per tick × bytes per round-trip**,
not Python CPU. Two zendriver conveniences dominated that cost:

| Call | What it actually does | Cost on a 2.5k-node page |
|------|-----------------------|--------------------------|
| `tab.js_dumps('window.location.href')` | Enumerates the URL *string* like an object: one key per character plus every `String.prototype` member, each `.toString()`-ed, then Python re-joins ~120 nested dicts | 1 msg, large payload, ~1ms |
| `tab.query_selector(sel)` | `DOM.getDocument(depth=-1, pierce=True)` (whole tree over the wire) + `DOM.querySelector` + Python tree walk | 2 msgs, ~43ms |
| `Element.click()` | `DOM.resolveNode` + `DOM.getContentQuads` + injects a red "flash" `<div>` and a CSS keyframe into the page + `el.click()` | +4 msgs, and a visible DOM mutation on the target site |
| `tab.get_content()` | `DOM.getDocument` + `DOM.getOuterHTML` of the whole page | 2 msgs, ~48ms |
| `tab.wait_for(sel, timeout)` | `query_selector` in a loop with `sleep(0.5)` | up to 500ms late per appearance |

The replacements are one `Runtime.evaluate(returnByValue=True)` each, doing
the `querySelector` / `click()` / text extraction inside the page and shipping
back only a boolean, a short string, or a small JSON list.

## Results

Environment: Linux x86_64, Chromium 141 headless, zendriver 0.15.3,
fixture page with 2,531 DOM nodes and 40 area rows (`fixtures/area_page.html`).
`old` = frozen copies in `baseline.py`; `new` = current `src/`.

### `bench_cdp.py` (200 iterations, median / p95 per call)

| Scenario | old median / p95 (ms) | old CDP msgs | new median / p95 (ms) | new CDP msgs | speedup |
|---|---|---|---|---|---|
| URL poll (every 50ms tick) | 0.94 / 1.23 | 1.0 | 0.27 / 0.47 | 1.0 | 3.5x |
| Existence probe, selector absent | 42.59 / 63.52 | 2.0 | 0.28 / 0.48 | 1.0 | 151x |
| Click first `.zone a` | 50.61 / 72.66 | 6.0 | 0.37 / 0.61 | 1.0 | 136x |
| outerHTML of one element | 46.14 / 68.60 | 3.0 | 0.29 / 0.45 | 1.0 | 160x |
| Cloudflare detect (on URL change) | 51.55 / 74.98 | 4.0 | 2.43 / 3.04 | 2.0 | 21x |
| TixCraft area stage: scan + click | 182.80 / 199.19 | 11.0 | 1.30 / 1.80 | 2.0 | 141x |
| Full main-loop tick on tixcraft page | 45.02 / 66.53 | 4.0 | 1.01 / 1.55 | 3.0 | 45x |

What this means for the bot:

- **Loop period**: `sleep(0.05)` + tick work. On a TixCraft page the old
  tick cost ~45ms (the cookie-banner probe alone was a full DOM dump every
  tick), so the effective poll period was ~95ms. It is now ~51ms: the bot
  sees a page change roughly twice as fast.
- **Area click**: from "rows visible" to `element.click()` dispatched went
  from ~183ms to ~1.3ms.
- **Waits**: `nodriver_wait_for_selector` notices an element within 50ms of
  it appearing instead of at the next 500ms probe (verified in
  `tests/test_cdp_fast_path.py::test_wait_for_selector_reacts_within_poll_interval`).
- **Fingerprint**: no more `flash()` `<div>`/keyframe injection into the
  ticketing site's DOM on every click.

### `bench_pure.py` (Python-only helpers called per row / per tick)

| Helper | old µs/call | new µs/call | speedup |
|---|---|---|---|
| `get_app_root()` | 1.34 | 0.03 | 47x |
| `get_instance_state_path()` (named instance, was `os.makedirs` each call) | 7.73 | 0.45 | 17x |
| `parse_keyword_string_to_array()` | 1.03 | 0.13 | 8x |
| `reset_row_text_if_match_keyword_exclude()` (default exclude list) | 2.87 | 1.45 | 2x |
| `is_text_match_keyword('3,280;2,680', row)` | 1.60 | 0.20 | 8x |

These are microseconds and secondary to the CDP work above; they are
included because they run for every row on every tick and the change
(memoising `json.loads` of settings strings) is free.

### `bench_startup.py` (5 rounds, median)

| Metric | old (sequential) | new (OCR load overlapped with browser start) | delta |
|---|---|---|---|
| Time to bot ready (browser + page + OCR) | 380 ms | 367 ms | −13 ms |

Honest note: the universal model loads in ~25ms and the stock ddddocr model
in ~160ms on this machine, so overlapping OCR initialisation with the browser
launch is a small win. A warm-up inference was tried and dropped: the first
`classification()` was already ~3ms cold, so there was nothing to pre-pay.

## Running

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirement.txt pytest
python benchmarks/bench_cdp.py --iterations 200      # needs Chrome/Chromium; see --chrome
python benchmarks/bench_pure.py
python benchmarks/bench_startup.py --rounds 5
python -m pytest tests -q                             # 44 tests; browser tests skip without Chrome
```

`fixtures/gen_fixture.py` regenerates `fixtures/area_page.html`
deterministically.
