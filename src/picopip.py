# Copyright (C) 2025 by Posit Software, PBC.

"""picopip replicates features of pip within a compact single-file codebase.

Its primary purpose is to provide essential pip-like functionality for
inspecting and interacting with Python virtual environments,
without requiring the installation of pip itself.

This makes picopip ideal for vendoring alongside software that needs
 to query or manage virtual environments in a self-contained manner.

Version: 0.2.1
Author: Alessandro Molina <alessandro.molina@posit.co>
URL: https://github.com/posit-dev/picopip
License: MIT
"""

import itertools
import logging
import re
import site
from importlib.metadata import PathDistribution
from pathlib import Path
from typing import List, Optional, Tuple


# This comes from https://packaging.python.org/en/latest/specifications/version-specifiers/#appendix-parsing-version-strings-with-regular-expressions
_VERSION_PATTERN = r"""
    v?
    (?:
        (?:(?P<epoch>[0-9]+)!)?                           # epoch
        (?P<release>[0-9]+(?:\.[0-9]+)*)                  # release segment
        (?P<pre>                                          # pre-release
            [-_\.]?
            (?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)
            [-_\.]?
            (?P<pre_n>[0-9]+)?
        )?
        (?P<post>                                         # post release
            (?:-(?P<post_n1>[0-9]+))
            |
            (?:
                [-_\.]?
                (?P<post_l>post|rev|r)
                [-_\.]?
                (?P<post_n2>[0-9]+)?
            )
        )?
        (?P<dev>                                          # dev release
            [-_\.]?
            (?P<dev_l>dev)
            [-_\.]?
            (?P<dev_n>[0-9]+)?
        )?
    )
    (?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?       # local version
"""

_VERSION_REGEX = re.compile(
    r"^\s*" + _VERSION_PATTERN + r"\s*$", re.VERBOSE | re.IGNORECASE
)

_VERSION_TAG_NORMALIZE = {
    "a": "a",
    "alpha": "a",
    "b": "b",
    "beta": "b",
    "c": "rc",
    "pre": "rc",
    "preview": "rc",
    "rc": "rc",
    "post": "post",
    "rev": "post",
    "r": "post",
    "dev": "dev",
}

_VERSION_OFFSET_SPAN = 10_000
_VERSION_OFFSET = {
    "dev": -4 * _VERSION_OFFSET_SPAN,
    "a": -3 * _VERSION_OFFSET_SPAN,
    "b": -2 * _VERSION_OFFSET_SPAN,
    "rc": -1 * _VERSION_OFFSET_SPAN,
    "release": 0,
    "post": _VERSION_OFFSET_SPAN,
}

log = logging.getLogger(__name__)



def get_site_package_paths(venv_path: str) -> List[Path]:
    """Return all directories where packages might be installed for the given venv."""
    for version_dir in (Path(venv_path) / "lib").iterdir():
        if version_dir.name.startswith("python"):
            site_packages = version_dir / "site-packages"
            break
    else:
        msg = "Cannot locate site-packages in lib/pythonX.Y"
        raise RuntimeError(msg)

    seen = {site_packages}
    scan_paths = [site_packages]

    for pth_file in site_packages.glob("*.pth"):
        try:
            with pth_file.open() as f:
                for pth_line in f:
                    line = pth_line.strip()
                    if not line or line.startswith("#") or "import" in line:
                        continue
                    pth_path = (site_packages / line).absolute()
                    if pth_path.exists() and pth_path.is_dir() and pth_path not in seen:
                        scan_paths.append(pth_path)
                        seen.add(pth_path)
        except Exception as exc:
            # Ignore unreadable or malformed .pth
            log.warning(
                "Invalid .pth files %s: %s",
                pth_file,
                exc,
            )
            continue

    # Append system packages at the end, so that venv site-packages take precedence
    for system_path in _find_system_packages(venv_path):
        if system_path not in seen:
            scan_paths.append(system_path)
            seen.add(system_path)

    return scan_paths


