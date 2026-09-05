"""HTTP-level tests for the settings.py JSON API (the routes settings.js
talks to). Runs the real tornado Application on an ephemeral port with all
files rooted in a temp directory; no OCR engine, no browser."""

import json
import os

import pytest
import requests

import settings


@pytest.fixture
def api(settings_server):
    class Api:
        base = settings_server

        def get(self, path, **kw):
            return requests.get(self.base + path, timeout=5, **kw)

        def post(self, path, payload, **kw):
            data = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
            return requests.post(self.base + path, data=data, timeout=5, **kw)

        def delete(self, path, **kw):
            return requests.delete(self.base + path, timeout=5, **kw)

    return Api()


def test_version(api):
    r = api.get("/version")
    assert r.status_code == 200
    assert r.json() == {"version": settings.CONST_APP_VERSION}


def test_static_settings_page_is_served_without_cache(api):
    r = api.get("/settings.html")
    assert r.status_code == 200
    assert "Tickets Hunter" in r.text
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_load_returns_defaults_with_remote_url(api):
    cfg = api.get("/load").json()
    assert cfg["homepage"] == settings.CONST_HOMEPAGE_DEFAULT
    assert cfg["advanced"]["remote_url"] == f'"http://127.0.0.1:{settings.CONST_SERVER_PORT}/"'


