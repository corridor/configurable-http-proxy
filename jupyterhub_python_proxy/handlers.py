import datetime
import json

import dateutil.parser
from tornado.web import RequestHandler, HTTPError


def json_converter(val):
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    raise TypeError(f"Object of type {type(val).__name__} is not JSON serializable")


class APIHandler(RequestHandler):
    def initialize(self, proxy=None, **kwargs):
        super().initialize(**kwargs)
        self.proxy = proxy

    def is_authorized(self):
        if not self.proxy.auth_token:
            return

        auth = self.request.headers.get("authorization", "")
        auth = auth.strip()
        if auth and auth.startswith("token") and self.proxy.auth_token == auth[len("token") :].strip():
            return
        self.proxy.log.debug(f"Rejecting API request from: {auth or 'no authorization'}")
        raise HTTPError(403)

    def get(self, path: str = None):
        self.is_authorized()
        # GET /api/routes/(path) gets a single route
        if path and len(path) > 0 and path != "/":
            route = self.proxy.get_route(path)
            if not route:
                raise HTTPError(404)
            else:
                self.set_status(200)
                self.set_header("Content-Type", "application/json")
                self.write(json.dumps(route, default=json_converter))
                self.finish()
                return

        # GET returns routing table as JSON dict
        inactive_since = self.get_query_argument(
            "inactive_since", self.get_query_argument("inactiveSince", None)
        )
        if inactive_since:
            try:
                inactive_since = dateutil.parser.isoparse(inactive_since)
            except ValueError:
                raise HTTPError(400, f"Invalid datestamp '{inactive_since}' must be ISO8601.")

        routes = self.proxy.get_routes(inactive_since)

        self.set_status(200)
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps(routes, default=json_converter))
        self.finish()

    def post(self, path: str = None):
        self.is_authorized()
        # POST adds a new route
        path = path or "/"
        data = json.loads(self.request.body)

        if not isinstance(data.get("target"), str):
            self.log.warn(f"Bad POST data: {json.dumps(data, default=json_converter)}")
            raise HTTPError(400, "Must specify 'target' as string")

        self.proxy.add_route(path, data)
        self.set_status(201)
        self.finish()

    def delete(self, path=None):
        self.is_authorized()

        # DELETE removes an existing route
        result = self.proxy.get_route(path)
        if result:
            self.proxy.remove_route(path)
            self.set_status(204)
        else:
            self.set_status(404)
        self.finish()
