import subprocess
import tempfile
import venv
from pathlib import Path

from picopip import get_package_version_from_env


def install_and_check_version(pkg_name):
    with tempfile.TemporaryDirectory() as tmpdir:
        venv.create(tmpdir, with_pip=True)
        python_bin = Path(tmpdir) / "bin" / "python"
        subprocess.run([str(python_bin), "-m", "pip", "install", pkg_name], check=True)
        # Get expected version using pip show
        result = subprocess.run(
            [str(python_bin), "-m", "pip", "show", pkg_name],
            capture_output=True,
            text=True,
            check=True,
        )
        expected_version = None
        for line in result.stdout.splitlines():
            if line.startswith("Version:"):
                expected_version = line.split(":", 1)[1].strip()
                break
        version = get_package_version_from_env(tmpdir, pkg_name)
        assert version == expected_version, (
            f"{pkg_name} version mismatch: got {version}, expected {expected_version}"
        )
        return version


def test_jupyter_version():
    install_and_check_version("jupyter")


def test_nbconvert_version():
    install_and_check_version("nbconvert")


def test_ipykernel_version():
    install_and_check_version("ipykernel")


def test_pip_version():
    install_and_check_version("pip")


def test_setuptools_version():
    install_and_check_version("setuptools")


def test_nonexistent_package():
    with tempfile.TemporaryDirectory() as tmpdir:
        venv.create(tmpdir, with_pip=True)
        version = get_package_version_from_env(tmpdir, "NOT_EXISTING_PACKAGE")
        assert version is None


def test_get_package_version_from_env_egg_info():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake venv structure
        venv_path = Path(tmpdir) / "venv"
        site = venv_path / "lib" / "python3.11" / "site-packages"
        site.mkdir(parents=True)

        # Create an egg-info package
        egg_info = site / "legacy-package-1.2.3.egg-info"
        egg_info.mkdir()
        (egg_info / "PKG-INFO").write_text("Name: legacy-package\nVersion: 1.2.3\n")

        # Test version lookup
        version = get_package_version_from_env(str(venv_path), "legacy-package")
        assert version == "1.2.3"

        # Test case-insensitive lookup
        version = get_package_version_from_env(str(venv_path), "LEGACY-PACKAGE")
        assert version == "1.2.3"