def get_packages_from_env(venv_path: str) -> List[Tuple[str, str]]:
    """Return a list of (name, version) for all installed packages in the given venv."""
    seen = set()
    packages = []
    for path in get_site_package_paths(venv_path):
        log.debug(f"Scanning {path} for installed packages...")
        for dist_info in itertools.chain(
            path.glob("*.dist-info"), path.glob("*.egg-info")
        ):
            log.debug(f"Found distribution info: {dist_info}")
            try:
                dist = PathDistribution(dist_info)
                raw_name = dist.metadata["Name"]
                version = dist.version
                if not raw_name:
                    log.error(
                        "Missing package name in metadata for %s (skipping entry)",
                        dist_info,
                    )
                    continue
                name = raw_name.lower()
                if name not in seen:
                    seen.add(name)
                    packages.append((raw_name, version))
            except Exception as exc:
                log.warning(
                    "Failed to read package metadata for %s: %s",
                    dist_info,
                    exc,
                )
                continue
    return sorted(packages, key=lambda x: x[0].lower())


def get_package_version_from_env(venv_path: str, package_name: str) -> Optional[str]:
    """Return the version of a package installed in the given venv.

    Returns None if not found or not installed.
    """
    for name, version in get_packages_from_env(venv_path):
        if name.lower() == package_name.lower():
            return version
    return None


def _find_system_packages(venv_path: str) -> List[Path]:
    """Return scan paths for system packages if enabled in the venv."""
    scan_paths = []

    # See https://github.com/python/cpython/blob/a10b321a5807ba924c7a7833692fe5d0dc40e875/Lib/site.py#L618-L632
    cfg_path = Path(venv_path) / "pyvenv.cfg"
    if cfg_path.exists():
        content = cfg_path.read_text().splitlines()
        for raw_line in content:
            line = raw_line.strip().lower()
            if line.startswith("include-system-site-packages"):
                include_system_site = line.split("=", 1)[1].strip()
                if include_system_site == "true":
                    for sys_path in site.getsitepackages():
                        scan_paths.append(Path(sys_path))
                break

    return scan_paths


def parse_version(
    version: str,
) -> Tuple[int, ...]:
    """Return a tuple implementing practical PEP 440 ordering for *version*.

    The tuple contains the integer components of the release followed by a
    single *offset* element that encodes pre-release, post-release, and dev
    markers. Epochs, local versions, pre-release dev markers (e.g. ``a1.dev1``),
    and post-release dev variants are not supported. Pre-release numbers up to
    9999 and standalone ``.dev`` numbers up to 9999 are accepted. Post releases
    accept numbers up to 9999.
    """

    match = _VERSION_REGEX.search(version)
    if not match:
        raise ValueError(f"Invalid version: {version!r}")

    if match.group("epoch"):
        raise ValueError(f"Epochs are not supported: {version!r}")
    if match.group("local"):
        raise ValueError(f"Local versions are not supported: {version!r}")

    release_numbers = _normalize_release(match.group("release"))
    pre = None
    pre_letter = match.group("pre_l")
    pre_number = match.group("pre_n")
    if pre_letter or pre_number:
        pre = _parse_tagged_number(pre_letter, pre_number)

    post = None
    post_number = match.group("post_n1") or match.group("post_n2")
    post_letter = match.group("post_l") or ("post" if post_number else None)
    if post_letter and post_number is not None:
        post = _parse_tagged_number(post_letter, post_number)

    dev = None
    dev_letter = match.group("dev_l")
    dev_number = match.group("dev_n")
    if dev_number and not dev_letter:
        raise ValueError("Label required when number is provided")
    if dev_letter:
        dev = _parse_tagged_number(dev_letter, dev_number)

    if post and dev:
        raise ValueError(f"Post releases with dev segments are not supported: {version!r}")
    if pre and dev:
        raise ValueError(
            f"Pre-release dev segments are not supported: {version!r}"
        )

    component = pre or dev or post or ("release", 0)
    offset = _VERSION_OFFSET[component[0]] + component[1]
    return (tuple(release_numbers), offset)


def _normalize_release(release: str) -> List[int]:
    numbers = [int(part) for part in release.split(".")]
    while numbers and numbers[-1] == 0:
        numbers.pop()
    if not numbers:
        numbers = [0]
    return numbers


def _parse_tagged_number(
    letter: Optional[str],
    number: Optional[str],
) -> Optional[Tuple[str, int]]:
    if not letter:
        return None

    normalized = _VERSION_TAG_NORMALIZE.get(letter.lower())
    if normalized is None:
        raise ValueError(f"Unsupported release tag: {letter!r}")

    value = int(number or 0)
    if value < 0:
        raise ValueError(f"Release number cannot be negative: {value}")
    if value >= _VERSION_OFFSET_SPAN:
        raise ValueError(f"Release number too large: {value}")

    return normalized, value