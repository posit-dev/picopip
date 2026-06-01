import os
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


def test_get_packages_from_env_canonical_dedup(fake_venv):
    """Packages differing only by dashes/underscores should be deduped."""
    venv, site = fake_venv
    make_dist_info(site, "pure-eval", "0.2.2")
    extra = (site / "../dupe_extra").absolute()
    extra.mkdir(parents=True)
    make_dist_info(extra, "pure_eval", "0.2.3")
    (site / "dupe_extra.pth").write_text("../dupe_extra\n")
    pkgs = get_packages_from_env(str(venv))
    assert pkgs == [("pure-eval", "0.2.2")]


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


def test_get_packages_from_env_ignore_system_packages(tmp_path, monkeypatch):
    """System packages should be omitted when ignore_system_packages is True."""
    venv_dir = tmp_path / "venv"
    site_dir = venv_dir / "lib" / "python3.11" / "site-packages"
    site_dir.mkdir(parents=True)
    (venv_dir / "pyvenv.cfg").write_text("include-system-site-packages = true\n")

    system_site = tmp_path / "system_site"
    system_site.mkdir()
    make_dist_info(system_site, "system-pkg", "0.1.0")

    monkeypatch.setattr("picopip.site.getsitepackages", lambda: [str(system_site)])

    pkgs = get_packages_from_env(str(venv_dir))
    assert ("system-pkg", "0.1.0") in pkgs

    pkgs = get_packages_from_env(str(venv_dir), ignore_system_packages=True)
    assert ("system-pkg", "0.1.0") not in pkgs


def test_get_site_package_paths_includes_pythonpath(fake_venv, tmp_path, monkeypatch):
    """PYTHONPATH directories should be included in scan paths."""
    venv, _site = fake_venv
    pythonpath_dir = tmp_path / "pythonpath_packages"
    pythonpath_dir.mkdir()
    monkeypatch.setenv("PYTHONPATH", str(pythonpath_dir))
    paths = get_site_package_paths(str(venv))
    assert pythonpath_dir.resolve() in [p.resolve() for p in paths]


def test_get_site_package_paths_excludes_pythonpath_without_system(
    fake_venv, tmp_path, monkeypatch
):
    """PYTHONPATH should be excluded when include_system_packages is False."""
    venv, _site = fake_venv
    pythonpath_dir = tmp_path / "pythonpath_packages"
    pythonpath_dir.mkdir()
    monkeypatch.setenv("PYTHONPATH", str(pythonpath_dir))
    paths = get_site_package_paths(str(venv), include_system_packages=False)
    assert pythonpath_dir.resolve() not in [p.resolve() for p in paths]


def test_get_site_package_paths_pythonpath_empty(fake_venv, monkeypatch):
    """Empty PYTHONPATH should not cause errors."""
    venv, _site = fake_venv
    monkeypatch.setenv("PYTHONPATH", "")
    paths = get_site_package_paths(str(venv))
    assert len(paths) >= 1


def test_get_site_package_paths_pythonpath_unset(fake_venv, monkeypatch):
    """Unset PYTHONPATH should not cause errors."""
    venv, _site = fake_venv
    monkeypatch.delenv("PYTHONPATH", raising=False)
    paths = get_site_package_paths(str(venv))
    assert len(paths) >= 1


def test_get_site_package_paths_pythonpath_nonexistent(fake_venv, monkeypatch):
    """Nonexistent PYTHONPATH directories should be silently ignored."""
    venv, _site = fake_venv
    monkeypatch.setenv("PYTHONPATH", "/nonexistent/path/that/does/not/exist")
    paths = get_site_package_paths(str(venv))
    assert not any(str(p) == "/nonexistent/path/that/does/not/exist" for p in paths)


def test_get_site_package_paths_pythonpath_multiple(fake_venv, tmp_path, monkeypatch):
    """Multiple PYTHONPATH entries should all be included."""
    venv, _site = fake_venv
    dir_a = tmp_path / "path_a"
    dir_b = tmp_path / "path_b"
    dir_a.mkdir()
    dir_b.mkdir()
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(dir_a), str(dir_b)]))
    paths = get_site_package_paths(str(venv))
    resolved = [p.resolve() for p in paths]
    assert dir_a.resolve() in resolved
    assert dir_b.resolve() in resolved


