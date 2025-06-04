# Copyright (C) 2025 by Posit Software, PBC.

"""picopip replicates features of pip within a compact single-file codebase.

Its primary purpose is to provide essential pip-like functionality for
inspecting and interacting with Python virtual environments,
without requiring the installation of pip itself.

This makes picopip ideal for vendoring alongside software that needs
 to query or manage virtual environments in a self-contained manner.

Note: This tool only supports modern Python packaging metadata (.dist-info)
and does not support legacy .egg-info or .egg formats.

Version: 0.2.0
Author: Alessandro Molina <alessandro.molina@posit.co>
URL: https://github.com/posit-dev/picopip
License: MIT
"""

import site
import logging
from importlib.metadata import PathDistribution
from pathlib import Path
from typing import List, Optional, Set, Tuple

log = logging.getLogger(__name__)


def get_site_package_paths(venv_path: str) -> Set[Path]:
    """Return all directories where packages might be installed for the given venv."""
    for version_dir in (Path(venv_path) / "lib").iterdir():
        if version_dir.name.startswith("python"):
            site_packages = version_dir / "site-packages"
            break
    else:
        msg = "Cannot locate site-packages in lib/pythonX.Y"
        raise RuntimeError(msg)

    scan_paths = {site_packages.absolute()}

    for pth_file in site_packages.glob("*.pth"):
        try:
            with pth_file.open() as f:
                for pth_line in f:
                    line = pth_line.strip()
                    if not line or line.startswith("#") or "import" in line:
                        continue
                    pth_path = (site_packages / line).absolute()
                    if pth_path.exists() and pth_path.is_dir():
                        scan_paths.add(pth_path)
        except Exception as exc:
            # Ignore unreadable or malformed .pth
            log.warning(
                "Invalid .pth files %s: %s",
                pth_file,
                exc,
            )
            continue

    # Include system site-packages if enabled in venv
    # See https://github.com/python/cpython/blob/a10b321a5807ba924c7a7833692fe5d0dc40e875/Lib/site.py#L618-L632
    cfg_path = Path(venv_path) / "pyvenv.cfg"
    if cfg_path.exists():
        content = cfg_path.read_text().splitlines()
        for line in content:
            line = line.strip().lower()
            if line.startswith("include-system-site-packages"):
                include_system_site = line.split("=", 1)[1].strip()
                if include_system_site == "true":
                    for sys_path in site.getsitepackages():
                        scan_paths.add(Path(sys_path))
                break

    return scan_paths


def get_packages_from_env(venv_path: str) -> List[Tuple[str, str]]:
    """Return a list of (name, version) for all installed packages in the given venv."""
    packages = []
    for path in get_site_package_paths(venv_path):
        log.debug(f"Scanning {path} for installed packages...")
        for dist_info in path.glob("*.dist-info"):
            log.debug(f"Found distribution info: {dist_info}")
            try:
                dist = PathDistribution(dist_info)
                name = dist.metadata["Name"]
                version = dist.version
                if not name:
                    log.error(
                        "Missing package name in metadata for %s (skipping entry)",
                        dist_info,
                    )
                    continue
                packages.append((name, version))
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
