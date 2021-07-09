from configurable_http_proxy.store import MemoryStore


class TestMemoryStore:
    def setup_method(self, method):
        self.subject = MemoryStore()

    def test_get(self):
        self.subject.add("/myRoute", {"test": "value"})
        route = self.subject.get("/myRoute")
        assert route == {"test": "value"}

    def test_get_with_invalid_path(self):
        route = self.subject.get("/wut")
        assert route is None

    def test_get_target(self):
        self.subject.add("/myRoute", {"target": "http://localhost:8213"})
        target = self.subject.get_target("/myRoute")
        assert target.prefix == "/myRoute"
        assert target.data["target"] == "http://localhost:8213"

    def test_get_all(self):
        self.subject.add("/myRoute", {"test": "value1"})
        self.subject.add("/myOtherRoute", {"test": "value2"})

        routes = self.subject.get_all()
        assert len(routes) == 2
        assert routes["/myRoute"] == {"test": "value1"}
        assert routes["/myOtherRoute"] == {"test": "value2"}

    def test_get_all_with_no_routes(self):
        routes = self.subject.get_all()
        assert routes == {}

    def test_add(self):
        self.subject.add("/myRoute", {"test": "value"})

        route = self.subject.get("/myRoute")
        assert route == {"test": "value"}

    def test_add_overwrite(self):
        self.subject.add("/myRoute", {"test": "value"})
        self.subject.add("/myRoute", {"test": "updatedValue"})

        route = self.subject.get("/myRoute")
        assert route == {"test": "updatedValue"}

    def test_update(self):
        self.subject.add("/myRoute", {"version": 1, "test": "value"})
        self.subject.update("/myRoute", {"version": 2})

        route = self.subject.get("/myRoute")
        assert route["version"] == 2
        assert route["test"] == "value"

    def test_remove(self):
        self.subject.add("/myRoute", {"test": "value"})
        self.subject.remove("/myRoute")

        route = self.subject.get("/myRoute")
        assert route is None

    def test_remove_with_invalid_route(self):
        # No error should occur
        self.subject.remove("/myRoute/foo/bar")

    def test_has_route(self):
        self.subject.add("/myRoute", {"test": "value"})
        route = self.subject.get("/myRoute")
        assert route == {"test": "value"}

    def test_has_route_path_not_found(self):
        route = self.subject.get("/wut")
        assert route is None
