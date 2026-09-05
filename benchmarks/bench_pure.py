#!/usr/bin/env python3
"""Pure-Python hot helper micro-benchmark (no browser).

Compares the pre-optimization implementations (inlined here from git history)
against the current util.py for the helpers the main loop and the row
matchers call on every tick.

    python benchmarks/bench_pure.py
"""

import json
import os
import sys
import timeit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

import util  # noqa: E402

EXCLUDE = '"輪椅","身障","身心","障礙","愛心","Restricted View","燈柱遮蔽","視線不完整"'
ROW = "2F 區域 B 3,280 熱賣中 視線良好"
CONFIG = {"keyword_exclude": EXCLUDE}


# --- old implementations -----------------------------------------------------


def old_get_app_root():
    if hasattr(sys, "frozen"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(util.__file__))


def old_get_instance_state_path(filename, instance_id="bench01"):
    app_root = old_get_app_root()
    instance_dir = os.path.join(app_root, "instances", instance_id)
    os.makedirs(instance_dir, exist_ok=True)
    return os.path.join(instance_dir, filename)


def old_parse_keyword_string_to_array(keyword_string):
    if not keyword_string or not keyword_string.strip():
        return []
    try:
        return json.loads("[" + keyword_string + "]")
    except Exception:
        return []


def old_is_row_match_keyword(keyword_string, row_text):
    row_text = util.format_keyword_string(row_text)
    is_match_keyword = True
    if len(keyword_string) > 0 and len(row_text) > 0:
        is_match_keyword = False
        try:
            keyword_array = json.loads("[" + keyword_string + "]")
        except Exception:
            keyword_array = []
        for item_list in keyword_array:
            if len(item_list) > 0:
                if " " in item_list:
                    ok = True
                    for each in item_list.split(" "):
                        if util.format_keyword_string(each) not in row_text:
                            ok = False
                    if ok:
                        is_match_keyword = True
                else:
                    if util.format_keyword_string(item_list) in row_text:
                        is_match_keyword = True
            else:
                is_match_keyword = True
            if is_match_keyword:
                break
    return is_match_keyword


def old_is_text_match_keyword(keyword_string, text):
    is_match_keyword = True
    if len(keyword_string) > 0 and len(text) > 0:
        if ";" in keyword_string and '"' not in keyword_string:
            items = keyword_string.split(";")
            keyword_string = ",".join([f'"{i.strip()}"' for i in items if i.strip()])
        if len(keyword_string) > 0 and '"' not in keyword_string:
            keyword_string = '"' + keyword_string + '"'
        is_match_keyword = False
        try:
            keyword_array = json.loads("[" + keyword_string + "]")
        except Exception:
            keyword_array = []
        for item_list in keyword_array:
            if len(item_list) > 0:
                if " " in item_list:
                    if all(e in text for e in item_list.split(" ")):
                        is_match_keyword = True
                elif item_list in text:
                    is_match_keyword = True
            else:
                is_match_keyword = True
            if is_match_keyword:
                break
    return is_match_keyword


# --- runner ------------------------------------------------------------------


def bench(name, old_fn, new_fn, number=20000):
    assert old_fn() == new_fn(), (name, old_fn(), new_fn())
    old_t = min(timeit.repeat(old_fn, number=number, repeat=5)) / number * 1e6
    new_t = min(timeit.repeat(new_fn, number=number, repeat=5)) / number * 1e6
    print(f"| {name} | {old_t:.2f} | {new_t:.2f} | {old_t / new_t:.1f}x |")


def main():
    util.set_instance_id("bench01")
    print("| Helper (called per row / per tick) | old us/call | new us/call | speedup |")
    print("|---|---|---|---|")
    bench("get_app_root()", old_get_app_root, util.get_app_root)
    bench(
        "get_instance_state_path() (named instance)",
        lambda: old_get_instance_state_path("MAXBOT_INT28_IDLE.txt"),
        lambda: util.get_instance_state_path("MAXBOT_INT28_IDLE.txt"),
    )
    bench(
        "parse_keyword_string_to_array(area keywords)",
        lambda: old_parse_keyword_string_to_array('"VIP","1F 3280","搖滾區"'),
        lambda: util.parse_keyword_string_to_array('"VIP","1F 3280","搖滾區"'),
    )
    bench(
        "reset_row_text_if_match_keyword_exclude (default exclude list)",
        lambda: old_is_row_match_keyword(EXCLUDE, ROW),
        lambda: util.reset_row_text_if_match_keyword_exclude(CONFIG, ROW),
    )
    bench(
        "is_text_match_keyword('3,280;2,680', row)",
        lambda: old_is_text_match_keyword("3,280;2,680", ROW),
        lambda: util.is_text_match_keyword("3,280;2,680", ROW),
    )
    # clean up the instance dir the benchmark created
    inst = os.path.join(util.get_app_root(), "instances", "bench01")
    try:
        os.rmdir(inst)
    except OSError:
        pass


if __name__ == "__main__":
    main()
