# CHANGELOG

## v0.2.3

- Fix support for `c.ConfigurableHTTPProxy.debug=True` by allowing lowercase --log-level
  arguments.

## v0.2.2

- Bugfix to handle headers with multiple values (For example: Set-Cookie)

## v0.2.1

- Bugfix for issues in adding `x-forward` headers

## v0.2.0

This releases increases our compatiblity with jupyterhub/configurable-http-proxy.

- Support the `--timeout` and `--proxy-timeout` arguments
- Add the `x-forward` headers by default, and allow users to disable this with `--no-x-forward`
- Add support for `--custom-headers` to pass to the proxy targets
- Improve metadata that we send to pypi like classifiers, description, python-requires

## v0.1.0

- Support the basic CLI and proxy mechanism provided by jupyterhub/configurable-http-proxy
