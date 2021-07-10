import os

from setuptools import find_packages, setup

BASE_PATH = os.path.abspath(os.path.dirname(__file__))

if __name__ == '__main__':
    setup(
        name="configurable-http-proxy",
        url="https://github.com/AbdealiJK/configurable-http-proxy",
        author="AbdealiJK",
        author_email="abdealikothari@gmail.com",
        license="MIT",
        use_scm_version={
            "write_to": "configurable_http_proxy/version.txt",
        },
        setup_requires=["setuptools_scm"],
        install_requires=open(os.path.join(BASE_PATH, "requirements.txt")).readlines(),
        include_package_data=True,
        zip_safe=False,
        packages=find_packages(include=["configurable_http_proxy", "configurable_http_proxy.*"]),
        entry_points={
            "console_scripts": [
                "configurable-http-proxy = configurable_http_proxy.cli:main",
            ],
        },
    )
