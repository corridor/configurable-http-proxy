import typing
import re


def trim_prefix(prefix):
    if len(prefix) == 0 or prefix[0] != "/":
        prefix = "/" + prefix

    # ensure path *doesn't* end with / (unless it's exactly /)
    if len(prefix) > 1 and prefix[-1] == "/":
        prefix = prefix[:-1]

    return prefix


def string_to_path(val):
    # turn a /prefix/string/ into ['prefix', 'string']
    val = val.strip("/")
    if val == "":
        # special case because ''.split() gives [''], which is wrong.
        return []
    else:
        return val.split("/")


class URLTrie:
    def __init__(self, prefix=None):
        self.prefix: str = trim_prefix(prefix or "/")
        self.branches: typing.Dict[str, URLTrie] = {}
        self.size = 0
        self.data = None

    def add(self, path, data):
        # add data to a node in the trie at path
        if isinstance(path, str):
            path = string_to_path(path)
        if len(path) == 0:
            self.data = data
            return

        part, *path = path
        if part not in self.branches:
            # join with /, and handle the fact that only root ends with '/'
            prefix = self.prefix if len(self.prefix) == 1 else self.prefix + "/"
            self.branches[part] = URLTrie(prefix + part)
            self.size += 1
        self.branches[part].add(path, data)

    def remove(self, path):
        # remove `path` from the trie
        if isinstance(path, str):
            path = string_to_path(path)
        if len(path) == 0:
            # allow deleting root
            self.data = None
            return
        part, *path = path
        if part not in self.branches:
            # Requested node doesn't exist, consider it already removed.
            return
        child = self.branches[part]
        child.remove(path)
        if child.size == 0 and child.data is None:
            # child has no branches and is not a leaf
            del self.branches[part]
            self.size -= 1

    def get(self, path) -> typing.Union[None, "URLTrie"]:
        # if I have data, return me, otherwise return None
        me = None if self.data is None else self

        if isinstance(path, str):
            path = string_to_path(path)

        if len(path) == 0:
            # exact match, it's definitely me!
            return me
        part, *path = path
        if part not in self.branches:
            # prefix matches, and I don't have any more specific children
            return me
        child = self.branches.get(part)
        # I match and I have a more specific child that matches.
        # That *does not* mean that I have a more specific *leaf* that matches.
        node = child.get(path)
        if node:
            # found a more specific leaf
            return node
        else:
            # I'm still the most specific match
            return me