def test_get_packages_from_env_finds_pythonpath_packages(
    fake_venv, tmp_path, monkeypatch
):
    """Packages in PYTHONPATH directories should be discovered."""
    venv, _site = fake_venv
    pythonpath_dir = tmp_path / "pythonpath_packages"
    pythonpath_dir.mkdir()
    make_dist_info(pythonpath_dir, "external-pkg", "2.0.0")
    monkeypatch.setenv("PYTHONPATH", str(pythonpath_dir))
    pkgs = get_packages_from_env(str(venv))
    assert ("external-pkg", "2.0.0") in pkgs


def test_get_packages_from_env_ignores_pythonpath_with_ignore_system(
    fake_venv, tmp_path, monkeypatch
):
    """PYTHONPATH packages should be excluded when ignore_system_packages is True."""
    venv, _site = fake_venv
    pythonpath_dir = tmp_path / "pythonpath_packages"
    pythonpath_dir.mkdir()
    make_dist_info(pythonpath_dir, "external-pkg", "2.0.0")
    monkeypatch.setenv("PYTHONPATH", str(pythonpath_dir))
    pkgs = get_packages_from_env(str(venv), ignore_system_packages=True)
    assert ("external-pkg", "2.0.0") not in pkgs


def test_get_packages_from_env_path_as_target(tmp_path):
    """path_as_target scans the given directory directly for dist-info entries."""
    target = tmp_path / "target"
    target.mkdir()
    make_dist_info(target, "foo", "1.2.3")
    make_egg_info(target, "legacy", "0.9.0")
    pkgs = get_packages_from_env(str(target), path_as_target=True)
    assert pkgs == [("foo", "1.2.3"), ("legacy", "0.9.0")]


def test_get_packages_from_env_path_as_target_skips_venv_layout(tmp_path):
    """path_as_target must not require a lib/pythonX.Y/site-packages structure."""
    target = tmp_path / "flat_target"
    target.mkdir()
    # No lib/pythonX.Y/site-packages here; the default mode would raise.
    make_dist_info(target, "foo", "1.0.0")
    pkgs = get_packages_from_env(str(target), path_as_target=True)
    assert pkgs == [("foo", "1.0.0")]


def test_get_packages_from_env_path_as_target_ignores_pth_and_pythonpath(
    tmp_path, monkeypatch
):
    """path_as_target must not expand .pth files or read PYTHONPATH."""
    target = tmp_path / "target"
    target.mkdir()
    make_dist_info(target, "foo", "1.0.0")

    # A sibling directory referenced from a .pth file must be ignored.
    extra = tmp_path / "extra"
    extra.mkdir()
    make_dist_info(extra, "from-pth", "9.9.9")
    (target / "extra.pth").write_text("../extra\n")

    # PYTHONPATH must also be ignored.
    pythonpath_dir = tmp_path / "pp"
    pythonpath_dir.mkdir()
    make_dist_info(pythonpath_dir, "from-pythonpath", "1.1.1")
    monkeypatch.setenv("PYTHONPATH", str(pythonpath_dir))

    pkgs = get_packages_from_env(str(target), path_as_target=True)
    assert pkgs == [("foo", "1.0.0")]


def test_get_site_package_paths_missing_layout_raises(tmp_path):
    """An invalid venv (no lib/pythonX.Y/site-packages) must fail loudly."""
    bogus = tmp_path / "not_a_venv"
    bogus.mkdir()
    with pytest.raises(NotADirectoryError):
        get_site_package_paths(str(bogus))


def test_get_site_package_paths_multiple_versions_raises(tmp_path):
    """A venv with more than one python site-packages is ambiguous."""
    venv = tmp_path / "venv"
    (venv / "lib" / "python3.11" / "site-packages").mkdir(parents=True)
    (venv / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    with pytest.raises(RuntimeError):
        get_site_package_paths(str(venv))


def test_get_packages_from_env_path_as_target_missing_dir_raises(tmp_path):
    """A nonexistent target path must raise instead of silently returning []."""
    missing = tmp_path / "does_not_exist"
    with pytest.raises(NotADirectoryError):
        get_packages_from_env(str(missing), path_as_target=True)


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
