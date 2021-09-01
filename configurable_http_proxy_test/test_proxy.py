import datetime
import json
import os

import pytest
from tornado.httpclient import HTTPClientError, HTTPRequest
from tornado.httpserver import HTTPServer
from tornado.testing import AsyncHTTPTestCase, bind_unused_port, get_async_test_timeout, gen_test
from tornado.web import Application, RequestHandler
from tornado.websocket import WebSocketHandler, websocket_connect

from configurable_http_proxy.configproxy import PythonProxy
from configurable_http_proxy_test.testutil import RESOURCES_PATH, pytest_regex


class TargetHandler(WebSocketHandler):
    def initialize(self, target=None, path=None, **kwargs):
        super().initialize(**kwargs)
        self.target = target
        self.path = path

    async def get(self, path=None):
        if self.request.headers.get("Upgrade", "").lower() == "websocket":
            await WebSocketHandler.get(self, path)
            return

        reply = {
            "target": self.target,
            "path": self.path,
            "url": self.request.uri,
            "headers": dict(self.request.headers.get_all()),
        }
        self.set_status(200)
        self.set_header("Content-Type", "application/json")
        if self.get_argument("with_set_cookie"):
            # Values that set-cookie can take:
            # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
            values = {
                "Secure": "",
                "HttpOnly": "",
                "SameSite": "None",
                "Path": "/",
                "Domain": "example.com",
                "Max-Age": "999999",
                "Expires": "Fri, 01 Oct 2020 06:12:16 GMT",  # .strftime('%a, %d %b %Y %H:%M:%S %Z')
            }
            self.add_header("Set-Cookie", "key=val")
            for name, val in values.items():
                self.add_header("Set-Cookie", f"{name}_key=val; {name}={val}")
            combined = "; ".join((f"{name}={val}" for name, val in values.items()))
            self.add_header("Set-Cookie", f"combined_key=val; {combined}")

        self.write(json.dumps(reply))
        self.finish()

    def open(self, path=None):
        self.write_message("connected")

    def on_message(self, message):
        reply = {
            "target": self.target,
            "path": self.path,
            "message": message,
        }
        self.write_message(json.dumps(reply))


class RedirectingTargetHandler(RequestHandler):
    def initialize(self, target=None, path=None, redirect_to=None, **kwargs):
        super().initialize(**kwargs)
        self.target = target
        self.path = path
        self.redirect_to = redirect_to

    def get(self, path=None):
        self.set_header("Location", self.redirect_to)
        self.set_status(301)
        self.finish()


class ErrorTargetHandler(RequestHandler):
    def initialize(self, target=None, path=None, **kwargs):
        super().initialize(**kwargs)

    def get(self, path=None):
        self.set_header("Content-Type", "text/plain")
        self.write(self.get_query_argument("url"))
        self.finish()


