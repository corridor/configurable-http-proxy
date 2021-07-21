import datetime
import json
import os
import re
import typing
import urllib.parse

import dateutil.parser
from tornado.gen import with_timeout
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPClientError
from tornado.web import RequestHandler, HTTPError
from tornado.websocket import WebSocketHandler, websocket_connect

if typing.TYPE_CHECKING:
    from configurable_http_proxy.configproxy import PythonProxy


def json_converter(val):
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    raise TypeError(f"Object of type {type(val).__name__} is not JSON serializable")


async def apply_timeout(timeout, future):
    if timeout is None:
        return await future
    else:
        return await with_timeout(datetime.timedelta(seconds=timeout), future)


class APIHandler(RequestHandler):
    def initialize(self, proxy: "PythonProxy" = None, **kwargs):
        super().initialize(**kwargs)
        self.proxy = proxy

    def write_error(self, status_code, **kwargs):
        err_type, err, err_tb = (None, None, None)
        if "exc_info" in kwargs:
            err_type, err, err_tb = kwargs["exc_info"]
        if not isinstance(err, HTTPError):  # Only log exceptions
            self.proxy.log.error(f"Error in handler for {self.request.method} {self.request.path}: {err}")
        return super().write_error(status_code, **kwargs)

    def on_finish(self):
        # log function called when any response is finished
        code = self.get_status()
        if code < 400:
            log_func = self.proxy.log.info
        elif code < 500:
            log_func = self.proxy.log.warning
        else:
            log_func = self.proxy.log.error
        msg = ""  # Get _logMsg ?
        log_func(f"{code} {self.request.method.upper()} {self.request.path} {msg}")

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
            self.proxy.log.warn(f"Bad POST data: {json.dumps(data, default=json_converter)}")
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


