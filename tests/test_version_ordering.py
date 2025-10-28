import pytest

from picopip import parse_version


def test_common_versions_sort_as_expected():
    versions = [
        "1.0.dev1",
        "1.0a1",
        "1.0a2",
        "1.0b1",
        "1.0rc1",
        "1.0",
        "1.0.post1",
    ]

    assert sorted(versions, key=parse_version) == versions


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("1.0", "1.0.0"),
        ("1.2.0", "1.2"),
        ("1.0c1", "1.0rc1"),
        ("1.0-5", "1.0.post5"),
    ],
)
def test_equivalent_versions(left, right):
    assert parse_version(left) == parse_version(right)


def test_local_version_segments_order():
    assert parse_version("1.0.dev1") < parse_version("1.0a1")
    assert parse_version("1.0a1") < parse_version("1.0")
    assert parse_version("1.0") < parse_version("1.0.post1")


def test_invalid_version_raises_value_error():
    with pytest.raises(ValueError, match="Invalid version"):
        parse_version("not a version")


def test_epoch_versions_raise_error():
    with pytest.raises(ValueError, match="Epochs are not supported"):
        parse_version("1!0.9")


def test_local_versions_raise_error():
    with pytest.raises(ValueError, match="Local versions are not supported"):
        parse_version("1.0+abc")


def test_dev_post_versions_raise_error():
    with pytest.raises(ValueError, match="Post releases with dev segments"):
        parse_version("1.0.post1.dev1")


def test_parse_version_matches_expected_offset():
    assert parse_version("1.13.5") == ((1, 13, 5), 0)
    assert parse_version("1.13.5a5")[1] < 0
    assert parse_version("1.13.5.post2")[1] > 0


def test_pre_dev_numbers_larger_than_slot_raise_error():
    with pytest.raises(ValueError, match="Pre-release dev segments are not supported"):
        parse_version("1.0a1.dev99")


def test_large_dev_release_is_supported():
    assert parse_version("1.0.dev9999")[1] < 0


def test_pre_number_out_of_range_is_rejected():
    with pytest.raises(ValueError, match="Release number too large"):
        parse_version("1.0a10000")


def test_dev_release_out_of_range_is_rejected():
    with pytest.raises(ValueError, match="Release number too large"):
        parse_version("1.0.dev10000")


def test_pre_release_dev_is_rejected():
    with pytest.raises(ValueError, match="Pre-release dev segments are not supported"):
        parse_version("1.0a2.dev1")


def test_post_without_number_defaults_to_zero():
    assert parse_version("1.0.post") == parse_version("1.0.post0")


@pytest.mark.parametrize(
    ("longer", "tagged"),
    [
        ("1.2.3.4", "1.2.3.post5"),
        ("1.2.3.4", "1.2.3"),
        ("1.2.3.4", "1.2.3a1"),
        ("1.2.3.4", "1.2.3.dev1"),
        ("1.2.3.4", "1.2.3.post1"),
        ("1.2.3.4", "1.2.3.4.post1"),
    ],
)
def test_release_length_vs_offset(longer, tagged):
    longer_key = parse_version(longer)
    tagged_key = parse_version(tagged)

    if longer_key[0] == tagged_key[0]:
        assert longer_key[1] < tagged_key[1]
    else:
        assert longer_key[0] > tagged_key[0]
