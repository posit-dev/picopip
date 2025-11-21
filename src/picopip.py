# Copyright (C) 2025 by Posit Software, PBC.

"""picopip replicates features of pip within a compact single-file codebase.

Its primary purpose is to provide essential pip-like functionality for
inspecting and interacting with Python virtual environments,
without requiring the installation of pip itself.

This makes picopip ideal for vendoring alongside software that needs
 to query or manage virtual environments in a self-contained manner.

Version: 0.4.0
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

log = logging.getLogger(__name__)


def get_site_package_paths(
    venv_path: str, *, include_system_packages: bool = True
) -> List[Path]:
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

    if include_system_packages:
        # Append system packages at the end, so that venv site-packages take precedence
        for system_path in _find_system_packages(venv_path):
            if system_path not in seen:
                scan_paths.append(system_path)
                seen.add(system_path)

    return scan_paths


def get_packages_from_env(
    venv_path: str, *, ignore_system_packages: bool = False
) -> List[Tuple[str, str]]:
    """Return a list of (name, version) for all installed packages in the given venv."""

    def _canonical_name(name: str) -> str:
        """PEP 503 normalization plus dashes as underscores."""
        return re.sub(r"[-_.]+", "-", name).lower().replace("-", "_")

    seen = set()
    packages = []
    for path in get_site_package_paths(
        venv_path, include_system_packages=not ignore_system_packages
    ):
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
                name = _canonical_name(raw_name)
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


def parse_version(version: str) -> Tuple[Tuple[int, ...], int]:
    """Parse the given version string and return a tuple suitable for comparison.

    dev, pre, rc, alpha, beta, post releases are supported,
    and represented as a numeric offset from the release number.
    Negative offsets signal pre-releases, positive offsets signal post-releases.

    Epochs and local versions are not supported.

    Raises ValueError if the version string is invalid or unsupported.
    """
    return _VersionParser(version).parse_key()


class _VersionParser:
    """Parse and normalize a version string according to PEP 440.

    Implements a subset of PEP 440 sufficient for practical version comparison,
    excluding epochs (e.g. "1!1.0.0") and local versions (e.g. "1.0.0+abc") which
    are rarely used in released packages.

    It also excludes support for combining pre-releases with dev or post
    releases, which only make sense during development (e.g. "1.0.0rc1.dev2").
    """

    # This comes from https://packaging.python.org/en/latest/specifications/version-specifiers/#appendix-parsing-version-strings-with-regular-expressions
    VERSION_PATTERN = r"""
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

    VERSION_REGEX = re.compile(
        r"^\s*" + VERSION_PATTERN + r"\s*$", re.VERBOSE | re.IGNORECASE
    )

    TAG_NORMALIZE = {
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

    # To simplify representing pre/post/dev stages as integers for comparison,
    # we assign each stage a base offset, and add the stage number to it.
    # For example, "1.0.0rc2" becomes ( (1,0,0), -9998 ), while
    # "1.0.0post3" becomes ( (1,0,0), 10003 ).
    # This guarantees that releases are always sortable as simple numeric tuples.
    OFFSET_STAGE_SPAN = 10_000  # 9999 pre/post/dev stages per release should be enough.
    OFFSET_BASE = {  # dev < a < b < rc < release < post
        "dev": -4 * OFFSET_STAGE_SPAN,
        "a": -3 * OFFSET_STAGE_SPAN,
        "b": -2 * OFFSET_STAGE_SPAN,
        "rc": -1 * OFFSET_STAGE_SPAN,
        "release": 0,
        "post": OFFSET_STAGE_SPAN,
    }

    def __init__(self, version: str) -> None:
        self.version = version

    def parse_key(self) -> Tuple[Tuple[int, ...], int]:
        """Return a tuple implementing practical PEP 440 ordering for the version."""
        match = self.VERSION_REGEX.search(self.version)
        if not match:
            raise ValueError(f"Invalid version: {self.version!r}")

        if match.group("epoch"):
            raise ValueError(f"Epochs are not supported: {self.version!r}")
        if match.group("local"):
            raise ValueError(f"Local versions are not supported: {self.version!r}")

        release_numbers = self._normalize_release(match.group("release"))

        pre = None
        pre_letter = match.group("pre_l")
        pre_number = match.group("pre_n")
        if pre_letter:
            pre = self._parse_tagged_number(pre_letter, pre_number)

        # post releases are the only case where the number can be specified
        # without a tag. In such case we treat it as "postN".
        post = None
        post_number = match.group("post_n1") or match.group("post_n2")
        post_letter = match.group("post_l") or ("post" if post_number else None)
        if post_letter:
            post = self._parse_tagged_number(post_letter, post_number)

        dev = None
        dev_letter = match.group("dev_l")
        dev_number = match.group("dev_n")
        if dev_letter:
            dev = self._parse_tagged_number(dev_letter, dev_number)

        if post and dev:
            raise ValueError(
                f"Post releases with dev segments are not supported: {self.version!r}"
            )
        if pre and dev:
            raise ValueError(
                f"Pre-release dev segments are not supported: {self.version!r}"
            )

        component = pre or dev or post or ("release", 0)
        offset = self.OFFSET_BASE[component[0]] + component[1]
        return (tuple(release_numbers), offset)

    def _normalize_release(self, release: str) -> List[int]:
        numbers = [int(part) for part in release.split(".")]
        while numbers and numbers[-1] == 0:
            numbers.pop()
        if not numbers:
            numbers = [0]
        return numbers

    def _parse_tagged_number(
        self,
        letter: Optional[str],
        number: Optional[str],
    ) -> Optional[Tuple[str, int]]:
        if not letter:
            return None

        normalized = self.TAG_NORMALIZE.get(letter.lower())
        if normalized is None:
            raise ValueError(f"Unsupported release tag: {letter!r}")

        value = int(number or 0)
        if value < 0:
            raise ValueError(f"Release number cannot be negative: {value}")
        if value >= self.OFFSET_STAGE_SPAN:
            raise ValueError(f"Release number too large: {value}")

        return normalized, value
