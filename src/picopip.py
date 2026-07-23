# Copyright (C) 2025 by Posit Software, PBC.

"""picopip replicates features of pip within a compact single-file codebase.

Its primary purpose is to provide essential pip-like functionality for
inspecting and interacting with Python virtual environments,
without requiring the installation of pip itself.

This makes picopip ideal for vendoring alongside software that needs
 to query or manage virtual environments in a self-contained manner.

Version: 0.6.1
Author: Alessandro Molina <alessandro.molina@posit.co>
URL: https://github.com/posit-dev/picopip
License: MIT
"""

import itertools
import logging
import operator
import os
import re
import site
from importlib.metadata import PathDistribution
from pathlib import Path
from typing import Callable, List, Optional, Tuple

log = logging.getLogger(__name__)


def get_site_package_paths(
    venv_path: str, *, include_system_packages: bool = True
) -> List[Path]:
    """Return all directories where packages might be installed for the given venv."""
    matches = sorted((Path(venv_path) / "lib").glob("python*/site-packages"))
    if not matches:
        raise NotADirectoryError(
            f"Cannot locate site-packages in {venv_path}/lib/python*/site-packages"
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple python site-packages found under {venv_path}/lib: {matches}"
        )
    site_packages = matches[0]

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
        _extend_unique(scan_paths, seen, _find_system_packages(venv_path))
        _extend_unique(scan_paths, seen, _find_pythonpath_packages())

    return scan_paths


def get_packages_from_env(
    venv_path: str,
    *,
    ignore_system_packages: bool = False,
    path_as_target: bool = False,
) -> List[Tuple[str, str]]:
    """Return a list of (name, version) for all installed packages in the given venv.

    :param str venv_path: Path to a virtual environment, or to a flat directory
        of installed packages when ``path_as_target`` is True.
    :param bool ignore_system_packages: Exclude system site-packages and
        PYTHONPATH entries. Ignored when ``path_as_target`` is True.
    :param bool path_as_target: Treat ``venv_path`` as the site-packages
        directory itself (e.g. the output of ``pip install --target <dir>``).
        Skips venv layout, ``.pth`` expansion, system, and PYTHONPATH discovery.
    """

    def _canonical_name(name: str) -> str:
        """PEP 503 normalization plus dashes as underscores."""
        return re.sub(r"[-_.]+", "-", name).lower().replace("-", "_")

    if path_as_target:
        scan_paths = [Path(venv_path)]
    else:
        scan_paths = get_site_package_paths(
            venv_path, include_system_packages=not ignore_system_packages
        )

    seen = set()
    packages = []
    for path in scan_paths:
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        log.debug(f"Scanning {path} for installed packages...")
        for dist_info in itertools.chain(
            path.glob("*.dist-info"), path.glob("*.egg-info")
        ):
            log.debug(f"Found distribution info: {dist_info}")
            try:
                dist = PathDistribution(dist_info)
                raw_name = dist.metadata.get("Name")
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


def get_package_version_from_env(
    venv_path: str,
    package_name: str,
    *,
    ignore_system_packages: bool = False,
    path_as_target: bool = False,
) -> Optional[str]:
    """Return the version of a package installed in the given venv.

    Returns None if not found or not installed. Both ``ignore_system_packages``
    and ``path_as_target`` are forwarded to :func:`get_packages_from_env` with
    the same semantics.

    :param str venv_path: Path to a virtual environment, or to a flat directory
        of installed packages when ``path_as_target`` is True.
    :param str package_name: Name of the package to look up. Matched
        case-insensitively against the raw distribution names.
    :param bool ignore_system_packages: Exclude system site-packages and
        PYTHONPATH entries. Ignored when ``path_as_target`` is True.
    :param bool path_as_target: Treat ``venv_path`` as the site-packages
        directory itself (e.g. the output of ``pip install --target <dir>``).
    """
    packages = get_packages_from_env(
        venv_path,
        ignore_system_packages=ignore_system_packages,
        path_as_target=path_as_target,
    )
    for name, version in packages:
        if name.lower() == package_name.lower():
            return version
    return None


def _extend_unique(scan_paths: List[Path], seen: set, new_paths: List[Path]) -> None:
    """Append paths to scan_paths that are not already in seen."""
    for path in new_paths:
        if path not in seen:
            scan_paths.append(path)
            seen.add(path)


def _find_pythonpath_packages() -> List[Path]:
    """Return existing directories listed in the PYTHONPATH environment variable.

    PYTHONPATH is read from the process running picopip, which may differ from
    the interpreter that will import from the venv. Results are only meaningful
    when the two processes share the same PYTHONPATH value.
    """
    scan_paths = []
    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if entry:
            pp = Path(entry).resolve()
            if pp.exists() and pp.is_dir():
                scan_paths.append(pp)
    return scan_paths


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
                        path = Path(sys_path)
                        if path.exists() and path.is_dir():
                            scan_paths.append(path)
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


def parse_constraints(
    spec: str,
) -> Tuple[Optional[str], List[Tuple[Callable, Tuple[Tuple[int, ...], int]]]]:
    """Parse a requirement spec into ``(name, [(comparator, parsed_version), ...])``.

    Accepts either a bare spec (``">= 0.8, < 1.0"``) or a full requirement
    line (``"aiokafka >= 0.8, < 1.0"``). Any text before the first operator is
    returned as the package name (with original case preserved); ``None`` when
    the spec is bare.

    ``~= V`` is expanded into the equivalent ``>= V`` and ``< V'`` pair, where
    ``V'`` drops the last segment of ``V`` and bumps the new last, per PEP 440.
    """
    ops = {
        "==": operator.eq,
        "!=": operator.ne,
        ">=": operator.ge,
        "<=": operator.le,
        ">": operator.gt,
        "<": operator.lt,
    }
    matches = list(re.finditer(r"(===|==|!=|<=|>=|~=|<|>)\s*([^\s,]+)", spec))
    name = (spec[: matches[0].start()] if matches else spec).strip() or None
    constraints = []
    for m in matches:
        op, ver = m.group(1), m.group(2)
        if op == "~=":
            # PEP 440 ~= upper bound: drop the last segment, bump the new last.
            # e.g. "1.4.5" -> head=["1","4"] -> ["1","5"] -> upper "1.5"
            *head, _ = ver.split(".")
            if not head:
                raise ValueError(
                    f"~= requires a multi-segment version: {ver!r}",
                )
            head[-1] = str(int(head[-1]) + 1)
            constraints.append((operator.ge, parse_version(ver)))
            constraints.append((operator.lt, parse_version(".".join(head))))
        else:
            constraints.append((ops[op], parse_version(ver)))
    return name, constraints


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
