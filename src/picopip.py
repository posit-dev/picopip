"""picopip replicates features of pip within a compact single-file codebase.

Its primary purpose is to provide essential pip-like functionality for
inspecting and interacting with Python virtual environments,
without requiring the installation of pip itself.

This makes picopip ideal for vendoring alongside software that needs
 to query or manage virtual environments in a self-contained manner.

Note: This tool only supports modern Python packaging metadata (.dist-info)
and does not support legacy .egg-info or .egg formats.
"""
import logging
from importlib.metadata import PathDistribution
from pathlib import Path

log = logging.getLogger(__name__)


def get_site_package_paths(venv_path: str) -> set[Path]:
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
                "Invalid .pth files %s: %s", pth_file, exc,
            )
            continue

    return scan_paths


def get_packages_from_env(venv_path: str) -> list[tuple[str, str]]:
    """Return a list of (name, version) for all installed packages in the given venv."""
    packages = []
    for path in get_site_package_paths(venv_path):
        for dist_info in path.glob("*.dist-info"):
            try:
                dist = PathDistribution(dist_info)
                name = dist.metadata["Name"]
                version = dist.version
                if not name:
                    log.error(
                        "Missing package name in metadata for %s (skipping entry)", dist_info
                    )
                    continue
                packages.append((name, version))
            except Exception as exc:
                log.warning(
                    "Failed to read package metadata for %s: %s", dist_info, exc,
                )
                continue
    return sorted(packages, key=lambda x: x[0].lower())
