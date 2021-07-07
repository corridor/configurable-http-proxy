import datetime
import json
import os

import pytest
import tornado.gen
from tornado.httpserver import HTTPServer
from tornado.testing import AsyncHTTPTestCase, bind_unused_port, get_async_test_timeout
from tornado.web import Application, RequestHandler

from jupyterhub_python_proxy.configproxy import PythonProxy
from jupyterhub_python_proxy_test.testutil import RESOURCES_PATH, pytest_regex


class TargetHandler(RequestHandler):
    def initialize(self, target=None, path=None, **kwargs):
        super().initialize(**kwargs)
        self.target = target
        self.path = path

    @tornado.gen.coroutine
    def get(self, path=None):
        reply = {
            "target": self.target,
            "path": self.path,
            "url": self.request.uri,
            "headers": dict(self.request.headers.get_all()),
        }
        self.set_status(200)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(reply))
        self.finish()


class RedirectingTargetHandler(RequestHandler):
    def initialize(self, target=None, path=None, redirect_to=None, **kwargs):
        super().initialize(**kwargs)
        self.target = target
        self.path = path
        self.redirect_to = redirect_to

    @tornado.gen.coroutine
    def get(self, path=None):
        print("RedirectingTargetHandler - get -- starting")
        self.set_header("Location", self.redirect_to)
        self.set_status(301)
        self.finish()
        print("RedirectingTargetHandler - get -- ending")


class ErrorTargetHandler(RequestHandler):
    def initialize(self, target=None, path=None, **kwargs):
        super().initialize(**kwargs)

    @tornado.gen.coroutine
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

    def test_basic_websocket_request(self):
        pytest.skip("websocket is not supported")

    #   it("basic WebSocket request", function (done) {
    #     var ws = new WebSocket("ws://127.0.0.1:" + port);
    #     ws.on("error", function () {
    #       // jasmine fail is only in master
    #       expect("error").toEqual("ok");
    #       done();
    #     });
    #     var nmsgs = 0;
    #     ws.on("message", function (msg) {
    #       if (nmsgs === 0) {
    #         expect(msg).toEqual("connected");
    #       } else {
    #         msg = JSON.parse(msg);
    #         expect(msg).toEqual(
    #           jasmine.objectContaining({
    #             path: "/",
    #             message: "hi",
    #           })
    #         );
    #         // check last_activity was updated
    #         return proxy._routes.get("/").then((route) => {
    #           expect(route.last_activity).toBeGreaterThan(proxy._setup_timestamp);
    #           ws.close();
    #           done();
    #         });
    #       }
    #       nmsgs++;
    #     });
    #     ws.on("open", function () {
    #       ws.send("hi");
    #     });
    #   });

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
            {"storage_backend": "jupyterhub_python_proxy_test.dummy_store.PlugableDummyStore"}
        )
        assert type(proxy._routes).__name__ == "PlugableDummyStore"

        # With a class
        from jupyterhub_python_proxy_test.dummy_store import PlugableDummyStore

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
        # mock timestamp in the past
        first_activity = now - datetime.timedelta(hours=1)

        self.proxy.remove_route("/")
        self.proxy.add_route("/missing", {"target": "https://127.0.0.1:12345"})
        self.proxy._routes.update("/missing", {"last_activity": first_activity})

        # fail a http activity
        resp = self.fetch("/missing/prefix", raise_error=False)
        assert resp.code == 503  # This should be 503 ??
        assert self.proxy.get_route("/missing")["last_activity"] == first_activity

        # fail a websocket activity
        pytest.xfail(reason="websocket not supported")
        # var ws = new WebSocket("ws://127.0.0.1:" + port + "/missing/ws");
        # ws.on("error", () => {
        #   // expect this, since there is no websocket handler
        #   // check last_activity was not updated
        #   // assert self.proxy.get_route('/missing')['last_activity'] == first_activity
        #   expectNoActivity().then((route) => {
        #       ws.close();
        #       done();
        #   });
        # });
        # ws.on("open", () => {
        #   done.fail("Expected websocket error");
        # });

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
