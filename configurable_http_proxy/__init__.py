import logging

log = logging.getLogger("configurable_http_proxy")
log.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(levelname)-.1s %(asctime)s %(name)s] %(message)s"))
logging.root.addHandler(handler)
