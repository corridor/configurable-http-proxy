import datetime
import importlib
import json
import os
import typing
import urllib.parse

from tornado.web import Application

from configurable_http_proxy import log
from configurable_http_proxy.store import MemoryStore
from configurable_http_proxy.trie import URLTrie
from configurable_http_proxy.handlers import APIHandler, ProxyHandler

BASE_PATH = os.path.abspath(os.path.dirname(__file__))


def load_storage(options):
    backend = options.get("storage_backend")
    if isinstance(backend, str):
        backend_import = backend.split(".")
        backend_module = ".".join(backend_import[:-1])
        backend_clsname = backend_import[-1]
        if backend_module == "":
            raise AssertionError(f"Unknown backend provided '{backend}'")
        backend = getattr(importlib.import_module(backend_module), backend_clsname)
    elif backend is None:
        backend = MemoryStore

    # loads default storage strategy
    return backend()


class PythonProxy:
    def __init__(self, options=()):
        super().__init__()
        self.options = options = dict(options)

        self.log = self.options.get("log")
        if not self.log:
            self.log = log

        self._routes = load_storage(self.options)
        self.include_prefix = self.options.get("include_prefix", True)
        self.prepend_path = self.options.get("prepend_path", True)
        self.headers = self.options.get("headers")
        self.host_routing = self.options.get("host_routing", False)
        self.timeout = self.options.get("timeout")
        self.proxy_timeout = self.options.get("proxy_timeout")
        self.custom_headers = dict(self.options.get("custom_headers") or {})
        self.x_forward = self.options.get("x_forward", True)
        self.error_target = self.options.get("error_target")
        if self.error_target and not self.error_target.endswith("/"):
            self.error_target = self.error_target + "/"  # ensure trailing slash
        self.error_path = self.options.get("error_path", os.path.join(BASE_PATH, "templates"))

        self.default_target = self.options.get("default_target")
        if self.default_target:
            self.add_route("/", {"target": self.default_target})

        # handle API requests
        self.auth_token = self.options.get("auth_token")
        self.api_app = Application(
            [
                (r"^\/api\/routes(\/.*)?$", APIHandler, {"proxy": self}),
            ]
        )
        self.proxy_app = Application(
            [
                (r"/(.*)", ProxyHandler, {"proxy": self}),
            ]
        )

    def add_route(self, path, data):
        # add a route to the routing table
        path = self._routes.clean_path(path)
        if self.host_routing and path != "/":
            data["host"] = path.split("/")[1]
        self.log.info(f"Adding route {path} -> {data.get('target')}")

        self._routes.add(path, data)
        self.update_last_activity(path)
        self.log.info(f"Route added {path} -> {data.get('target')}")

    def remove_route(self, path) -> typing.Union[URLTrie, None]:
        # remove a route from the routing table
        result = self._routes.get(path)
        if result:
            self.log.info(f"Removing route {path}")
            return self._routes.remove(path)

    def get_route(self, path: str):
        # GET a single route
        path = self._routes.clean_path(path)
        return self._routes.get(path)

    def get_routes(self, inactive_since=None):
        # GET all of routes
        routes = self._routes.get_all()
        if inactive_since:
            return {path: val for path, val in routes.items() if val["last_activity"] < inactive_since}
        else:
            return routes

    def target_for_req(self, host, path):
        # return proxy target for a given url path
        base_path = "/" + host if host else ""
        path = base_path + urllib.parse.unquote(path)

        route = self._routes.get_target(path)
        if route:
            return {
                "prefix": route.prefix,
                "target": route.data["target"],
            }

    def update_last_activity(self, prefix):
        result = self._routes.get(prefix)
        if result:
            return self._routes.update(prefix, {"last_activity": datetime.datetime.now()})

    def handle_health_check(self, req, res):
        if req.url == "/_chp_healthz":
            res.writeHead(200, {"Content-Type": "application/json"})
            res.write(json.dumps({"status": "OK"}))
            res.end()
