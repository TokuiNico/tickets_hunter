"""Keyword parsing / matching helpers in util.py.

These are the pure functions every platform module funnels the user's
date/area/exclude keywords through, so their edge cases (quotes, semicolons,
commas inside prices, full-width spaces, AND-groups) are pinned here.
"""

import pytest

import util


@pytest.mark.parametrize(
    "json_value,display",
    [
        ('"AA BB","CC","DD"', "AA BB;CC;DD"),
        ('"3,280","2,680"', "3,280;2,680"),  # commas inside a keyword survive
        ("'AA','BB'", "AA;BB"),
        ('"single"', "single"),
        ("", ""),
    ],
)
def test_format_keyword_for_display(json_value, display):
    assert util.format_keyword_for_display(json_value) == display


@pytest.mark.parametrize(
    "user_input,json_value",
    [
        ("AA BB;CC;DD", '"AA BB","CC","DD"'),
        ("3,280;2,680", '"3,280","2,680"'),
        (" VIP ; 1F ;; ", '"VIP","1F"'),  # whitespace and empty items dropped
        ("VIP", '"VIP"'),
        ('"VIP"', '"VIP"'),  # idempotent on already-quoted input
        ('["VIP","1F"]', '"VIP,1F"'),  # array form: brackets stripped, no re-split on comma
        ("", ""),
    ],
)
def test_format_config_keyword_for_json(user_input, json_value):
    assert util.format_config_keyword_for_json(user_input) == json_value


def test_display_and_json_round_trip():
    original = '"AA BB","3,280","CC"'
    assert util.format_config_keyword_for_json(util.format_keyword_for_display(original)) == original


@pytest.mark.parametrize(
    "text,expected",
    [
        ("<b>VIP</b> <span>1F</span>", "VIP 1F"),
        ("  plain  ", "plain"),
        (None, ""),
        ("", ""),
    ],
)
def test_remove_html_tags(text, expected):
    assert util.remove_html_tags(text) == expected


@pytest.mark.parametrize(
    "s,first,last,expected",
    [
        ("id=123&x", "id=", "&", "123"),
        ("no markers", "[", "]", ""),
        ("[open only", "[", "]", ""),
    ],
)
def test_find_between(s, first, last, expected):
    assert util.find_between(s, first, last) == expected


def test_format_keyword_string_strips_full_width_space_only():
    assert util.format_keyword_string("VIP　Rock") == "VIPRock"
    assert util.format_keyword_string("VIP Rock") == "VIP Rock"
    assert util.format_keyword_string("") == ""
    assert util.format_keyword_string(None) is None


def test_format_quota_string_normalises_brackets():
    assert util.format_quota_string("「A」『B』(C)[D]") == "【A】【B】【C】【D】"


@pytest.mark.parametrize(
    "kw,row,expected",
    [
        ("", "anything", True),  # no keyword: everything matches
        ('"VIP"', "", True),  # legacy: empty row text counts as match
        ('"VIP"', "VIP Zone", True),
        ('"VIP"', "General", False),
        ('"VIP 1F"', "1F VIP seats", True),  # space = AND, order independent
        ('"VIP 1F"', "2F VIP seats", False),
        ('"VIP","1F"', "1F only", True),  # comma = OR
        ('"VIP"', "VIP　Zone", True),  # full-width space in row is stripped
        ('""', "anything", True),  # empty item matches everything (same as is_text_match_keyword)
    ],
)
def test_is_row_match_keyword(kw, row, expected):
    assert util.is_row_match_keyword(kw, row) is expected


@pytest.mark.parametrize(
    "row,expected",
    [
        ("輪椅席", True),
        ("Restricted View seat", True),
        ("Restricted　View seat", True),  # full-width space stripped by format_keyword_string
        ("搖滾區 3,280", False),
        ("", True),  # legacy semantics: empty row text counts as excluded
    ],
)
def test_reset_row_text_if_match_keyword_exclude(row, expected):
    config_dict = {"keyword_exclude": '"輪椅","身障","Restricted View"'}
    assert util.reset_row_text_if_match_keyword_exclude(config_dict, row) is expected


def test_reset_row_text_with_empty_exclude_never_matches():
    assert util.reset_row_text_if_match_keyword_exclude({"keyword_exclude": ""}, "輪椅席") is False


@pytest.mark.parametrize(
    "char,expected",
    [
        ("一", 1),
        ("貳", 2),
        ("③", 3),
        ("４", 4),
        ("five", 5),
        ("零", 0),
        ("x", None),
    ],
)
def test_chinese_numeric_to_int(char, expected):
    assert util.chinese_numeric_to_int(char) == expected


def test_normalize_chinese_numeric_keeps_only_digits():
    assert util.normalize_chinese_numeric("第一二區") == "12"
    assert util.normalize_chinese_numeric("A區") == ""


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Area 12A seat", "12"),
        ("no digits", ""),
        ("3,280 元", "3"),  # stops at the first non-digit
    ],
)
def test_find_continuous_number(text, expected):
    assert util.find_continuous_number(text) == expected


def test_find_continuous_text():
    assert util.find_continuous_text("--abc123 def") == "abc123"
