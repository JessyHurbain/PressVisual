"""Chargement, validation et persistance de ``Config``."""

from __future__ import annotations

import json

import pytest

import pressvisual


def write_json(path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Chargement
# ---------------------------------------------------------------------------


def test_defaults_need_no_correction():
    assert pressvisual.Config().validate() == []


def test_load_missing_file_keeps_defaults(tmp_path):
    warnings: list[str] = []
    config = pressvisual.Config.load(tmp_path / "absent.json", warnings.append)

    assert warnings == []
    assert config.path == tmp_path / "absent.json"
    assert config.opacity == pytest.approx(0.86)
    assert config.position == "bottom-right"


def test_load_applies_keys_and_signals_unknown_ones(tmp_path):
    path = tmp_path / "config.json"
    write_json(path, {"opacity": 0.5, "font_family": "Inter", "inconnue": 1})
    warnings: list[str] = []

    config = pressvisual.Config.load(path, warnings.append)

    assert config.opacity == 0.5
    assert config.font_family == "Inter"
    assert any("inconnue" in warning for warning in warnings)


def test_load_ignores_reserved_path_key(tmp_path):
    path = tmp_path / "config.json"
    write_json(path, {"path": "/tmp/ailleurs.json"})
    warnings: list[str] = []

    config = pressvisual.Config.load(path, warnings.append)

    assert config.path == path
    assert any("path" in warning for warning in warnings)


def test_load_invalid_json_keeps_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ pas du json", encoding="utf-8")
    warnings: list[str] = []

    config = pressvisual.Config.load(path, warnings.append)

    assert warnings and "illisible" in warnings[0]
    assert config.opacity == pytest.approx(0.86)


def test_load_non_object_keeps_defaults(tmp_path):
    path = tmp_path / "config.json"
    write_json(path, [1, 2, 3])
    warnings: list[str] = []

    config = pressvisual.Config.load(path, warnings.append)

    assert warnings and "objet JSON" in warnings[0]
    assert config.font_size == 16


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_clamps_out_of_range_values():
    config = pressvisual.Config(
        opacity=4.0,
        font_size=200,
        display_duration=0.0,
        max_rows=99,
        margin=-5,
    )

    notes = config.validate()

    assert config.opacity == 1.0
    assert config.font_size == 40
    assert config.display_duration == 0.3
    assert config.max_rows == 8
    assert config.margin == 0
    assert len(notes) >= 5


def test_validate_converts_numeric_strings():
    config = pressvisual.Config(opacity="0.5", corner_radius="24")

    config.validate()

    assert config.opacity == 0.5
    assert config.corner_radius == 24


def test_validate_falls_back_when_conversion_fails():
    config = pressvisual.Config(font_size="beaucoup")

    notes = config.validate()

    assert config.font_size == 16
    assert any("font_size" in note for note in notes)


def test_validate_replaces_invalid_colors():
    config = pressvisual.Config(text_color="pas une couleur", accent_color=12)

    notes = config.validate()

    assert config.text_color == pressvisual.Config.text_color
    assert config.accent_color == pressvisual.Config.accent_color
    assert len([note for note in notes if "couleur" in note]) == 2


def test_validate_keeps_translucent_colors():
    config = pressvisual.Config(background_color="#80262f3f")

    config.validate()

    assert config.background_color.lower() == "#80262f3f"


def test_validate_converts_boolean_aliases():
    config = pressvisual.Config(
        capture_mouse="non",
        ignore_key_repeats=0,
        concat_text="oui",
        start_hidden=None,
    )

    config.validate()

    assert config.capture_mouse is False
    assert config.ignore_key_repeats is False
    assert config.concat_text is True
    assert config.start_hidden is True


def test_validate_normalises_filtered_keys():
    config = pressvisual.Config(filtered_keys=["A", "Espace", 12])

    config.validate()

    assert config.filtered_keys == ["a", "espace", "12"]


def test_validate_resets_filtered_keys_when_not_a_list():
    config = pressvisual.Config(filtered_keys="a,b")

    notes = config.validate()

    assert config.filtered_keys == []
    assert any("filtered_keys" in note for note in notes)


def test_validate_falls_back_on_unknown_position():
    config = pressvisual.Config(position="milieu")

    notes = config.validate()

    assert config.position == "bottom-right"
    assert any("position" in note for note in notes)


def test_validate_trims_text_settings():
    config = pressvisual.Config(font_family="  Inter  ", hotkey_toggle=" ctrl+f12 ")

    config.validate()

    assert config.font_family == "Inter"
    assert config.hotkey_toggle == "ctrl+f12"


# ---------------------------------------------------------------------------
# Persistance
# ---------------------------------------------------------------------------


def test_remember_position_preserves_unrelated_keys(tmp_path):
    path = tmp_path / "config.json"
    write_json(path, {"display_duration": 5.0, "inconnue": "gardée"})
    config = pressvisual.Config.load(path, lambda _message: None)

    assert config.remember_position("top-left") is True

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["position"] == "top-left"
    assert data["display_duration"] == 5.0
    assert data["inconnue"] == "gardée"


def test_remember_position_rejects_unknown_value(tmp_path):
    path = tmp_path / "config.json"
    write_json(path, {"position": "bottom-right"})
    config = pressvisual.Config.load(path, lambda _message: None)

    assert config.remember_position("milieu") is False
    assert json.loads(path.read_text(encoding="utf-8"))["position"] == "bottom-right"


def test_remember_position_without_file_writes_nothing():
    config = pressvisual.Config()
    assert config.path is None

    assert config.remember_position("top-right") is True


def test_save_appearance_round_trip(tmp_path):
    path = tmp_path / "config.json"
    write_json(path, {"position": "top-left", "display_duration": 4.0})
    config = pressvisual.Config.load(path, lambda _message: None)

    saved = config.save_appearance(
        {
            "opacity": 0.5,
            "font_family": "Inter",
            "font_size": 22,
            "max_width": 700,
            "corner_radius": 4,
            "margin": 40,
            "accent_color": "#ff8800",
            "display_duration": 99.0,  # hors périmètre : doit être ignoré
        }
    )

    assert saved is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["accent_color"] == "#ff8800"
    assert data["font_size"] == 22
    assert data["position"] == "top-left"
    assert data["display_duration"] == 4.0

    reloaded = pressvisual.Config.load(path, lambda _message: None)
    assert reloaded.font_family == "Inter"
    assert reloaded.margin == 40


def test_save_appearance_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    config = pressvisual.Config.load(path, lambda _message: None)

    assert config.save_appearance({"inconnue": 1}) is True
    assert not path.exists()


def test_update_config_refuses_corrupted_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ cassé", encoding="utf-8")
    config = pressvisual.Config.load(path, lambda _message: None)

    assert config.remember_position("top-left") is False
    assert path.read_text(encoding="utf-8") == "{ cassé"


def test_update_config_writes_through_temporary_file(tmp_path):
    path = tmp_path / "config.json"
    config = pressvisual.Config.load(path, lambda _message: None)

    config.remember_position("bottom-center")

    assert json.loads(path.read_text(encoding="utf-8"))["position"] == "bottom-center"
    assert not (tmp_path / "config.json.tmp").exists()
