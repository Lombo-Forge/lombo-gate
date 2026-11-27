"""A fake Seerr, Sonarr and webhook on localhost, so tests need no real server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest


def tv(rid, seasons, who="Sam", is4k=False):
    return {
        "id": rid,
        "type": "tv",
        "is4k": is4k,
        "media": {"mediaType": "tv", "tmdbId": 1},
        "seasons": [{"seasonNumber": n} for n in seasons],
        "requestedBy": {"displayName": who},
    }


class Fake:
    def __init__(self):
        self.calls: list[dict] = []
        self.key = "good-key"
        self.pending: list[dict] = []
        self.users = [{"id": 1, "displayName": "Boss", "permissions": 2}]
        self.default_permissions = 32
        self.show = {
            "name": "Some Show",
            "seasons": [{"seasonNumber": n, "episodeCount": 22} for n in range(11)],
            "episodeRunTime": [42],
        }
        self.definitions = [{"quality": {"name": "WEBDL-1080p"}, "preferredSize": 60, "maxSize": 100}]
        self.redirect = False
        self.hook_status = 204
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, payload=None, headers=()):
                data = json.dumps(payload if payload is not None else {}).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                for k, v in headers:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.calls.append({"method": "GET", "path": self.path})
                url = urlsplit(self.path)
                if self.headers.get("X-Api-Key") != outer.key:
                    return self._reply(401)
                skip = int(parse_qs(url.query).get("skip", ["0"])[0])
                if url.path == "/api/v1/request":
                    return self._reply(200, {"results": outer.pending[skip : skip + 100]})
                if url.path == "/api/v1/user":
                    return self._reply(200, {"results": outer.users[skip : skip + 100]})
                if url.path == "/api/v1/settings/main":
                    return self._reply(200, {"defaultPermissions": outer.default_permissions})
                if url.path == "/api/v1/tv/1":
                    return self._reply(200, outer.show)
                if url.path == "/api/v3/qualitydefinition":
                    return self._reply(200, outer.definitions)
                return self._reply(404)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
                outer.calls.append({"method": "POST", "path": self.path, "body": body.decode()})
                if self.path == "/hook":
                    return self._reply(outer.hook_status)
                if outer.redirect:
                    return self._reply(302, headers=[("Location", "/api/v1/settings/main")])
                return self._reply(200)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def posts(self):
        return [c["path"] for c in self.calls if c["method"] == "POST"]


@pytest.fixture
def fake():
    f = Fake()
    yield f
    f.server.shutdown()


@pytest.fixture
def env(fake, tmp_path):
    return {
        "LOMBO_GATE_SEERR_URL": fake.url,
        "LOMBO_GATE_SEERR_API_KEY": "good-key",
        "LOMBO_GATE_SONARR_URL": fake.url,
        "LOMBO_GATE_SONARR_API_KEY": "good-key",
        "LOMBO_GATE_WEBHOOK_URL": fake.url + "/hook",
        "LOMBO_GATE_STATE_FILE": str(tmp_path / "state.json"),
    }
