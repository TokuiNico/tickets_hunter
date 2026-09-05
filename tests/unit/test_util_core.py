"""Selection-mode arithmetic, instance-id state paths, app root override
and DebugLogger behaviour in util.py."""

import os
import random

import pytest

import util


class TestGetTargetIndexByMode:
    def test_empty_list_returns_none(self):
        assert util.get_target_index_by_mode(0, util.CONST_FROM_TOP_TO_BOTTOM) is None
        assert util.get_target_index_by_mode(-1, util.CONST_RANDOM) is None

    @pytest.mark.parametrize("mode", [util.CONST_FROM_TOP_TO_BOTTOM, "from_top_to_bottom", "", None, "bogus"])
    def test_top_to_bottom_and_fallbacks_pick_first(self, mode):
        assert util.get_target_index_by_mode(5, mode) == 0

    @pytest.mark.parametrize("mode", [util.CONST_FROM_BOTTOM_TO_TOP, "from_bottom_to_top"])
    def test_bottom_to_top_picks_last(self, mode):
        assert util.get_target_index_by_mode(5, mode) == 4

    def test_center(self):
        assert util.get_target_index_by_mode(5, util.CONST_CENTER) == 2
        assert util.get_target_index_by_mode(4, util.CONST_CENTER) == 2
        assert util.get_target_index_by_mode(1, util.CONST_CENTER) == 0

    def test_random_stays_in_range(self):
        random.seed(1234)
        for _ in range(200):
            assert 0 <= util.get_target_index_by_mode(7, util.CONST_RANDOM) <= 6


class TestGetTargetItemFromMatchedList:
    items = ["a", "b", "c", "d"]

    def test_empty_returns_none(self):
        assert util.get_target_item_from_matched_list([], util.CONST_CENTER) is None

    def test_modes(self):
        assert util.get_target_item_from_matched_list(self.items, util.CONST_FROM_TOP_TO_BOTTOM) == "a"
        assert util.get_target_item_from_matched_list(self.items, util.CONST_FROM_BOTTOM_TO_TOP) == "d"
        assert util.get_target_item_from_matched_list(self.items, util.CONST_CENTER) == "c"
        assert util.get_target_item_from_matched_list(self.items, util.CONST_RANDOM) in self.items


class TestAppRoot:
    def test_env_override(self, app_root):
        assert util.get_app_root() == str(app_root)

    def test_env_override_ignored_when_not_a_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TICKETS_HUNTER_APP_ROOT", str(tmp_path / "missing"))
        util.get_app_root.cache_clear()
        try:
            assert util.get_app_root() == os.path.dirname(os.path.abspath(util.__file__))
        finally:
            util.get_app_root.cache_clear()

    def test_default_is_src_directory(self, monkeypatch):
        monkeypatch.delenv("TICKETS_HUNTER_APP_ROOT", raising=False)
        util.get_app_root.cache_clear()
        try:
            root = util.get_app_root()
        finally:
            util.get_app_root.cache_clear()
        assert os.path.isfile(os.path.join(root, "util.py"))
        assert os.path.isdir(os.path.join(root, "www"))


class TestInstanceState:
    @pytest.fixture(autouse=True)
    def _reset_instance(self):
        yield
        util.set_instance_id(util.CONST_DEFAULT_INSTANCE_ID)

    def test_default_instance_uses_root_paths(self, app_root):
        assert util.get_instance_id() == util.CONST_DEFAULT_INSTANCE_ID
        assert util.get_instance_state_path("x.txt") == os.path.join(str(app_root), "x.txt")

    def test_named_instance_gets_its_own_directory(self, app_root):
        assert util.set_instance_id("kktix-2") is True
        path = util.get_instance_state_path("x.txt")
        assert path == os.path.join(str(app_root), "instances", "kktix-2", "x.txt")
        assert os.path.isdir(os.path.dirname(path))

    @pytest.mark.parametrize("bad", ["", None, "has space", "a" * 33, "../etc", "中文"])
    def test_invalid_instance_ids_are_rejected(self, bad):
        assert util.set_instance_id(bad) is False
        assert util.get_instance_id() == util.CONST_DEFAULT_INSTANCE_ID


class TestDebugLogger:
    def test_disabled_by_default(self, capsys):
        logger = util.create_debug_logger()
        assert logger.enabled is False
        logger.log("hidden")
        assert capsys.readouterr().out == ""

    def test_enabled_via_config_verbose(self, capsys):
        logger = util.create_debug_logger({"advanced": {"verbose": True}})
        assert logger.enabled is True
        logger.log("a", 1, None)
        assert capsys.readouterr().out == "a 1 None\n"

    def test_explicit_flag_wins_over_config(self):
        assert util.create_debug_logger({"advanced": {"verbose": True}}, enabled=False).enabled is False
        assert util.create_debug_logger(None, enabled=True).enabled is True

    def test_get_debug_mode_tolerates_garbage(self):
        assert util.get_debug_mode(None) is False
        assert util.get_debug_mode("not a dict") is False
        assert util.get_debug_mode({}) is False


def test_save_json_round_trip(tmp_path):
    target = tmp_path / "settings.json"
    util.save_json({"homepage": "https://kktix.com", "中文": "值"}, str(target))
    import json

    assert json.loads(target.read_text(encoding="utf-8")) == {"homepage": "https://kktix.com", "中文": "值"}


def test_force_remove_file_is_idempotent(tmp_path):
    target = tmp_path / "flag.txt"
    target.write_text("")
    util.force_remove_file(str(target))
    util.force_remove_file(str(target))
    assert not target.exists()
