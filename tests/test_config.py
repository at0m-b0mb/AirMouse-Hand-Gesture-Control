"""Tests for Config: defaults, validation/clamping, profiles, persistence."""
import json

import pytest

import config as config_mod
from config import Config, PROFILES


def test_defaults_are_sane():
    c = Config()
    assert 0.3 <= c.sensitivity <= 3.0
    assert c.theme in ("Aurora", "Cyber", "Mono", "Sunset", "Ocean")
    assert c.camera_index == -1


def test_validate_clamps_out_of_range():
    c = Config()
    c.sensitivity = 99.0
    c.scroll_speed = 999
    c.detection_confidence = 5.0
    c.oe_beta = -1.0
    c.validate()
    assert c.sensitivity == 3.0
    assert c.scroll_speed == 20
    assert c.detection_confidence == 1.0
    assert c.oe_beta == 0.001


def test_validate_keeps_click_release_above_threshold():
    c = Config()
    c.click_threshold = 0.2
    c.click_release = 0.05          # below threshold — would break hysteresis
    c.validate()
    assert c.click_release > c.click_threshold


def test_validate_returns_self():
    c = Config()
    assert c.validate() is c


def test_apply_and_match_profile():
    c = Config()
    assert c.apply_profile("Precision") is True
    assert c.profile == "Precision"
    assert c.matches_profile("Precision") is True
    assert c.matches_profile("Gaming") is False


def test_apply_unknown_profile_is_false():
    c = Config()
    assert c.apply_profile("Nope") is False


def test_all_profiles_apply_cleanly():
    for name in PROFILES:
        c = Config()
        assert c.apply_profile(name)
        assert c.matches_profile(name)


def test_save_load_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_PATH", path)
    c = Config()
    c.sensitivity = 1.9
    c.theme = "Ocean"
    c.save()
    loaded = Config.load()
    assert loaded.sensitivity == pytest.approx(1.9)
    assert loaded.theme == "Ocean"


def test_load_clamps_bad_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_PATH", path)
    path.write_text(json.dumps({"sensitivity": 500, "scroll_speed": -5}))
    loaded = Config.load()
    assert loaded.sensitivity == 3.0
    assert loaded.scroll_speed == 1


def test_load_corrupt_file_returns_defaults(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_PATH", path)
    path.write_text("{ not json")
    loaded = Config.load()
    assert loaded.sensitivity == Config().sensitivity


def test_load_ignores_unknown_keys(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "_PATH", path)
    path.write_text(json.dumps({"sensitivity": 1.5, "bogus_field": 123}))
    loaded = Config.load()
    assert loaded.sensitivity == pytest.approx(1.5)
    assert not hasattr(loaded, "bogus_field")
