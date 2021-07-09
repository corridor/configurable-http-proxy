from configurable_http_proxy.trie import URLTrie


def setup_full_trie():
    # return a simple trie for testing
    trie = URLTrie()
    paths = ["/1", "/2", "/a/b/c/d", "/a/b/d", "/a/b/e", "/b", "/b/c", "/b/c/d"]
    for path in paths:
        trie.add(path, {"path": path})

    return trie


class TestUrlTrie:
    def test_init(self):
        trie = URLTrie()
        assert trie.prefix == "/"
        assert trie.size == 0
        assert trie.data is None
        assert trie.branches == {}

        trie = URLTrie("/foo")
        assert trie.size == 0
        assert trie.prefix == "/foo"
        assert trie.data is None
        assert trie.branches == {}

    def test_root(self):
        trie = URLTrie()
        trie.add("/", -1)
        node = trie.get("/1/etc/etc/")
        assert node.prefix == "/"
        assert node.data == -1

        node = trie.get("/")
        assert node.prefix == "/"
        assert node.data == -1

        node = trie.get("")
        assert node.prefix == "/"
        assert node.data == -1

    def test_add(self):
        trie = URLTrie()

        trie.add("foo", 1)
        assert trie.size == 1

        assert trie.data is None
        assert trie.branches["foo"].data == 1
        assert trie.branches["foo"].size == 0

        trie.add("bar/leaf", 2)
        assert trie.size == 2
        bar = trie.branches["bar"]
        assert bar.prefix == "/bar"
        assert bar.size == 1
        assert bar.branches["leaf"].data == 2

        trie.add("/a/b/c/d", 4)
        assert trie.size == 3
        a = trie.branches["a"]
        assert a.prefix == "/a"
        assert a.size == 1
        assert a.data is None

        b = a.branches["b"]
        assert b.prefix == "/a/b"
        assert b.size == 1
        assert b.data is None

        c = b.branches["c"]
        assert c.prefix == "/a/b/c"
        assert c.size == 1
        assert c.data is None
        d = c.branches["d"]
        assert d.prefix == "/a/b/c/d"
        assert d.size == 0
        assert d.data == 4

    def test_get(self):
        trie = setup_full_trie()
        assert trie.get("/not/found") is None

        node = trie.get("/1")
        assert node.prefix == "/1"
        assert node.data["path"] == "/1"

        node = trie.get("/1/etc/etc/")
        assert node.prefix == "/1"
        assert node.data["path"] == "/1"

        assert trie.get("/a") is None
        assert trie.get("/a/b/c") is None

        node = trie.get("/a/b/c/d/e/f")
        assert node.prefix == "/a/b/c/d"
        assert node.data["path"] == "/a/b/c/d"

        node = trie.get("/b/c/d/word")
        assert node.prefix == "/b/c/d"
        assert node.data["path"] == "/b/c/d"

        node = trie.get("/b/c/dword")
        assert node.prefix == "/b/c"
        assert node.data["path"] == "/b/c"

    def test_remove(self):
        trie = setup_full_trie()
        size = trie.size
        node = trie.get("/b/just-b")
        assert node.prefix == "/b"

        trie.remove("/b")
        # deleting a node doesn't change size if no children
        assert trie.size == size
        assert trie.get("/b/just-b") is None
        node = trie.get("/b/c/sub-still-here")
        assert node.prefix == "/b/c"

        node = trie.get("/a/b/c/d/word")
        assert node.prefix == "/a/b/c/d"
        b = trie.branches["a"].branches["b"]
        assert b.size == 3
        trie.remove("/a/b/c/d")
        assert b.size == 2
        assert "c" not in b.branches

        trie.remove("/")
        node = trie.get("/")
        assert node is None

    def test_sub_paths(self):
        trie = URLTrie()
        trie.add("/", {"path": "/"})

        node = trie.get("/prefix/sub")
        assert node.prefix == "/"

        # add /prefix/sub/tree
        trie.add("/prefix/sub/tree", {})

        # which shouldn't change the results for /prefix and /prefix/sub
        node = trie.get("/prefix")
        assert node.prefix == "/"

        node = trie.get("/prefix/sub")
        assert node.prefix == "/"

        node = trie.get("/prefix/sub/tree")
        assert node.prefix == "/prefix/sub/tree"

        # add /prefix, and run one more time
        trie.add("/prefix", {})

        node = trie.get("/prefix")
        assert node.prefix == "/prefix"

        node = trie.get("/prefix/sub")
        assert node.prefix == "/prefix"

        node = trie.get("/prefix/sub/tree")
        assert node.prefix == "/prefix/sub/tree"

    def test_remove_first_leaf_doesnt_remove_root(self):
        trie = URLTrie()
        trie.add("/", {"path": "/"})

        node = trie.get("/prefix/sub")
        assert node.prefix == "/"

        trie.add("/prefix", {"path": "/prefix"})

        node = trie.get("/prefix/sub")
        assert node.prefix == "/prefix"

        trie.remove("/prefix/")

        node = trie.get("/prefix/sub")
        assert node.prefix == "/"
