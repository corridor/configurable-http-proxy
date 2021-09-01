# Releasing

When doing a release, ensure the following steps are followed.

## Update the Changelog

Ensure the CHANGELOG.md is up to date.

## Tag the version

To update the version, we use `setuptools_scm` and git tags. Run the following to tag the commit
to the version you are releasing:

```bash
git tag v0.2.0
git push origin main --tags
```

## Releasing on PyPI

To release the package on PyPI, run:

```bash
venv/bin/pip install wheel twine
rm -rf build dist  # Cleanup
venv/bin/python setup.py bdist_wheel sdist
venv/bin/twine upload dist/*
```