class TestProxy(AsyncHTTPTestCase):
    def _add_server(self, server):
        servers = getattr(self, "_created_http_servers", [])
        servers.append(server)
        self._created_http_servers = servers

    def _add_target_route(self, path, target_path="", handler=TargetHandler, **kwargs):
        sock, port = bind_unused_port()
        target = f"http://127.0.0.1:{port}" + target_path
        app = Application(
            [
                (r"/(.*)", handler, {"target": target, "path": path, **kwargs}),
            ]
        )

        http_server = HTTPServer(app)
        http_server.add_sockets([sock])
        self._add_server(http_server)

        self.proxy.add_route(path, {"target": target})
        # routes are created with an activity timestamp artificially shifted into the past
        # so that activity can more easily be measured
        self.proxy._routes.update("/", {"last_activity": self.start_time})

        return target

    def tearDown(self):
        for server in self._created_http_servers:
            server.stop()
            self.io_loop.run_sync(server.close_all_connections, timeout=get_async_test_timeout())
        return super().tearDown()

    def get_app(self):
        self.proxy = PythonProxy()
        self.start_time = datetime.datetime.now() - datetime.timedelta(hours=1)
        self._add_target_route(path="/")

        return self.proxy.proxy_app

    def fetch(self, path, raise_error=True, **kwargs):
        return super().fetch(path, raise_error=raise_error, **kwargs)

    def test_basic_http_request(self):
        now = datetime.datetime.now()
        last_hour = now - datetime.timedelta(hours=1)

        self.proxy._routes.update("/", {"last_activity": last_hour})
        resp = self.fetch("/")
        reply = json.loads(resp.body)
        assert reply["path"] == "/"

        # check last_activity was updated
        route = self.proxy.get_route("/")
        assert route["last_activity"] > now

        # check the other HTTP methods too
        resp = self.fetch("/", method="HEAD", raise_error=False)
        assert resp.code == 405
        resp = self.fetch("/", method="OPTIONS", raise_error=False)
        assert resp.code == 405
        resp = self.fetch("/", method="POST", body="", raise_error=False)
        assert resp.code == 405
        resp = self.fetch("/", method="DELETE", raise_error=False)
        assert resp.code == 405
        resp = self.fetch("/", method="PATCH", body="", raise_error=False)
        assert resp.code == 405
        resp = self.fetch("/", method="PUT", body="", raise_error=False)
        assert resp.code == 405

    @gen_test
    def test_basic_websocket_request(self):
        now = datetime.datetime.now()
        route = self.proxy.get_route("/")
        assert route["last_activity"] <= now

        ws_client = yield websocket_connect(self.get_url("/").replace("http:", "ws:"))

        ws_client.write_message("hi")
        response = yield ws_client.read_message()
        assert response == "connected"

        response = yield ws_client.read_message()
        reply = json.loads(response)
        assert reply["path"] == "/"
        assert reply["message"] == "hi"

        # check last_activity was updated
        route = self.proxy.get_route("/")
        assert route["last_activity"] > now

    def test_sending_headers(self):
        resp = self.fetch("/", headers={"testing": "OK"})
        reply = json.loads(resp.body)
        assert reply["path"] == "/"
        assert reply["headers"].get("Testing") == "OK"

    def test_proxy_request_event_can_modify_header(self):
        pytest.skip("proxy_request event is not supported")

    #   it("proxyRequest event can modify headers", function (done) {
    #     var called = {};
    #     proxy.on("proxyRequest", function (req, res) {
    #       req.headers.testing = "Test Passed";
    #       called.proxyRequest = true;
    #     });

    #     r(proxyUrl)
    #       .then(function (body) {
    #         body = JSON.parse(body);
    #         expect(called.proxyRequest).toBe(true);
    #         expect(body).toEqual(
    #           jasmine.objectContaining({
    #             path: "/",
    #           })
    #         );
    #         expect(body.headers).toEqual(
    #           jasmine.objectContaining({
    #             testing: "Test Passed",
    #           })
    #         );
    #       })
    #       .then(done);
    #   });

    def test_target_path_is_prepended_by_default(self):
        self._add_target_route(path="/bar", target_path="/foo")
        resp = self.fetch("/bar/rest/of/it")
        reply = json.loads(resp.body)
        assert reply["path"] == "/bar"
        assert reply["url"] == "/foo/bar/rest/of/it"

    def test_handle_path_with_querystring(self):
        self._add_target_route(path="/bar", target_path="/foo")
        resp = self.fetch("/bar?query=foo")
        reply = json.loads(resp.body)
        assert reply["path"] == "/bar"
        assert reply["url"] == "/foo/bar?query=foo"
        assert reply["target"] == pytest_regex(r"http://127.0.0.1:\d+/foo")

    def test_handle_path_with_uri_encoding(self):
        self._add_target_route(path="/b@r/b r", target_path="/foo")
        resp = self.fetch("/b%40r/b%20r/rest/of/it")
        reply = json.loads(resp.body)
        assert reply["path"] == "/b@r/b r"
        assert reply["url"] == "/foo/b%40r/b%20r/rest/of/it"

    def test_handle_path_with_uri_encoding_partial(self):
        self._add_target_route(path="/b@r/b r", target_path="/foo")
        resp = self.fetch("/b@r/b%20r/rest/of/it")
        reply = json.loads(resp.body)
        assert reply["path"] == "/b@r/b r"
        assert reply["url"] == "/foo/b%40r/b%20r/rest/of/it"

    def test_target_without_prepend_path(self):
        self.proxy.prepend_path = False
        self._add_target_route(path="/bar", target_path="/foo")
        resp = self.fetch("/bar/rest/of/it")
        reply = json.loads(resp.body)
        assert reply["path"] == "/bar"
        assert reply["url"] == "/bar/rest/of/it"

    def test_target_without_include_prefix(self):
        self.proxy.include_prefix = False
        self._add_target_route(path="/bar", target_path="/foo")
        resp = self.fetch("/bar/rest/of/it")
        reply = json.loads(resp.body)
        assert reply["path"] == "/bar"
        assert reply["url"] == "/foo/rest/of/it"

    def test_default_target_config(self):
        proxy = PythonProxy({"default_target": "http://127.0.0.1:12345"})
        route = proxy.get_route("/")
        assert route["target"] == "http://127.0.0.1:12345"

    def test_storage_backend_config_invalid(self):
        with pytest.raises(AssertionError, match="Unknown backend provided 'invalid_storage'"):
            PythonProxy({"storage_backend": "invalid_storage"})

    def test_storage_backend_config(self):
        # With a importable string
        proxy = PythonProxy(
            {"storage_backend": "configurable_http_proxy_test.dummy_store.PlugableDummyStore"}
        )
        assert type(proxy._routes).__name__ == "PlugableDummyStore"

        # With a class
        from configurable_http_proxy_test.dummy_store import PlugableDummyStore

        proxy = PythonProxy({"storage_backend": PlugableDummyStore})
        assert type(proxy._routes).__name__ == "PlugableDummyStore"

    def test_without_include_prefix_and_without_prepend_path(self):
        self.proxy.include_prefix = False
        self.proxy.prepend_path = False
        self._add_target_route(path="/bar", target_path="/foo")
        resp = self.fetch("/bar/rest/of/it")
        reply = json.loads(resp.body)
        assert reply["path"] == "/bar"
        assert reply["url"] == "/rest/of/it"

    @pytest.mark.xfail(reason="host_routing doesnt work")
    def test_host_routing_config(self):
        self.proxy.host_routing = True
        host = "test.localhost.org"
        target_url = self._add_target_route(path="/" + host)
        resp = self.fetch(f"http://{host}:{self.get_http_port()}/some/path")
        reply = json.loads(resp.body)
        assert reply["target"] == target_url  # "http://127.0.0.1:" + testPort,
        assert reply["url"] == "/some/path"

    def test_last_activity_not_updated_on_errors(self):
        now = datetime.datetime.now()

        self.proxy.remove_route("/")
        self.proxy.add_route("/missing", {"target": "https://127.0.0.1:12345"})
        self.proxy._routes.update("/missing", {"last_activity": now})

        # fail a http activity
        resp = self.fetch("/missing/prefix", raise_error=False)
        assert resp.code == 503  # This should be 503 ??
        assert self.proxy.get_route("/missing")["last_activity"] == now

    @gen_test
    def test_last_activity_not_updated_on_errors_websocket(self):
        now = datetime.datetime.now()

        self.proxy.remove_route("/")
        self.proxy.add_route("/missing", {"target": "https://127.0.0.1:12345"})
        self.proxy._routes.update("/missing", {"last_activity": now})

        # fail a websocket activity
        with pytest.raises(HTTPClientError, match="HTTP 503: Service Unavailable"):
            yield websocket_connect(self.get_url("/missing/ws").replace("http:", "ws:"))

        # expect an error, since there is no websocket handler - check last_activity was not updated
        route = self.proxy.get_route("/missing")
        assert route["last_activity"] == now

    def test_custom_error_target(self):
        sock, port = bind_unused_port()
        app = Application([(r"/(.*)", ErrorTargetHandler)])
        http_server = HTTPServer(app)
        http_server.add_sockets([sock])
        self._add_server(http_server)

        self.proxy.error_target = f"http://127.0.0.1:{port}"
        self.proxy.remove_route("/")
        resp = self.fetch("/foo/bar", raise_error=False)
        assert resp.code == 404
        assert resp.headers["content-type"] == "text/plain"
        assert resp.body == b"/foo/bar"

    def test_custom_error_path(self):
        self.proxy.error_path = os.path.join(RESOURCES_PATH, "errors")
        self.proxy.remove_route("/")
        self.proxy.add_route("/missing", {"target": "http://127.0.0.1:54321"})

        resp = self.fetch("/nope", raise_error=False)
        assert resp.code == 404
        assert resp.headers["content-type"] == "text/html"
        assert b"<b>404'D!</b>" in resp.body

        resp = self.fetch("/missing/prefix", raise_error=False)
        assert resp.code == 503
        assert resp.headers["content-type"] == "text/html"
        assert b"<b>UNKNOWN ERROR</b>" in resp.body

    def test_default_error_html(self):
        self.proxy.remove_route("/")
        self.proxy.add_route("/missing", {"target": "http://127.0.0.1:54321"})

        resp = self.fetch("/nope", raise_error=False)
        assert resp.code == 404
        assert "text/html" in resp.headers["content-type"]
        assert b"<title>404: Not Found</title>" in resp.body

        resp = self.fetch("/missing/prefix", raise_error=False)
        assert resp.code == 503
        assert "text/html" in resp.headers["content-type"]
        assert b"<title>503: Service Unavailable</title>" in resp.body

    def test_redirect_location_untouched_without_rewrite_option(self):
        redirect_to = "http://foo.com:12345/whatever"
        target_url = self._add_target_route(
            "/external/urlpath",
            target_path="/internal/urlpath/",
            handler=RedirectingTargetHandler,
            redirect_to=redirect_to,
        )

        resp = self.fetch("/external/urlpath/rest/of/it", follow_redirects=False, raise_error=False)
        assert resp.code == 301
        assert resp.headers["Location"] == redirect_to

    def test_redirect_location_with_rewriting(self):
        pytest.xfail(reason="rewrite not supported")

    #   it("Redirect location with rewriting", function (done) {
    #     var proxyPort = 55556;
    #     var options = {
    #       protocolRewrite: "https",
    #       autoRewrite: true,
    #     };

    #     // where the backend server redirects us.
    #     // Note that http-proxy requires (logically) the redirection to be to the same (internal) host.
    #     var redirectTo = "https://127.0.0.1:" + testPort + "/whatever";
    #     var expectedRedirect = "https://127.0.0.1:" + proxyPort + "/whatever";

    #     util
    #       .setupProxy(proxyPort, options, [])
    #       .then((proxy) =>
    #         util.addTargetRedirecting(
    #           proxy,
    #           "/external/urlpath/",
    #           testPort,
    #           "/internal/urlpath/",
    #           redirectTo
    #         )
    #       )
    #       .then(() => r("http://127.0.0.1:" + proxyPort + "/external/urlpath/"))
    #       .then((body) => done.fail("Expected 301"))
    #       .catch((err) => {
    #         expect(err.statusCode).toEqual(301);
    #         expect(err.response.headers.location).toEqual(expectedRedirect);
    #       })
    #       .then(done);
    #   });

    def test_health_check_request(self):
        resp = self.fetch("/_chp_healthz")
        reply = json.loads(resp.body)
        assert reply == {"status": "OK"}

    def test_target_not_found(self):
        self.proxy.remove_route("/")

        resp = self.fetch("/unknown", raise_error=False)
        assert resp.code == 404
        assert "text/html" in resp.headers["content-type"]
        assert b"<title>404: Not Found</title>" in resp.body

    @gen_test
    def test_target_not_found_websocket(self):
        self.proxy.remove_route("/")

        with pytest.raises(HTTPClientError, match="HTTP 404: Not Found"):
            yield websocket_connect(self.get_url("/unknown").replace("http:", "ws:"))

    @gen_test
    def test_websocket_failure_due_to_request(self):
        # The tornado websocket internally checks for: header[ORIGIN] == header[HOST] if both the headers are present.
        # This test checks that we close the ws_client correctly in case of such errors

        with pytest.raises(HTTPClientError, match="HTTP 403: Forbidden"):
            req = HTTPRequest(
                self.get_url("/").replace("http:", "ws:"),
                headers={
                    "Origin": "http://origin.com",
                    "Host": "http://host.com",
                },
            )
            ws_client = yield websocket_connect(req)

    def test_custom_headers(self):
        self.proxy.custom_headers = {"testing_from_custom": "OK"}
        resp = self.fetch("/", headers={"testing_from_request": "OK"})
        reply = json.loads(resp.body)
        assert reply["path"] == "/"
        assert reply["headers"].get("Testing_from_request") == "OK"
        assert reply["headers"].get("Testing_from_custom") == "OK"

    def test_custom_headers_higher_priority(self):
        self.proxy.custom_headers = {"testing": "from_custom"}
        resp = self.fetch("/", headers={"testing": "from_request"})
        reply = json.loads(resp.body)
        assert reply["path"] == "/"
        assert reply["headers"].get("Testing") == "from_custom"

    def test_receiving_headers_setcookie(self):
        # When the same header has multiple values - it needs to be handled correctly.
        resp = self.fetch("/?with_set_cookie=1")
        headers = list(resp.headers.get_all())
        cookies = {}
        for header_name, header in headers:
            if header_name.lower() !='set-cookie':
                continue
            key, val = header.split("=", 1)
            cookies[key] = val
        assert "key" in cookies
        assert cookies['key'] == 'val'
        assert "combined_key" in cookies
        assert cookies['combined_key'] == 'val; Secure=; HttpOnly=; SameSite=None; Path=/; Domain=example.com; Max-Age=999999; Expires=Fri, 01 Oct 2020 06:12:16 GMT'
        for prefix in ["Secure", "HttpOnly", "SameSite", "Path", "Domain", "Max-Age", "Expires"]:
            assert prefix + "_key" in cookies
