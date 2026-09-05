"""Behavioural tests for the memoized util helpers.

The optimisation replaced per-call json.loads / os.makedirs / abspath work
with caches; these tests pin the observable behaviour to the pre-cache
semantics (including the odd corners: invalid JSON, empty strings, mutation
safety, instance-id switching).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import util  # noqa: E402


def _old_parse(keyword_string):
    if not keyword_string or not keyword_string.strip():
        return []
    try:
        return json.loads("[" + keyword_string + "]")
    except Exception:
        return []


@pytest.mark.parametrize("kw", [
    '', '   ', '"VIP"', '"VIP","1F"', '"VIP Rock Area"', 'invalid', '"unterminated',
    '"3,280","2,680"', '["a","b"],"c"', '"搖滾區","看台"',
])
def test_parse_keyword_string_to_array_matches_old(kw):
    assert util.parse_keyword_string_to_array(kw) == _old_parse(kw)


def test_parse_keyword_string_to_array_returns_fresh_list():
    a = util.parse_keyword_string_to_array('"VIP","1F"')
    a.append("mutated")
    b = util.parse_keyword_string_to_array('"VIP","1F"')
    assert b == ["VIP", "1F"]


@pytest.mark.parametrize("kw,text,expected", [
    ("", "anything", True),
    ("VIP", "", True),
    ("VIP", "VIP zone", True),
    ("VIP", "General", False),
    ("3,280;2,680", "Area B 2,680", True),
    ("3,280;2,680", "Area B 1,980", False),
    ('"1280 一般"', "1280 一般票", True),
    ('"1280 一般"', "1280 學生票", False),
    ('"VIP","1F"', "1F seats", True),
    ('""', "anything", True),           # empty item matches all
    ('not json"', "anything", False),   # unparsable -> no match
])
def test_is_text_match_keyword(kw, text, expected):
    assert util.is_text_match_keyword(kw, text) is expected


def test_is_text_match_keyword_repeated_calls_are_stable():
    for _ in range(3):
        assert util.is_text_match_keyword("3,280;2,680", "Area 2,680") is True
        assert util.is_text_match_keyword("3,280;2,680", "Area 9,999") is False


EXCLUDE = "\"輪椅\",\"身障\",\"身心\",\"障礙\",\"愛心\",\"Restricted View\",\"燈柱遮蔽\",\"視線不完整\""


@pytest.mark.parametrize("row,expected", [
    ("2F 區域 B 3,280 熱賣中", False),
    ("輪椅席 1,200", True),
    ("Restricted View seat", True),
    ("Restricted　View seat", True),  # full-width space stripped by format_keyword_string
    ("", True),  # legacy semantics: empty row text counts as excluded
])
def test_reset_row_text_if_match_keyword_exclude(row, expected):
    assert util.reset_row_text_if_match_keyword_exclude({"keyword_exclude": EXCLUDE}, row) is expected


def test_reset_row_text_if_match_keyword_exclude_empty_config():
    assert util.reset_row_text_if_match_keyword_exclude({"keyword_exclude": ""}, "輪椅") is False


def test_is_row_match_keyword_and_logic():
    assert util.is_row_match_keyword('"VIP 1F"', "1F VIP zone") is True
    assert util.is_row_match_keyword('"VIP 1F"', "2F VIP zone") is False


def test_get_app_root_is_src_dir():
    root = util.get_app_root()
    assert os.path.isdir(root)
    assert os.path.exists(os.path.join(root, "util.py"))
    assert util.get_app_root() == root


def test_get_instance_state_path_default_and_named(tmp_path, monkeypatch):
    # redirect the app root into tmp so the test does not touch src/instances
    util.get_app_root.cache_clear()
    monkeypatch.setattr(util, "get_app_root", lambda: str(tmp_path))
    util._get_instance_dir.cache_clear()
    try:
        util._instance_id = util.CONST_DEFAULT_INSTANCE_ID
        assert util.get_instance_state_path("x.txt") == os.path.join(str(tmp_path), "x.txt")

        assert util.set_instance_id("inst-A") is True
        p = util.get_instance_state_path("x.txt")
        assert p == os.path.join(str(tmp_path), "instances", "inst-A", "x.txt")
        assert os.path.isdir(os.path.dirname(p))

        # switching instance id must not serve the stale cached directory
        assert util.set_instance_id("inst_B") is True
        p2 = util.get_instance_state_path("x.txt")
        assert p2.endswith(os.path.join("instances", "inst_B", "x.txt"))
        assert os.path.isdir(os.path.dirname(p2))

        assert util.set_instance_id("bad id!") is False
        assert util.get_instance_id() == "inst_B"
    finally:
        util._instance_id = util.CONST_DEFAULT_INSTANCE_ID
        util._get_instance_dir.cache_clear()
        monkeypatch.undo()
        util.get_app_root.cache_clear()
