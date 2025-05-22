import pytest

from picopip import get_packages_from_env, get_site_package_paths
from pathlib import Path


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
