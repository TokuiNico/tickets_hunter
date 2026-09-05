"""Shared pytest fixtures.

`src/` is on sys.path via `[tool.pytest.ini_options] pythonpath` in
pyproject.toml, so tests import the application modules directly
(`import util`, `import settings`, ...).
"""

import asyncio
import threading

import pytest
import tornado.httpserver
import tornado.netutil

import util


@pytest.fixture
def app_root(tmp_path, monkeypatch):
    """Redirect every config/state file (settings.json, profiles/, instances/,
    pause flags...) into a throw-away directory.

    util.get_app_root() honours TICKETS_HUNTER_APP_ROOT; its lru_cache and the
    per-instance directory cache are cleared so the override takes effect.
    """
    monkeypatch.setenv("TICKETS_HUNTER_APP_ROOT", str(tmp_path))
    util.get_app_root.cache_clear()
    util._get_instance_dir.cache_clear()
    yield tmp_path
    util.get_app_root.cache_clear()
    util._get_instance_dir.cache_clear()


class TornadoServerThread:
    """Run a tornado Application on an ephemeral 127.0.0.1 port in a
    background thread with its own event loop."""

    def __init__(self, app):
        self._sockets = tornado.netutil.bind_sockets(0, "127.0.0.1")
        self.port = self._sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._app = app
        self._ready = threading.Event()
        self._loop = None
        self._stop = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        server = tornado.httpserver.HTTPServer(self._app)
        server.add_sockets(self._sockets)
        self._stop = asyncio.Event()
        self._ready.set()
        self._loop.run_until_complete(self._stop.wait())
        server.stop()
        self._loop.run_until_complete(server.close_all_connections())
        self._loop.close()

    def start(self):
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("tornado test server did not start")
        return self

    def stop(self):
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(10)


@pytest.fixture
def settings_server(app_root):
    """The real settings.py Application (no OCR engine) on an ephemeral port.

    Yields the base URL. Every request goes through the same tornado handlers
    the desktop UI talks to, with all files rooted in `app_root`.
    """
    import settings

    server = TornadoServerThread(settings.make_app()).start()
    try:
        yield server.base_url
    finally:
        server.stop()
