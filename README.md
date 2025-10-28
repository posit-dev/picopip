# picopip

Embed-friendly Python env/package scanner with zero deps.

This is primarily designed so that you can take `src/picopip.py`
and copy it into your own project to use it without having
to install dependencies.

## Usage

### Get list of installed packages

You can use `get_packages_from_env` to list all installed packages in a Python virtual environment. Here's how to do it using Python's built-in `venv` module:

```python
>>> from picopip import get_packages_from_env
>>>
>>> pkgs = get_packages_from_env(venvdir)
>>> print(pkgs)
[('certifi', '2025.4.26'), ('charset-normalizer', '3.4.2'), ('idna', '3.10'), 
 ('pip', '21.2.4'), ('requests', '2.32.3'), ('setuptools', '58.0.4'), 
 ('urllib3', '2.4.0')]
```

- `get_packages_from_env(<venv_path>)` returns a list of `(name, version)` tuples for all installed packages in the given virtual environment.
- You can use any venv path, and the function will find all packages, including those installed via pip.

### Get version of a package

If you only need the version of a specific package, you can get it
using `get_package_version_from_env`

```python
>>> from picopip import get_package_version_from_env
>>>
>>> version = get_package_version_from_env(venvdir, "pip")
>>> print(version)
'21.2.4'
```

### Parse a version string

`parse_version` normalizes a version into a tuple that follows the same ordering
rules used by `pip`/`packaging`. The first element is the release components,
the second is an offset encoding pre/dev/post markers so you can compare the
tuples with standard operators.

```python
>>> from picopip import parse_version
>>>
>>> parse_version("1.13.5")
((1, 13, 5), 0)
>>> parse_version("1.13.5a1") < parse_version("1.13.5")
True
>>> parse_version("1.13.5.post2") > parse_version("1.13.5")
True
```