def test_load_rejects_invalid_profile(api):
    r = api.get("/load", params={"profile": "bad name"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid profile name"


def test_save_then_load_round_trip(api, app_root):
    cfg = settings.get_default_config()
    cfg["homepage"] = "https://kktix.com/events/demo"
    cfg["ticket_number"] = 3
    r = api.post("/save", cfg)
    assert r.status_code == 200

    assert os.path.isfile(app_root / "settings.json")
    loaded = api.get("/load").json()
    assert loaded["homepage"] == "https://kktix.com/events/demo"
    assert loaded["ticket_number"] == 3


def test_save_clamps_minimum_intervals(api):
    cfg = settings.get_default_config()
    cfg["kktix"]["max_dwell_time"] = 5
    cfg["advanced"]["reset_browser_interval"] = 3
    api.post("/save", cfg)
    loaded = api.get("/load").json()
    assert loaded["kktix"]["max_dwell_time"] == 15
    assert loaded["advanced"]["reset_browser_interval"] == 20


def test_save_zero_intervals_stay_zero(api):
    cfg = settings.get_default_config()
    cfg["kktix"]["max_dwell_time"] = 0
    cfg["advanced"]["reset_browser_interval"] = 0
    api.post("/save", cfg)
    loaded = api.get("/load").json()
    assert loaded["kktix"]["max_dwell_time"] == 0
    assert loaded["advanced"]["reset_browser_interval"] == 0


def test_save_rejects_malformed_json(api, app_root):
    r = api.post("/save", "{not json")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == 1002
    assert not os.path.exists(app_root / "settings.json")


def test_save_rejects_invalid_profile_name(api):
    r = api.post("/save?profile=..", settings.get_default_config())
    assert r.status_code == 401
    assert r.json()["error"]["code"] == 1003


def test_reset_restores_defaults(api, app_root):
    cfg = settings.get_default_config()
    cfg["ticket_number"] = 4
    api.post("/save", cfg)

    r = api.get("/reset")
    assert r.status_code == 200
    assert r.json()["ticket_number"] == settings.get_default_config()["ticket_number"]
    assert api.get("/load").json()["ticket_number"] == 2


def test_reset_only_for_default_profile(api):
    r = api.get("/reset", params={"profile": "other"})
    assert r.status_code == 400


class TestProfilesApi:
    def test_lists_default_only_initially(self, api):
        body = api.get("/profiles").json()
        assert body["profiles"] == ["default"]
        assert body["details"][0]["name"] == "default"

    def test_create_load_delete(self, api, app_root):
        cfg = settings.get_default_config()
        cfg["homepage"] = "https://tixcraft.com/activity"
        r = api.post("/profiles", {"name": "tix", "config": cfg})
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True, "profile": "tix"}
        assert os.path.isfile(app_root / "profiles" / "tix.json")

        body = api.get("/profiles").json()
        assert body["profiles"] == ["default", "tix"]
        assert {"name": "tix", "homepage": "https://tixcraft.com/activity"} in body["details"]

        assert api.get("/load", params={"profile": "tix"}).json()["homepage"] == "https://tixcraft.com/activity"

        assert api.post("/profiles", {"name": "tix"}).status_code == 409

        assert api.delete("/profiles", params={"profile": "tix"}).json() == {"success": True}
        assert api.get("/profiles").json()["profiles"] == ["default"]

    def test_create_without_config_copies_current_settings(self, api):
        cfg = settings.get_default_config()
        cfg["ticket_number"] = 4
        api.post("/save", cfg)
        api.post("/profiles", {"name": "copy"})
        assert api.get("/load", params={"profile": "copy"}).json()["ticket_number"] == 4

    @pytest.mark.parametrize("name", ["default", "", "bad name", "x" * 33])
    def test_invalid_names_rejected(self, api, name):
        assert api.post("/profiles", {"name": name}).status_code == 400

    def test_delete_missing_is_404(self, api):
        assert api.delete("/profiles", params={"profile": "ghost"}).status_code == 404

    def test_delete_default_refused(self, api):
        assert api.delete("/profiles", params={"profile": "default"}).status_code == 400


class TestInstanceControl:
    def test_pause_resume_status(self, api):
        assert api.get("/status").json()["status"] is True
        assert api.get("/pause").json() == {"pause": True}
        assert api.get("/status").json()["status"] is False
        assert api.get("/resume").json() == {"resume": True}
        assert api.get("/status").json()["status"] is True

    def test_named_instance_isolated_from_default(self, api, app_root):
        api.get("/pause", params={"profile": "worker"})
        assert api.get("/status").json()["status"] is True
        assert api.get("/status", params={"profile": "worker"}).json()["status"] is False
        assert os.path.exists(app_root / "instances" / "worker" / settings.CONST_MAXBOT_INT28_FILE)

    def test_stop_writes_quit_flag(self, api, app_root):
        assert api.get("/stop").json() == {"stop": True}
        assert os.path.exists(app_root / settings.CONST_MAXBOT_INT28_QUIT_FILE)

    def test_instances_overview(self, api, app_root):
        (app_root / settings.CONST_MAXBOT_LAST_URL_FILE).write_text("https://kktix.com/x\n")
        rows = api.get("/instances").json()["instances"]
        assert rows[0]["id"] == "default"
        assert rows[0]["last_url"] == "https://kktix.com/x"
        assert rows[0]["alive"] is False

    @pytest.mark.parametrize("path", ["/status", "/pause", "/resume", "/stop", "/run", "/question"])
    def test_invalid_profile_rejected_everywhere(self, api, path):
        assert api.get(path, params={"profile": "no way"}).status_code == 400


def test_question_endpoint(api, app_root):
    assert api.get("/question").json() == {"exists": False, "question": ""}
    (app_root / settings.CONST_MAXBOT_QUESTION_FILE).write_text("  請輸入驗證碼  ", encoding="utf-8")
    assert api.get("/question").json() == {"exists": True, "question": "請輸入驗證碼"}


def test_sendkey_writes_token_answer_file(api, app_root):
    r = api.post("/sendkey", {"token": "MAXBOT_ONLINE_ANSWER", "answer": "abcd"})
    assert r.json() == {"return": True}
    tmp = app_root / "MAXBOT_ONLINE_ANSWER.tmp"
    assert tmp.is_file()
    assert json.loads(tmp.read_text(encoding="utf-8"))["answer"] == "abcd"


def test_ocr_without_engine_returns_empty_answer(api):
    r = api.post("/ocr", {"image_data": ""})
    assert r.json() == {"answer": ""}
    assert api.post("/ocr", "garbage").json() == {"answer": ""}


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"webhook_url": ""}, "webhook URL is empty"),
        ({"webhook_url": "http://discord.com/api/webhooks/1/x"}, "only HTTPS URLs are allowed"),
        ({"webhook_url": "https://evil.example/api/webhooks/1/x"}, "only Discord webhook URLs are allowed"),
        ({"webhook_url": "https://discord.com/other/1/x"}, "invalid Discord webhook URL format"),
    ],
)
def test_discord_webhook_validation_never_hits_network(api, payload, message):
    r = api.post("/test_discord_webhook", payload)
    assert r.json() == {"success": False, "message": message}


@pytest.mark.parametrize(
    "payload,message",
    [
        ({"bot_token": "", "chat_id": "1"}, "Bot Token is empty"),
        ({"bot_token": "not-a-token", "chat_id": "1"}, "Bot Token format invalid"),
        ({"bot_token": "123:abc", "chat_id": ""}, "Chat ID is empty"),
        ({"bot_token": "123:abc", "chat_id": "1,abc"}, "Chat ID format invalid: abc"),
    ],
)
def test_telegram_validation_never_hits_network(api, payload, message):
    r = api.post("/test_telegram", payload)
    assert r.json() == {"success": False, "message": message}