class ProxyHandler(WebSocketHandler):
    def initialize(self, proxy: "PythonProxy" = None, **kwargs):
        super().initialize(**kwargs)
        self.proxy = proxy
        self.target = None
        self.ws_client = None
        self.closed = True

    def write_error(self, status_code, **kwargs):
        err_type, err, err_tb = (None, None, None)
        if "exc_info" in kwargs:
            err_type, err, err_tb = kwargs["exc_info"]

        if not isinstance(err, HTTPError):  # Only log exceptions
            self.proxy.log.error(f"Error in handler for {self.request.method} {self.request.path}: {err}")

        return super().write_error(status_code, **kwargs)

    def handle_proxy_error_default(self, code, err):
        # called when no custom error handler is registered, or is registered and doesn't work
        raise HTTPError(code)

    async def handle_proxy_error(self, code, err):
        # Called when proxy itself has an error so far, just 404 for no target and 503 for target not responding.
        # Custom error server gets `/CODE?url=/escapedUrl/`, e.g. /404?url=%2Fuser%2Ffoo
        self.proxy.log.error(f"{code} {self.request.method} {self.request.path} {str(err or '')}")

        if self.ws_connection:
            self.proxy.log.debug("Socket error, no response to send")
            return

        if self.proxy.error_target:
            error_target = urllib.parse.urlparse(self.proxy.error_target)
            # error request is $errorTarget/$code?url=$requestUrl
            error_target = error_target._replace(
                query=f"url={urllib.parse.quote(self.request.path)}",
                path=error_target.path.rstrip("/") + f"/{code}",
            )
            self.proxy.log.debug(f"Requesting custom error page: {error_target.geturl()}")

            #  add client SSL config if error target is using https
            # if (secure && this.options.clientSsl) {
            #     target.key = this.options.clientSsl.key;
            #     target.cert = this.options.clientSsl.cert;
            #     target.ca = this.options.clientSsl.ca;
            # }

            http_client = AsyncHTTPClient()
            try:
                response = await http_client.fetch(error_target.geturl(), raise_error=True, method="GET")
            except Exception as err2:
                self.proxy.log.error(f"Failed to get custom error page: {err2}")
                self.handle_proxy_error_default(code, err)
                return

            # Return the error we got from the target
            for key, val in response.headers.get_all():
                self.set_header(key, val)
            self.set_status(code)
            self.write(response.body)
            self.finish()

        elif self.proxy.error_path:
            filename = os.path.join(self.proxy.error_path, f"{code}.html")
            if not os.path.exists(filename):
                self.proxy.log.debug(f"No error file {filename}")
                filename = os.path.join(self.proxy.error_path, "error.html")
                if not os.path.exists(filename):
                    self.proxy.log.debug(f"No error file {filename}")
                    self.handle_proxy_error_default(code, err)
                    return
            try:
                with open(filename, "r") as fh:
                    self.write(fh.read())
            except OSError as err2:
                self.proxy.log.error(f"Error reading {filename} {err2}")
                self.handle_proxy_error_default(code, err)
                return
            self.set_status(code)
            self.set_header("Content-Type", "text/html")
            self.finish()

        else:
            self.handle_proxy_error_default(code, err)

    async def get_target_url(self, path):
        self.target = self.proxy.target_for_req(None, path)
        if self.target is None:
            await self.handle_proxy_error(404, err=None)
            return

        prefix, target = self.target["prefix"], self.target["target"]
        self.proxy.log.debug(f"PROXY WEB {self.request.path} to {target}")

        proxy_path = urllib.parse.quote(path)
        if not self.proxy.include_prefix:
            proxy_path = proxy_path[len(urllib.parse.quote(prefix)) :]

        target = urllib.parse.urlparse(target)
        if self.proxy.prepend_path:
            query_strings = [target.query, self.request.query]
            query_strings = [i for i in query_strings if i not in (None, "")]
            target = target._replace(query="&".join(query_strings))
            target = target._replace(path=target.path.rstrip("/") + "/" + proxy_path.lstrip("/"))
        else:
            target = target._replace(query=self.request.query)
            target = target._replace(path=proxy_path)

        return target.geturl()

    def on_finish(self):
        # update last activity on completion of the request only consider 'successful' requests activity
        # A flood of invalid requests such as 404s or 403s or 503s because the endpoint is down
        # shouldn't make it look like the endpoint is 'active'

        code = self.get_status()
        prefix = self.target["prefix"] if self.target else ""
        # (don't count redirects...but should we?)
        if code < 300:
            if prefix:
                self.proxy.update_last_activity(prefix)
        else:
            self.proxy.log.debug(f"Not recording activity for status {code} on {prefix}")

    def health_check(self):
        if self.request.path == "/_chp_healthz":
            self.set_status(200)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({"status": "OK"}))
            self.finish()
            return True
        return False

    def _get_proxy_request(self, url):
        # Add custom-headers if required
        headers = dict(self.request.headers.get_all())
        headers.update(self.proxy.custom_headers)

        # Add x-forward headers if required
        if self.proxy.x_forward:
            encrypted = self.request.uri.partition(":")[0] in {"https", "wss"}
            host = headers.get("host")
            port = None
            if host:
                port = re.match(".*?:([0-9]+)$", host)
                if port:
                    port = int(port.group(1))
            if port is None:  # Detect the port based on default ports fo scheme
                port = 433 if encrypted else 80

            fwd_values = {
                "for": self.request.remote_ip,
                "port": str(port),
                "proto": 'https' if encrypted else 'http',
            }

            for key in ["for", "port", "proto"]:
                key_header = f"x-forwarded-{key}"
                headers[key_header] = ",".join([headers.get(key_header, ""), fwd_values[key]])

            headers["x-forwarded-host"] = headers.get("x-forwarded-host") or headers.get("host") or ""

        return HTTPRequest(
            url,
            method=self.request.method,
            headers=headers,
            body=self.request.body,
            follow_redirects=False,
            allow_nonstandard_methods=True,  # Needed to allow body for GET, OPTIONS, DELETE
            request_timeout=self.proxy.proxy_timeout,
        )

    async def call_proxy(self, path=None):
        url = await self.get_target_url(path)
        if url is None:
            return

        req = self._get_proxy_request(url)
        http_client = AsyncHTTPClient()
        try:
            response = await http_client.fetch(req, raise_error=False)
        except Exception as err:
            await self.handle_proxy_error(503, err)
            return

        self.set_status(response.code)
        for key, val in response.headers.get_all():
            if key.lower() not in ("content-length", "transfer-encoding", "content-encoding", "connection"):
                self.set_header(key, val)
        if response.body:
            self.write(response.body)
            self.set_header("Content-Length", len(response.body))
        self.finish()

    async def get(self, path=None):
        if self.request.headers.get("Upgrade", "").lower() == "websocket":
            url = await self.get_target_url(path)
            if url is None:
                return
            # NOTE: We need to start the ws-client before we run WebSocketHandler
            #       cause if the websocket cannot connect - we want to throw an error
            #       Maybe we should do this in get_websocket_protocol() instead as that runs after
            #       the header level checks
            await self.start_ws_client(path)
            if not self.ws_client:
                # Creating the websocket client to our target failed - so, don't establish a websocket connection
                return

            try:
                await WebSocketHandler.get(self, path)
            except Exception:
                # Cleanup dangling ws-client connection if we are not upgrading to a websocket
                self.ws_client.close()
                self.ws_client = None
                raise

            if self.get_status() != 101:
                # Cleanup dangling ws-client connection if we are not upgrading to a websocket
                self.ws_client.close()
                self.ws_client = None

        elif self.health_check():
            pass

        else:
            await self.call_proxy(path=path)

    async def _proxy_method(self, *args, **kwargs) -> None:
        return await apply_timeout(self.proxy.timeout, self.call_proxy(*args, **kwargs))

    head = _proxy_method
    post = _proxy_method
    delete = _proxy_method
    patch = _proxy_method
    put = _proxy_method
    options = _proxy_method

    async def start_ws_client(self, path=None):
        self.closed = False

        url = await self.get_target_url(path)
        if url is None:
            return
        url = urllib.parse.urlparse(url)
        url = url._replace(scheme=url.scheme.replace("http", "ws"))
        url = url.geturl()

        def write(msg):
            if self.closed:
                if self.ws_client:
                    self.ws_client.close()
                    self.ws_client = None
            else:
                # update timestamp on any reply data
                prefix = self.target["prefix"] if self.target else ""
                if prefix:
                    self.proxy.update_last_activity(prefix)

                if self.ws_client and msg is not None:
                    self.write_message(msg, binary=isinstance(msg, bytes))

        req = self._get_proxy_request(url)
        try:
            self.ws_client = await apply_timeout(
                self.proxy.timeout, websocket_connect(req, on_message_callback=write)
            )
        except HTTPClientError as err:
            self.set_status(err.code)
            self.write(err.message)
            self.finish()
        except Exception as err:
            await self.handle_proxy_error(503, err)
            raise

    def on_message(self, message):
        if self.ws_client:
            # update timestamp on any request data
            prefix = self.target["prefix"] if self.target else ""
            if prefix:
                self.proxy.update_last_activity(prefix)

            self.ws_client.write_message(message)

    def on_close(self):
        if self.ws_client:
            self.ws_client.close()
            self.ws_client = None
            self.closed = True
