"""settings.py config loading, migration and profile resolution."""

import json
import os

import pytest

import settings
import util


def test_default_config_shape():
    cfg = settings.get_default_config()
    for section in [
        "advanced",
        "kktix",
        "tixcraft",
        "date_auto_select",
        "area_auto_select",
        "ocr_captcha",
        "contact",
        "accounts",
        "cityline",
    ]:
        assert isinstance(cfg[section], dict), section
    assert cfg["homepage"] == settings.CONST_HOMEPAGE_DEFAULT
    assert cfg["ticket_number"] == 2
    assert cfg["advanced"]["server_port"] == settings.CONST_SERVER_PORT
    assert cfg["webdriver_type"] == settings.CONST_WEBDRIVER_TYPE_NODRIVER
    # Fresh configs must be JSON serialisable as-is.
    json.dumps(cfg)


def test_default_config_returns_fresh_object():
    a = settings.get_default_config()
    a["advanced"]["server_port"] = 1
    assert settings.get_default_config()["advanced"]["server_port"] == settings.CONST_SERVER_PORT


class TestMigrateConfig:
    def test_none_passthrough(self):
        assert settings.migrate_config(None) is None

    def test_moves_ocr_model_path(self):
        cfg = {"advanced": {"ocr_model_path": "custom/model"}}
        out = settings.migrate_config(cfg)
        assert out["ocr_captcha"]["path"] == "custom/model"
        assert "ocr_model_path" not in out["advanced"]

    def test_drops_removed_image_source(self):
        out = settings.migrate_config({"ocr_captcha": {"image_source": "canvas"}})
        assert "image_source" not in out["ocr_captcha"]
        assert out["ocr_captcha"]["path"] == "assets/model/universal"

    def test_moves_discount_code_from_accounts(self):
        out = settings.migrate_config({"accounts": {"discount_code": "ABC"}, "advanced": {}})
        assert out["advanced"]["discount_code"] == "ABC"
        assert "discount_code" not in out["accounts"]

    def test_existing_advanced_discount_code_wins(self):
        out = settings.migrate_config({"accounts": {"discount_code": "OLD"}, "advanced": {"discount_code": "NEW"}})
        assert out["advanced"]["discount_code"] == "NEW"

    def test_fills_missing_sections_and_scalars(self):
        out = settings.migrate_config({"homepage": "https://kktix.com"})
        default = settings.get_default_config()
        assert out["homepage"] == "https://kktix.com"  # user value kept
        assert out["ticket_number"] == default["ticket_number"]  # scalar filled
        assert out["kktix"] == default["kktix"]  # section filled
        assert out["advanced"]["server_port"] == settings.CONST_SERVER_PORT

    def test_user_values_inside_sections_are_preserved(self):
        out = settings.migrate_config({"kktix": {"max_dwell_time": 42}})
        assert out["kktix"]["max_dwell_time"] == 42
        assert out["kktix"]["auto_press_next_step_button"] is True

    def test_non_dict_section_is_replaced(self):
        out = settings.migrate_config({"kktix": "broken"})
        assert out["kktix"] == settings.get_default_config()["kktix"]

    def test_default_config_is_a_fixed_point(self):
        default = settings.get_default_config()
        assert settings.migrate_config(json.loads(json.dumps(default))) == default


