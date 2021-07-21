# configurable-http-proxy

This is a pure python implementation of the
[configurable-http-proxy](https://github.com/jupyterhub/configurable-http-proxy)
written in nodejs. It is meant to be a drop in replacement.

## Install

Prerequisite: Python 3.6+

```bash
pip install configurable-http-proxy
```

## Feature support

The following items are supported:

- Proxying for Websocket and HTTP requests
- Configuring the proxy using API requests
- Auth token for API requests
- Error management using error_path and error_target
- Prepend path or include prefix
- Timeouts
- X-Forward related headers
- Custom Headers
- Customizable storage backends
- PID file writing
- Logging

The following options are not supported (yet):

- SSL for proxy, client, API is not available (`--ssl-*`, `--api-ssl-*`, `--client-ssl-*`, `--insecure`)
- Redirecting: `--redirect-port` and `--redirect-to`
- Change Origin: `--change-origin`
- Rewrites in Location header: `--protocol-rewrite` and `--auto-rewrite`
- Metrics server: `--metrics-port` and `--metrics-ip`
