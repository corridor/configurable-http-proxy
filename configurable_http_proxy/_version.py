import os

version = None

if version is None:
    # When installed with pip - Fetch version from pip
    try:
        from pkg_resources import get_distribution

        module_name = __name__.split('.', 1)[0]
        version = get_distribution(module_name).version
    except Exception:  # noqa: S110
        pass

if version is None:
    # When running directly from the SCM repo - Fetch version with setuptools_scm
    try:
        from setuptools_scm import get_version

        version = get_version()
    except Exception:  # noqa: S110
        pass

if version is None:
    # When version.txt file is available - use that
    try:
        version = open(os.path.join(os.path.dirname(__file__), 'version.txt')).read()
    except Exception:  # noqa: S110
        pass
