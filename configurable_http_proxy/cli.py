import logging
import os
import sys

import click
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop


from configurable_http_proxy import __version__, log
from configurable_http_proxy.configproxy import PythonProxy


def print_version(ctx, param, value):
    click.echo(__version__)


class HeaderParamType(click.ParamType):
    # This is a paramtype similar to TupleType provided by click - but we handle `--param key:value`
    # instead of `--param key value`
    name = "header"

    def convert(self, value, param, ctx):
        out = tuple([i.strip() for i in value.split(":")])
        if len(out) != 2:
            self.fail(f"A single colon was expected in custom header: {value}", param, ctx)
        return out


@click.command()
@click.version_option(__version__)
@click.option("--ip", type=click.STRING, help="Public-facing IP of the proxy")
@click.option("--port", default=8000, type=click.INT, help="Public-facing port of the proxy")
@click.option("--ssl-key", type=click.Path(), help="SSL key to use, if any")
@click.option("--ssl-cert", type=click.Path(), help="SSL certificate to use, if any")
@click.option("--ssl-ca", type=click.Path(), help="SSL certificate authority, if any")
@click.option("--ssl-request-cert", help="Request SSL certs to authenticate clients")
@click.option(
    "--ssl-reject-unauthorized",
    help="Reject unauthorized SSL connections (only meaningful if --ssl-request-cert is given)",
)
@click.option("--ssl-protocol", type=click.STRING, help="Set specific SSL protocol, e.g. TLSv1.2, SSLv3")
@click.option("--ssl-ciphers", type=click.STRING, help="`:`-separated ssl cipher list. Default excludes RC4")
@click.option("--ssl-allow-rc4", help="Allow RC4 cipher for SSL (disabled by default)")
@click.option("--ssl-dhparam", type=click.Path(), help="SSL Diffie-Helman Parameters pem file, if any")
@click.option("--api-ip", type=click.STRING, help="Inward-facing IP for API requests (default: 'localhost')")
@click.option(
    "--api-port", type=click.INT, help="Inward-facing port for API requests (defaults to --port=value+1)"
)
@click.option("--api-ssl-key", type=click.Path(), help="SSL key to use, if any, for API requests")
@click.option("--api-ssl-cert", type=click.Path(), help="SSL certificate to use, if any, for API requests")
@click.option("--api-ssl-ca", type=click.Path(), help="SSL certificate authority, if any, for API requests")
@click.option("--api-ssl--request-cert", help="Request SSL certs to authenticate clients for API requests")
@click.option(
    "--api-ssl-reject-unauthorized",
    help="Reject unauthorized SSL connections (only meaningful if --api-ssl-request-cert is given)",
)
@click.option(
    "--client-ssl-key", type=click.Path(), help="SSL key to use, if any, for proxy to client requests"
)
@click.option(
    "--client-ssl-cert",
    type=click.Path(),
    help="SSL certificate to use, if any, for proxy to client requests",
)
@click.option(
    "--client-ssl-ca",
    type=click.Path(),
    help="SSL certificate authority, if any, for proxy to client requests",
)
@click.option("--client-ssl-request-cert", help="Request SSL certs to authenticate clients for API requests")
@click.option(
    "--client-ssl-reject-unauthorized",
    help="Reject unauthorized SSL connections (only meaningful if --client-ssl-request-cert is given)",
)
@click.option("--default-target", type=click.STRING, help="Default proxy target (proto://host[:port])")
@click.option(
    "--error-target",
    type=click.STRING,
    help="Alternate server for handling proxy errors (proto://host[:port])",
)
@click.option(
    "--error-path", type=click.Path(), help="Alternate server for handling proxy errors (proto://host[:port])"
)
@click.option(
    "--redirect-port", type=click.INT, help="Redirect HTTP requests on this port to the server on HTTPS"
)
@click.option(
    "--redirect-to", type=click.INT, help="Redirect HTTP requests from --redirect-port to this port"
)
@click.option("--pid-file", type=click.Path(), help="Write our PID to a file")
@click.option(
    "--x-forward/--no-x-forward",
    default=True,
    help="Don't add 'X-forward-' headers to proxied requests",
)
@click.option(
    "--prepend-path/--no-prepend-path",
    default=True,
    help="Avoid prepending target paths to proxied requests",
)
@click.option(
    "--include-prefix/--no-include-prefix",
    default=True,
    help="Don't include the routing prefix in proxied requests",
)
@click.option("--auto-rewrite", help="Rewrite the Location header host/port in redirect responses")
@click.option(
    "--change-origin/--no-change-origin",
    default=False,
    help="Changes the origin of the host header to the target URL",
)
@click.option(
    "--protocol-rewrite",
    type=click.STRING,
    help="Rewrite the Location header protocol in redirect responses to the specified protocol",
)
@click.option(
    "--custom-header",
    type=HeaderParamType(),
    multiple=True,
    help="Custom header to add to proxied requests. Use same option for multiple headers (--custom-header k1:v1 --custom-header k2:v2) (default: [])",
)
@click.option("--insecure", help="Disable SSL cert verification")
@click.option("--host-routing", help="Use host routing (host as first level of path)")
@click.option(
    "--log-level",
    type=click.Choice(
        [logging.getLevelName(i) for i in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR)],
        case_sensitive=False,
    ),
    help='Log level (debug, info, warning, error) (default: "info")',
)
@click.option(
    "--timeout", type=click.INT, help="Timeout (in millis) when proxy drops connection for a request."
)
@click.option(
    "--proxy-timeout", type=click.INT, help="Timeout (in millis) when proxy receives no response from target."
)
@click.option("--storage-backend", help="Define an external storage class. Defaults to in-MemoryStore.")
def main(**args):
    if args.get("log_level"):
        log.setLevel(args["log_level"])
    options = {"log": log}

    if args.get("ssl_ciphers"):
        ssl_ciphers = args["ssl_ciphers"]
    else:
        rc4 = "!RC4"  # disable RC4 by default
        if args["ssl_allow_rc4"]:
            rc4 = "RC4"
        # ref: https://iojs.org/api/tls.html#tls_modifying_the_default_tls_cipher_suite
        ssl_ciphers = ":".join(
            [
                "ECDHE-RSA-AES128-GCM-SHA256",
                "ECDHE-ECDSA-AES128-GCM-SHA256",
                "ECDHE-RSA-AES256-GCM-SHA384",
                "ECDHE-ECDSA-AES256-GCM-SHA384",
                "DHE-RSA-AES128-GCM-SHA256",
                "ECDHE-RSA-AES128-SHA256",
                "DHE-RSA-AES128-SHA256",
                "ECDHE-RSA-AES256-SHA384",
                "DHE-RSA-AES256-SHA384",
                "ECDHE-RSA-AES256-SHA256",
                "DHE-RSA-AES256-SHA256",
                "HIGH",
                rc4,
                "!aNULL",
                "!eNULL",
                "!EXPORT",
                "!DES",
                "!RC4",
                "!MD5",
                "!PSK",
                "!SRP",
                "!CAMELLIA",
            ]
        )

    # ssl options
    if args.get("ssl_key") or args.get("ssl_cert"):
        raise NotImplementedError("--ssl-* is not supported yet")
        options["ssl"] = {}
        if args.get("ssl_key"):
            options["ssl"]["key"] = open(args["ssl_key"], "r").read()
            if os.environ.get("CONFIGPROXY_SSL_KEY_PASSPHRASE"):
                options["ssl"]["passphrase"] = os.environ["CONFIGPROXY_SSL_KEY_PASSPHRASE"]
        if args.get("ssl_cert"):
            options["ssl"]["cert"] = open(args["ssl_cert"], "r").read()
        if args.get("ssl_ca"):
            options["ssl"]["ca"] = open(args["ssl_ca"], "r").read()
        if args.get("ssl_dhparam"):
            options["ssl"]["dhparam"] = open(args["ssl_dhparam"], "r").read()
        if args.get("ssl_protocol"):
            options["ssl"]["secureProtocol"] = args["ssl_protocol"] + "_method"
        options["ssl"]["ciphers"] = ssl_ciphers
        options["ssl"]["honorCipherOrder"] = True
        options["ssl"]["requestCert"] = args["ssl_request_cert"]
        options["ssl"]["rejectUnauthorized"] = args["ssl_reject_unauthorized"]

    # ssl options for the API interface
    if args.get("api_ssl_key") or args.get("api_ssl_cert"):
        raise NotImplementedError("--api-ssl-* is not supported yet")
        options["api_ssl"] = {}
        if args.get("api_ssl_key"):
            options["api_ssl"]["key"] = open(args["api_ssl_key"], "r").read()
            if os.environ.get("CONFIGPROXY_API_SSL_KEY_PASSPHRASE"):
                options["api_ssl"]["passphrase"] = os.environ["CONFIGPROXY_API_SSL_KEY_PASSPHRASE"]
        if args.get("api_ssl_cert"):
            options["api_ssl"]["cert"] = open(args["api_ssl_cert"], "r").read()
        if args.get("api_ssl_ca"):
            options["api_ssl"]["ca"] = open(args["api_ssl_ca"], "r").read()
        if args.get("ssl_dhparam"):  # api_ssl_dhparam does not exist
            options["api_ssl"]["dhparam"] = open(args["ssl_dhparam"], "r").read()
        if args.get("ssl_protocol"):  # api_ssl_protocol does not exist
            options["api_ssl"]["secureProtocol"] = args["ssl_protocol"] + "_method"
        options["api_ssl"]["ciphers"] = ssl_ciphers
        options["api_ssl"]["honorCipherOrder"] = True
        options["api_ssl"]["requestCert"] = args["api_ssl_request_cert"]
        options["api_ssl"]["rejectUnauthorized"] = args["api_ssl_reject_unauthorized"]

    if args.get("client_ssl_key") or args.get("client_ssl_cert"):
        raise NotImplementedError("--client-ssl-* is not supported yet")
        options["client_ssl"] = {}
        if args.get("client_ssl_key"):
            options["client_ssl"]["key"] = open(args["client_ssl_key"], "r").read()
        if args.get("client_ssl_cert"):
            options["client_ssl"]["cert"] = open(args["client_ssl_cert"], "r").read()
        if args.get("client_ssl_ca"):
            options["client_ssl"]["ca"] = open(args["client_ssl_ca"], "r").read()
        if args.get("ssl_dhparam"):  # api_ssl_dhparam does not exist
            options["client_ssl"]["dhparam"] = open(args["ssl_dhparam"], "r").read()
        if args.get("ssl_protocol"):  # api_ssl_protocol does not exist
            options["client_ssl"]["secureProtocol"] = args["ssl_protocol"] + "_method"
        options["client_ssl"]["ciphers"] = ssl_ciphers
        options["client_ssl"]["honorCipherOrder"] = True
        options["client_ssl"]["requestCert"] = args["client_ssl_request_cert"]
        options["client_ssl"]["rejectUnauthorized"] = args["client_ssl_reject_unauthorized"]

    options.update(
        {
            "default_target": args["default_target"],
            "error_target": args["error_target"],
            "error_path": args["error_path"],
            "host_routing": args["host_routing"],
            "auth_token": os.environ.get("CONFIGPROXY_AUTH_TOKEN"),
            # "redirect_port": args["redirect_port"],
            # "redirect_to": args["redirect_to"],
            "custom_headers": dict(args["custom_header"]),
            "timeout": args["timeout"],
            "proxy_timeout": args["proxy_timeout"],
        }
    )
    # We take timeouts from CLI in millisec and convert it to seconds
    if options["proxy_timeout"] is not None:
        options["proxy_timeout"] = options["proxy_timeout"] / 1000.0
    if options["timeout"] is not None:
        options["timeout"] = options["timeout"] / 1000.0

    for key in [
        "redirect_port",
        "redirect_to",
        "insecure",
        "auto_rewrite",
        "protocol_rewrite",
    ]:
        if args.get(key):
            raise NotImplementedError(f'--{key.replace("_", "-")} is not supported yet')

    # certs need to be provided for https redirection
    if not options.get("ssl") and options.get("redirect_port"):
        log.error("HTTPS redirection specified but certificates not provided.")
        sys.exit(1)

    if options.get("error_target") and options.get("error_path"):
        log.error("Cannot specify both error-target and error-path. Pick one.")
        sys.exit(1)

    # passthrough for http-proxy options
    if args["insecure"]:
        options["secure"] = False
    options["x_forward"] = args["x_forward"]
    options["prepend_path"] = args["prepend_path"]
    options["include_prefix"] = args["include_prefix"]
    if args.get("auto_rewrite"):
        options["auto_rewrite"] = True
        log.info("AutoRewrite of Location headers enabled.")
    if args.get("change_origin"):
        options["change_origin"] = True
        log.info("Change Origin of host headers enabled.")

    if args.get("protocol_rewrite"):
        options["protocol_rewrite"] = args["protocol_rewrite"]
        log.info(f"ProtocolRewrite enabled. Rewriting to {options['protocol_rewrite']}")

    if not options.get("auth_token"):
        log.warn("REST API is not authenticated.")

    # external backend class
    options["storage_backend"] = args["storage_backend"]

    proxy = PythonProxy(options)

    if args["ip"] == "*":
        # handle ip=* alias for all interfaces
        log.warn(
            "Interpreting ip='*' as all-interfaces. Preferred usage is 0.0.0.0 for all IPv4 or '' for all-interfaces."
        )
        args["ip"] = ""

    port = int(args.get("port") or 8000)
    ip = args.get("ip")
    proxy_server = HTTPServer(proxy.proxy_app)
    proxy_server.listen(port, ip)
    log.info(
        "Proxying {scheme}://{ip}:{port} to {target}".format(
            scheme="https" if options.get("ssl") else "http",
            ip=ip or "*",
            port=port,
            target=options.get("default_target") or "(no default)",
        ),
    )

    api_port = args.get("api_port") or port + 1
    api_ip = args.get("api_ip") or "localhost"
    api_server = HTTPServer(proxy.api_app)
    api_server.listen(api_port, api_ip)
    log.info(
        "Proxy API at {scheme}://{ip}:{port}/api/routes".format(
            scheme="https" if options.get("api_ssl") else "http",
            ip=api_ip or "*",
            port=api_port,
        )
    )

    pid_file = args.get("pid_file")
    if pid_file:
        pid = str(os.getpid())
        log.info(f"Writing pid {pid} to {pid_file}")
        with open(pid_file, "w") as fh:
            fh.write(pid)

    # // Redirect HTTP to HTTPS on the proxy's port
    # if (options.redirectPort && listen.port !== 80) {
    # var http = require("http");
    # var redirectPort = options.redirectTo ? options.redirectTo : listen.port;
    # var server = http
    #     .createServer(function (req, res) {
    #     if (typeof req.headers.host === "undefined") {
    #         res.statusCode = 400;
    #         res.write(
    #         "This server is HTTPS-only on port " +
    #             redirectPort +
    #             ", but an HTTP request was made and the host could not be determined from the request."
    #         );
    #         res.end();
    #         return;
    #     }
    #     var host = req.headers.host.split(":")[0];

    #     // Make sure that when we redirect, it's to the port the proxy is running on
    #     // or the port to which we have been instructed to forward.
    #     if (redirectPort !== 443) {
    #         host = host + ":" + redirectPort;
    #     }
    #     res.writeHead(301, { Location: "https://" + host + req.url });
    #     res.end();
    #     })
    #     .listen(options.redirectPort, () => {
    #     log.info(
    #         "Added HTTP to HTTPS redirection from " + server.address().port + " to " + redirectPort
    #     );
    #     });
    # }

    try:
        IOLoop.current().start()
    except Exception as err:
        if pid_file:  # Cleanup PID file
            log.debug(f"Removing {pid_file}")
            os.remove(pid_file)
