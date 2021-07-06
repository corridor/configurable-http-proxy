import os

from setuptools import find_packages, setup

BASE_PATH = os.path.abspath(os.path.dirname(__file__))


setup(
    name='jupyterhub-python-proxy',
    use_scm_version={
        'write_to': 'jupyterhub_python_proxy/version.txt',
    },
    setup_requires=['setuptools_scm'],
    install_requires=open(os.path.join(BASE_PATH, 'requirements.txt')).readlines(),
    include_package_data=True,
    zip_safe=False,
    packages=find_packages(include=['jupyterhub_python_proxy', 'jupyterhub_python_proxy.*']),
    entry_points={
        'console_scripts': [
            'jupyterhub-python-proxy = jupyterhub_python_proxy.cli:main',
        ],
    },
)