class TestProfiles:
    @pytest.mark.parametrize(
        "name,ok",
        [
            ("default", True),
            ("kktix-2", True),
            ("A_b-9", True),
            ("a" * 32, True),
            ("", False),
            ("a" * 33, False),
            ("has space", False),
            ("../x", False),
            ("中文", False),
        ],
    )
    def test_is_valid_profile_name(self, name, ok):
        assert settings.is_valid_profile_name(name) is ok

    def test_default_profile_maps_to_settings_json(self, app_root):
        expected = os.path.join(str(app_root), settings.CONST_MAXBOT_CONFIG_FILE)
        assert settings.get_profile_filepath("") == expected
        assert settings.get_profile_filepath(settings.CONST_DEFAULT_PROFILE) == expected

    def test_named_profile_lives_under_profiles_dir(self, app_root):
        assert settings.get_profile_filepath("kktix") == os.path.join(str(app_root), "profiles", "kktix.json")

    def test_instance_state_filepath(self, app_root):
        assert settings.get_instance_state_filepath("", "f.txt") == os.path.join(str(app_root), "f.txt")
        assert settings.get_instance_state_filepath("x", "f.txt") == os.path.join(
            str(app_root), "instances", "x", "f.txt"
        )

    def test_list_profile_names_ignores_invalid_files(self, app_root):
        profiles = app_root / "profiles"
        profiles.mkdir()
        (profiles / "b.json").write_text("{}")
        (profiles / "a.json").write_text("{}")
        (profiles / "bad name.json").write_text("{}")
        (profiles / "notes.txt").write_text("")
        assert settings.list_profile_names() == ["default", "a", "b"]

    def test_list_profile_names_without_dir(self, app_root):
        assert settings.list_profile_names() == ["default"]

    def test_list_instance_ids_includes_orphan_instance_dirs(self, app_root):
        (app_root / "instances" / "cli-run").mkdir(parents=True)
        assert settings.list_instance_ids() == ["default", "cli-run"]


class TestLoadJson:
    def test_missing_file_yields_defaults(self, app_root):
        path, cfg = settings.load_json()
        assert path == os.path.join(str(app_root), "settings.json")
        assert cfg == settings.get_default_config()
        assert not os.path.exists(path)  # load never writes

    def test_corrupt_file_falls_back_to_defaults(self, app_root, capsys):
        (app_root / "settings.json").write_text("{not json", encoding="utf-8")
        _, cfg = settings.load_json()
        assert cfg == settings.get_default_config()
        assert "corrupted" in capsys.readouterr().out

    def test_existing_file_is_migrated(self, app_root):
        (app_root / "settings.json").write_text(json.dumps({"homepage": "https://tixcraft.com"}), encoding="utf-8")
        _, cfg = settings.load_json()
        assert cfg["homepage"] == "https://tixcraft.com"
        assert "kktix" in cfg

    def test_named_profile(self, app_root):
        (app_root / "profiles").mkdir()
        (app_root / "profiles" / "p1.json").write_text(json.dumps({"ticket_number": 4}), encoding="utf-8")
        path, cfg = settings.load_json("p1")
        assert path.endswith(os.path.join("profiles", "p1.json"))
        assert cfg["ticket_number"] == 4


class TestServerPort:
    @pytest.mark.parametrize("value", [16888, 8080, 65535, 1024])
    def test_valid_port_is_used(self, app_root, value):
        cfg = settings.get_default_config()
        cfg["advanced"]["server_port"] = value
        util.save_json(cfg, settings.get_profile_filepath(""))
        assert settings.get_server_port() == value

    @pytest.mark.parametrize("value", [80, 70000, "16888", None, -1])
    def test_invalid_port_falls_back(self, app_root, value):
        cfg = settings.get_default_config()
        cfg["advanced"]["server_port"] = value
        util.save_json(cfg, settings.get_profile_filepath(""))
        assert settings.get_server_port() == settings.CONST_SERVER_PORT


def test_pause_resume_stop_flags(app_root):
    idle = settings.get_instance_state_filepath("", settings.CONST_MAXBOT_INT28_FILE)
    settings.maxbot_idle()
    assert os.path.exists(idle)
    assert settings.get_instance_status("default")["paused"] is True
    settings.maxbot_resume()
    assert not os.path.exists(idle)
    assert settings.get_instance_status("default")["paused"] is False

    settings.maxbot_stop("worker")
    assert os.path.exists(os.path.join(str(app_root), "instances", "worker", settings.CONST_MAXBOT_INT28_QUIT_FILE))


def test_instance_status_reports_heartbeat_and_last_url(app_root):
    (app_root / settings.CONST_HEARTBEAT_FILE).write_text("")
    (app_root / settings.CONST_MAXBOT_LAST_URL_FILE).write_text("https://kktix.com/events/x\n")
    status = settings.get_instance_status("default")
    assert status == {"id": "default", "alive": True, "paused": False, "last_url": "https://kktix.com/events/x"}
