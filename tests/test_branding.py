"""Tests for the branding/theming single source of truth."""
import pytest

from src import branding


def test_every_theme_defines_the_same_keys():
    required = {"bg", "surface", "surface2", "primary", "secondary", "accent",
                "text", "muted", "success", "warning", "danger", "gradient"}
    for name, palette in branding.THEMES.items():
        missing = required - set(palette)
        assert not missing, f"{name} is missing {missing}"


def test_use_switches_active_theme():
    branding.use("Ocean")
    assert branding.active_name() == "Ocean"
    branding.use("Aurora")
    assert branding.active_name() == "Aurora"


def test_unknown_theme_falls_back_to_default():
    branding.use("DoesNotExist")
    assert branding.active_name() == "Aurora"


def test_hex_to_bgr_swaps_channels():
    # #112233 → R=0x11 G=0x22 B=0x33 → BGR (0x33, 0x22, 0x11)
    assert branding.hex_to_bgr("#112233") == (0x33, 0x22, 0x11)
    assert branding.hex_to_bgr("112233") == (0x33, 0x22, 0x11)


def test_hx_returns_hex_string():
    val = branding.hx("primary", "Aurora")
    assert val.startswith("#") and len(val) == 7


def test_bgr_is_three_byte_tuple():
    b = branding.bgr("accent", "Cyber")
    assert len(b) == 3 and all(0 <= c <= 255 for c in b)


def test_gradient_is_list_of_hex():
    g = branding.gradient("Sunset")
    assert isinstance(g, list) and len(g) >= 2
    assert all(c.startswith("#") for c in g)


@pytest.mark.parametrize("name", list(branding.THEMES))
def test_all_theme_colours_are_valid_hex(name):
    for key, val in branding.THEMES[name].items():
        if key == "gradient":
            continue
        assert isinstance(val, str) and len(val) == 7
        int(val[1:], 16)        # raises if not hex
