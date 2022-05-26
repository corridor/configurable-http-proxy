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
- Configurable storage backend

The following options are additional (not available in nodejs CHP currently):
- Ready to use DBMS storage backend

The following options are not supported (yet):

- SSL for proxy, client, API is not available (`--ssl-*`, `--api-ssl-*`, `--client-ssl-*`, `--insecure`)
- Redirecting: `--redirect-port` and `--redirect-to`
- Change Origin: `--change-origin`
- Rewrites in Location header: `--protocol-rewrite` and `--auto-rewrite`
- Metrics server: `--metrics-port` and `--metrics-ip`

## Database-backed storage backend

Using a SQL DBMS instead of the default in-memory store enables chp to be replicated
in a High Availability scenario.

To use a SQL DBMS as the storage backend:

1. Install DBMS support

```bash
$ pip install configurable-http-proxy[sqla]
```

2. Set the CHP_DATABASE_URL env var to any db URL supported by SQLAlchemy. The default is `sqlite:///chp.sqlite`.

```bash
$ export CHP_DATABASE_URL="sqlite:///chp.sqlite"
$ configurable-http-proxy --storage-backend configurable_http_proxy.dbstore.DatabaseStore
```

3. Optionally you may set the table name by setting the CHP_DATABASE_TABLE. The default is 'chp_routes'

```bash
$ export CHP_DATABASE_TABLE="chp_routes"
```
