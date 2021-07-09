import datetime
import json

from tornado.testing import AsyncHTTPTestCase

from configurable_http_proxy.configproxy import PythonProxy
from configurable_http_proxy_test.testutil import pytest_regex


class TestAPI(AsyncHTTPTestCase):
    def get_app(self):
        self.proxy = PythonProxy({"auth_token": "secret"})
        self.proxy.add_route("/", {"target": "http://127.0.0.1:54321"})
        return self.proxy.api_app

    def fetch(self, path, raise_error=True, with_auth=True, **kwargs):
        headers = kwargs.pop("headers", {})
        if with_auth:
            headers["Authorization"] = "token secret"
        return super().fetch(path, raise_error=raise_error, headers=headers, **kwargs)

    def test_basic_proxy(self):
        assert self.proxy.default_target is None
        route = self.proxy.target_for_req(None, "/")
        assert route == {
            "prefix": "/",
            "target": "http://127.0.0.1:54321",
        }

    def test_default_target_for_random_url(self):
        # assert self.proxy.default_target is None
        target = self.proxy.target_for_req(None, "/any/random/url")
        assert target == {
            "prefix": "/",
            "target": "http://127.0.0.1:54321",
        }

    def test_default_target_for_root(self):
        # assert self.proxy.default_target is None
        target = self.proxy.target_for_req(None, "/")
        assert target == {
            "prefix": "/",
            "target": "http://127.0.0.1:54321",
        }

    def test_without_auth(self):
        resp = self.fetch("/api/routes", with_auth=False, raise_error=False, method="GET")
        assert resp.code == 403
        resp = self.fetch("/api/routes", with_auth=False, raise_error=False, method="POST", body="")
        assert resp.code == 403
        resp = self.fetch("/api/routes", with_auth=False, raise_error=False, method="DELETE")
        assert resp.code == 403

    def test_get_routes(self):
        resp = self.fetch("/api/routes")
        reply = json.loads(resp.body)
        assert reply == {
            "/": {
                "last_activity": pytest_regex(".*"),
                "target": "http://127.0.0.1:54321",
            }
        }

    def test_get_single_route(self):
        self.proxy.add_route("/path", {"target": "http://127.0.0.1:12345"})
        resp = self.fetch("/api/routes/path")
        reply = json.loads(resp.body)
        assert reply == {
            "last_activity": pytest_regex(".*"),
            "target": "http://127.0.0.1:12345",
        }

    def test_get_single_route_missing(self):
        resp = self.fetch("/api/routes/path", raise_error=False)
        assert resp.code == 404

    def test_post_create_new_route(self):
        resp = self.fetch(
            "/api/routes/path", method="POST", body=json.dumps({"target": "http://127.0.0.1:12345"})
        )
        assert resp.code == 201
        route = self.proxy.get_route("/path")
        assert route["target"] == "http://127.0.0.1:12345"

    def test_post_create_new_route(self):
        resp = self.fetch(
            "/api/routes/path", method="POST", body=json.dumps({"target": "http://127.0.0.1:12345"})
        )
        assert resp.code == 201
        route = self.proxy.get_route("/path")
        assert route["target"] == "http://127.0.0.1:12345"
        assert isinstance(route["last_activity"], datetime.datetime)

    def test_post_create_new_route_with_urlescape(self):
        resp = self.fetch(
            "/api/routes/foo%40bar", method="POST", body=json.dumps({"target": "http://127.0.0.1:12345"})
        )
        assert resp.code == 201
        route = self.proxy.get_route("/foo@bar")
        assert route["target"] == "http://127.0.0.1:12345"
        assert isinstance(route["last_activity"], datetime.datetime)

        target = self.proxy.target_for_req(None, "/foo@bar/path")
        assert target["target"] == "http://127.0.0.1:12345"

    def test_post_create_new_root_route(self):
        resp = self.fetch(
            "/api/routes/", method="POST", body=json.dumps({"target": "http://127.0.0.1:12345"})
        )
        assert resp.code == 201
        route = self.proxy.get_route("/")
        assert route["target"] == "http://127.0.0.1:12345"
        assert isinstance(route["last_activity"], datetime.datetime)

    def test_delete_route(self):
        self.proxy.add_route("/path", {"target": "http://127.0.0.1:12345"})

        route = self.proxy.get_route("/path")
        assert route["target"] == "http://127.0.0.1:12345"
        assert isinstance(route["last_activity"], datetime.datetime)

        resp = self.fetch("/api/routes/path", method="DELETE")
        assert resp.code == 204

        route = self.proxy.get_route("/path")
        assert route is None

    def test_get_routes_with_inactive_since_invalid(self):
        resp = self.fetch("/api/routes?inactiveSince=endoftheuniverse", raise_error=False)
        assert resp.code == 400

    def test_get_routes_with_inactive_since(self):
        now = datetime.datetime.now()
        yesterday = now - datetime.timedelta(days=1)
        long_ago = datetime.datetime(2020, 1, 1)
        hour_ago = now - datetime.timedelta(hours=1)
        hour_from_now = now + datetime.timedelta(hours=1)

        self.proxy.add_route("/today", {"target": "http://127.0.0.1:12345/today"})
        self.proxy._routes.update("/today", {"last_activity": now})
        self.proxy.add_route("/yesterday", {"target": "http://127.0.0.1:12345/yesterday"})
        self.proxy._routes.update("/yesterday", {"last_activity": yesterday})

        resp = self.fetch(f"/api/routes?inactiveSince={long_ago.isoformat()}")
        reply = json.loads(resp.body)
        assert reply == {}

        resp = self.fetch(f"/api/routes?inactiveSince={hour_ago.isoformat()}")
        reply = json.loads(resp.body)
        assert set(reply.keys()) == {'/yesterday'}

        resp = self.fetch(f"/api/routes?inactiveSince={hour_from_now.isoformat()}")
        reply = json.loads(resp.body)
        assert set(reply.keys()) == {'/', '/today', '/yesterday'}
