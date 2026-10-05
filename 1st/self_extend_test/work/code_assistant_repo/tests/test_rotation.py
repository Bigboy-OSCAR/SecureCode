from services.markers import derive_rotation_marker_buggy


def test_rotation_marker_keeps_zero_padding() -> None:
    assert derive_rotation_marker_buggy("apac", 7) == "ROTATE::APAC::0007"
