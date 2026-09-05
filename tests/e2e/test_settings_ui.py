"""End-to-end: real settings.py process + real Chromium via Playwright."""

import json

import pytest
import requests
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

SAVED_MESSAGES = ("Saved", "已存檔")


def wait_for_saved_message(page: Page):
    page.wait_for_function(
        "msgs => msgs.includes(document.querySelector('#run_btn_pressed_message').innerText)",
        arg=list(SAVED_MESSAGES),
        timeout=10_000,
    )


def test_server_reports_version_and_serves_ui(settings_process):
    version = requests.get(settings_process + "/version", timeout=5).json()["version"]
    assert version.startswith("TicketsHunter")
    html = requests.get(settings_process + "/settings.html", timeout=5)
    assert html.status_code == 200
    assert 'id="save_btn"' in html.text


def test_page_loads_defaults_into_form(settings_page: Page):
    expect(settings_page).to_have_title("Tickets Hunter - 多平台搶票自動化系統")
    expect(settings_page.locator("#homepage")).to_have_value("about:blank")
    expect(settings_page.locator("#ticket_number")).to_have_value("2")
    expect(settings_page.locator("#save_btn")).to_be_visible()
    expect(settings_page.locator("#run_btn")).to_be_visible()


def test_save_persists_to_settings_json(settings_page: Page, settings_process, app_root):
    homepage = "https://kktix.com/events/e2e-demo"
    settings_page.fill("#homepage", homepage)
    settings_page.click("#save_btn")

    # settings.js shows a transient "Saved" / "已存檔" message after /save succeeds.
    wait_for_saved_message(settings_page)

    on_disk = json.loads((app_root / "settings.json").read_text(encoding="utf-8"))
    assert on_disk["homepage"] == homepage
    assert on_disk["ticket_number"] == 2  # untouched fields survive the round trip

    via_api = requests.get(settings_process + "/load", timeout=5).json()
    assert via_api["homepage"] == homepage

    # Reload: the form must come back from the saved file, not browser state.
    settings_page.reload()
    settings_page.wait_for_function("document.querySelector('#homepage').value !== ''")
    expect(settings_page.locator("#homepage")).to_have_value(homepage)


def test_reset_button_restores_defaults(settings_page: Page, app_root):
    settings_page.fill("#homepage", "https://tixcraft.com/activity/detail/x")
    settings_page.click("#save_btn")
    wait_for_saved_message(settings_page)
    assert json.loads((app_root / "settings.json").read_text(encoding="utf-8"))["homepage"].startswith(
        "https://tixcraft"
    )

    settings_page.click("#reset_btn")  # confirm() dialogs are auto-accepted by the fixture
    settings_page.wait_for_function("document.querySelector('#homepage').value === 'about:blank'", timeout=10_000)
    on_disk = json.loads((app_root / "settings.json").read_text(encoding="utf-8"))
    assert on_disk["homepage"] == "about:blank"
