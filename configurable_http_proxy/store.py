import typing

from configurable_http_proxy.trie import URLTrie, trim_prefix


class BaseStore:
    def get_target(self, path):
        raise NotImplementedError(f"{self}: get_target() not implemented")

    def get_all(self):
        raise NotImplementedError(f"{self}: get_all() not implemented")

    def add(self, path, data):
        raise NotImplementedError(f"{self}: add() not implemented")

    def update(self, path, data):
        raise NotImplementedError(f"{self}: update() not implemented")

    def remove(self, path):
        raise NotImplementedError(f"{self}: remove() not implemented")

    def get(self, path):
        path = self.clean_path(path)
        return self.get_all()[path]

    def clean_path(self, path: str):
        return trim_prefix(path)


class MemoryStore(BaseStore):
    def __init__(self):
        super().__init__()
        self.routes: typing.Dict[str, URLTrie] = {}
        self.urls = URLTrie()

    def get(self, path: str):
        return self.routes.get(self.clean_path(path))

    def get_target(self, path: str):
        return self.urls.get(path)

    def get_all(self):
        return self.routes

    def add(self, path: str, data):
        path = self.clean_path(path)
        self.routes[path] = data
        self.urls.add(path, data)

    def update(self, path: str, data):
        self.routes[self.clean_path(path)].update(data)

    def remove(self, path: str):
        path = self.clean_path(path)
        if path in self.routes:
            route = self.routes.get(path)
            del self.routes[path]
        else:
            route = None
        self.urls.remove(path)
        return route
