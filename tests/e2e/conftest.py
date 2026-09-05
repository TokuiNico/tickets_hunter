"""End-to-end fixtures: boot `python src/settings.py` as a real subprocess
(the same entry point users run) on a free port, with all state files
rooted in a temp directory, then drive the UI with Playwright.

Run with:  uv run pytest tests/e2e
Needs a Playwright Chromium:  uv run playwright install chromium
"""

import os
import socket
import subprocess
import sys
import time

import pytest
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import settings  # noqa: E402
import util  # noqa: E402


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    # CI containers run as root; Chromium refuses to start sandboxed there.
    args = {**browser_type_launch_args, "args": ["--no-sandbox"]}
    # Offline / pre-provisioned machines: point at an existing Chromium
    # instead of the one `playwright install chromium` would download.
    executable = os.environ.get("TICKETS_HUNTER_E2E_CHROMIUM")
    if executable:
        args["executable_path"] = executable
    return args


@pytest.fixture
def app_root(tmp_path):
    """Temp directory the settings server treats as its app root."""
    return tmp_path


@pytest.fixture
def settings_process(app_root):
    """Start src/settings.py as a subprocess and yield its base URL."""
    port = _free_port()
    config = settings.get_default_config()
    config["advanced"]["server_port"] = port
    util.save_json(config, os.path.join(str(app_root), settings.CONST_MAXBOT_CONFIG_FILE))

    env = dict(os.environ)
    env["TICKETS_HUNTER_APP_ROOT"] = str(app_root)
    env["TICKETS_HUNTER_NO_BROWSER"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        [sys.executable, os.path.join(SRC, "settings.py")],
        cwd=SRC,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60  # first start loads the OCR model
    try:
        while time.time() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"settings.py exited early (code {proc.returncode}):\n{output}")
            try:
                if requests.get(base_url + "/version", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.2)
        else:
            raise RuntimeError("settings.py did not start listening within 60s")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(10)


@pytest.fixture
def settings_page(page, settings_process):
    """Playwright page with the settings UI loaded and its /load call done."""
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(settings_process + "/settings.html")
    # The form is populated asynchronously from /load; homepage is the first field filled.
    page.wait_for_function("document.querySelector('#homepage') && document.querySelector('#homepage').value !== ''")
    # The UI opens on the read-me tab; the editable fields live under "基本設定".
    page.click("#home-tab")
    page.wait_for_selector("#homepage", state="visible")
    return page
