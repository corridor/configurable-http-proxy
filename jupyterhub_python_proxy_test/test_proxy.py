import pytest

from jupyterhub_python_proxy.configproxy import PythonProxy


class TestProxy:
    def test_storage_backend_config_invalid(self):
        with pytest.raises(AssertionError, match="Unknown backend provided 'invalid_storage'"):
            PythonProxy({"storage_backend": "invalid_storage"})

    def test_storage_backend_config(self):
        # With a importable string
        proxy = PythonProxy(
            {"storage_backend": "jupyterhub_python_proxy_test.dummy_store.PlugableDummyStore"}
        )
        assert type(proxy._routes).__name__ == "PlugableDummyStore"

        # With a class
        from jupyterhub_python_proxy_test.dummy_store import PlugableDummyStore

        proxy = PythonProxy({"storage_backend": PlugableDummyStore})
        assert type(proxy._routes).__name__ == "PlugableDummyStore"
