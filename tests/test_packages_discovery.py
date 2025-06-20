import subprocess
import tempfile
import venv
from pathlib import Path

import pytest

from picopip import get_packages_from_env, get_site_package_paths


@pytest.fixture
def fake_venv(tmp_path):
    venv = tmp_path / "venv"
    site = venv / "lib" / "python3.11" / "site-packages"
    site.mkdir(parents=True)
    return venv, site


def test_get_site_package_paths_basic(fake_venv):
    venv, site = fake_venv
    # Should find the main site-packages
    paths = get_site_package_paths(str(venv))
    assert site in paths


def test_get_site_package_paths_with_pth(fake_venv):
    venv, site = fake_venv
    # Create the extra directory using the exact path as constructed by the code
    expected = (site / "../extra_packages").absolute()
    expected.mkdir(parents=True)
    (site / "extra.pth").write_text("../extra_packages\n")
    paths = get_site_package_paths(str(venv))
    assert expected in paths


def test_get_site_package_paths_ignores_non_dirs(fake_venv):
    venv, site = fake_venv
    (site / "notadir.pth").write_text("not_a_dir\n")
    paths = get_site_package_paths(str(venv))
    # Should not add non-existent or non-dir
    assert not any(p.name == "not_a_dir" for p in paths)


def test_get_site_package_paths_with_system_site_packages(fake_venv, tmp_path):
    venv, site = fake_venv
    # Simulate system site-packages
    sys_site = tmp_path / "system_site"
    sys_site.mkdir()
    (site / "system.pth").write_text(f"{sys_site}\n")
    paths = get_site_package_paths(str(venv))
    assert Path(f"{sys_site}").absolute() in paths or sys_site in paths


def test_get_site_package_paths_with_editable(fake_venv):
    venv, site = fake_venv
    src_dir = venv / "src" / "mypkg"
    src_dir.mkdir(parents=True)
    (site / "mypkg.egg-link").write_text(str(src_dir) + "\n")
    # .egg-link is not a .pth, so should not be included
    paths = get_site_package_paths(str(venv))
    assert src_dir not in paths


def test_get_site_package_paths_with_symlink_in_pth(fake_venv, tmp_path):
    venv, site = fake_venv
    real_dir = tmp_path / "real_extra"
    real_dir.mkdir()
    symlink_dir = tmp_path / "symlink_extra"
    symlink_dir.symlink_to(real_dir, target_is_directory=True)
    (site / "symlinked.pth").write_text(f"{symlink_dir}\n")
    paths = get_site_package_paths(str(venv))
    # The implementation does not resolve symlinks, so check for the symlink path
    assert symlink_dir in paths


def test_get_site_package_paths_with_absolute_pth(fake_venv):
    venv, site = fake_venv
    abs_extra = (venv / "abs_extra_packages").absolute()
    abs_extra.mkdir(parents=True)
    # Write absolute path to .pth file
    (site / "abs_extra.pth").write_text(f"{abs_extra}\n")
    paths = get_site_package_paths(str(venv))
    assert abs_extra in paths


def test_get_site_package_paths_with_relative_pth(fake_venv):
    venv, site = fake_venv
    rel_extra = (site / "../rel_extra_packages").absolute()
    rel_extra.mkdir(parents=True)
    (site / "rel_extra.pth").write_text("../rel_extra_packages\n")
    paths = get_site_package_paths(str(venv))
    assert rel_extra in paths


def make_dist_info(site, name, version):
    dist = site / f"{name}-{version}.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n")
    return dist


def make_egg_info(site, name, version):
    """Create a legacy egg-info package directory."""
    egg_info = site / f"{name}-{version}.egg-info"
    egg_info.mkdir()
    # egg-info uses PKG-INFO instead of METADATA
    (egg_info / "PKG-INFO").write_text(f"Name: {name}\nVersion: {version}\n")
    return egg_info


def test_get_packages_from_env_dist_info(fake_venv):
    venv, site = fake_venv
    make_dist_info(site, "foo", "1.2.3")
    pkgs = get_packages_from_env(str(venv))
    assert ("foo", "1.2.3") in pkgs


def test_get_packages_from_env_with_pth(fake_venv):
    venv, site = fake_venv
    # Create the extra directory using the exact path as constructed by the code
    extra = (site / "../extra").absolute()
    extra.mkdir(parents=True)
    make_dist_info(extra, "baz", "4.5.6")
    (site / "extra.pth").write_text("../extra\n")
    pkgs = get_packages_from_env(str(venv))
    assert ("baz", "4.5.6") in pkgs


def test_get_packages_from_env_editable(fake_venv):
    venv, site = fake_venv
    src_dir = venv / "src" / "mypkg"
    src_dir.mkdir(parents=True)
    (site / "mypkg.egg-link").write_text(str(src_dir) + "\n")
    pkgs = get_packages_from_env(str(venv))
    assert not any(name == "mypkg" for name, _ in pkgs)


def test_get_packages_from_env_malformed(fake_venv):
    venv, site = fake_venv
    dist = site / "broken.dist-info"
    dist.mkdir()
    # No METADATA file
    pkgs = get_packages_from_env(str(venv))
    # Should not raise, just skip
    assert pkgs == []


def test_get_packages_from_env_egg_info(fake_venv):
    """Test that legacy egg-info packages are correctly discovered."""
    venv, site = fake_venv
    make_egg_info(site, "legacy-pkg", "2.1.0")
    pkgs = get_packages_from_env(str(venv))
    assert ("legacy-pkg", "2.1.0") in pkgs


def test_get_packages_from_env_mixed_formats(fake_venv):
    """Test that both dist-info and egg-info packages are discovered together."""
    venv, site = fake_venv
    make_dist_info(site, "modern-pkg", "3.0.0")
    make_egg_info(site, "legacy-pkg", "1.5.0")
    pkgs = get_packages_from_env(str(venv))
    pkg_dict = dict(pkgs)
    assert pkg_dict["modern-pkg"] == "3.0.0"
    assert pkg_dict["legacy-pkg"] == "1.5.0"


def test_get_packages_from_env_egg_info_with_pth(fake_venv):
    """Test that egg-info packages are discovered in paths from .pth files."""
    venv, site = fake_venv
    # Create the extra directory using the exact path as constructed by the code
    extra = (site / "../extra_egg").absolute()
    extra.mkdir(parents=True)
    make_egg_info(extra, "external-legacy", "0.9.5")
    (site / "extra_egg.pth").write_text("../extra_egg\n")
    pkgs = get_packages_from_env(str(venv))
    assert ("external-legacy", "0.9.5") in pkgs


def test_e2e_readme_example():
    with tempfile.TemporaryDirectory() as tmpdir:
        venv.create(tmpdir, with_pip=True)
        subprocess.run(
            [f"{tmpdir}/bin/python", "-m", "pip", "install", "requests"], check=True
        )
        pkgs = get_packages_from_env(tmpdir)
        # Should find at least pip and requests
        pkg_names = {name for name, _ in pkgs}
        assert "pip" in pkg_names
        assert "requests" in pkg_names
