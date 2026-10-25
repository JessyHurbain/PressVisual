"""Palette de couleurs et fenêtre de personnalisation."""

from __future__ import annotations

import json

from PyQt6.QtGui import QColor, QFontDatabase
from PyQt6.QtWidgets import QApplication, QDialog

import pressvisual
from pressvisual_app import overlay as overlay_module


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def test_palette_derives_colors_from_config(config):
    palette = pressvisual.Palette.from_config(config)

    assert palette.text.name() == "#f6f7f9"
    assert palette.panel_top.name() == "#26282f"
    assert palette.panel_bottom.name() == "#0e0f12"
    assert palette.key_bg.name() == "#f5f6f8"
    # Les traits sont dérivés du texte avec une alpha réduite.
    assert palette.border.alpha() == 40
    assert palette.mod_bg.alpha() == 28


def test_palette_uses_black_text_on_light_accent(config):
    config.accent_color = "#ffe066"

    palette = pressvisual.Palette.from_config(config)

    assert palette.on_accent.name() == "#000000"


def test_palette_uses_white_text_on_dark_accent(config):
    config.accent_color = "#1b2b6b"

    palette = pressvisual.Palette.from_config(config)

    assert palette.on_accent.name() == "#ffffff"


def test_palette_update_mutates_in_place(config):
    palette = pressvisual.Palette.from_config(config)
    shared = palette
    config.text_color = "#00ff00"

    palette.update_from_config(config)

    assert shared is palette
    assert palette.text.name() == "#00ff00"


def test_palette_falls_back_on_invalid_color(config):
    config.accent_color = "n'importe quoi"

    palette = pressvisual.Palette.from_config(config)

    assert palette.accent.name() == pressvisual.Config.accent_color


# ---------------------------------------------------------------------------
# Fenêtre d'apparence
# ---------------------------------------------------------------------------


def make_dialog(qapp, config, family="DejaVu Sans"):
    dialog = pressvisual.AppearanceDialog(config, family)
    qapp.processEvents()
    return dialog


def test_dialog_values_reflect_controls(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.opacity_slider.setValue(50)
        dialog.font_size.setValue(24)
        dialog.corner_radius.setValue(4)
        dialog.margin.setValue(40)
        dialog.max_width.setValue(700)
        dialog.color_buttons["accent_color"].set_color(QColor("#ff8800"))

        values = dialog.values()

        assert values["opacity"] == 0.5
        assert values["font_size"] == 24
        assert values["corner_radius"] == 4
        assert values["margin"] == 40
        assert values["max_width"] == 700
        assert values["accent_color"] == "#ff8800"
        assert values["font_family"]
        assert dialog.opacity_label.text() == "50 %"
    finally:
        dialog.deleteLater()


def test_dialog_preview_does_not_touch_base_config(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.font_size.setValue(30)
        dialog.margin.setValue(60)

        preview = dialog._preview_config()

        assert preview.font_size == 30
        assert preview.margin == 60
        assert config.font_size == 16
        assert config.margin == 28
    finally:
        dialog.deleteLater()


def test_dialog_reset_restores_defaults(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.opacity_slider.setValue(40)
        dialog.font_size.setValue(34)
        dialog.corner_radius.setValue(2)
        dialog.margin.setValue(70)
        dialog.max_width.setValue(1200)
        dialog.color_buttons["text_color"].set_color(QColor("#ff0000"))

        dialog._reset()
        values = dialog.values()

        defaults = pressvisual.Config()
        assert values["opacity"] == defaults.opacity
        assert values["font_size"] == defaults.font_size
        assert values["corner_radius"] == defaults.corner_radius
        assert values["margin"] == defaults.margin
        assert values["max_width"] == defaults.max_width
        assert values["text_color"] == defaults.text_color
    finally:
        dialog.deleteLater()


def test_dialog_preview_paints_without_error(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.preview.resize(420, 160)
        dialog.preview.update_appearance(dialog._preview_config(), "DejaVu Sans")

        pixmap = dialog.preview.grab()

        assert not pixmap.isNull()
    finally:
        dialog.deleteLater()


def test_dialog_exposes_language_choice(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        combo = dialog.language_combo
        assert combo.count() == 3
        assert combo.currentData() == "auto"
        assert combo.findData("fr") >= 0
        assert combo.findData("en") >= 0
    finally:
        dialog.deleteLater()


def test_dialog_reflects_configured_language(qapp, config):
    config.language = "en"

    dialog = make_dialog(qapp, config)
    try:
        assert dialog.values()["language"] == "en"
    finally:
        dialog.deleteLater()


def test_dialog_reset_restores_automatic_language(qapp, config):
    config.language = "en"
    dialog = make_dialog(qapp, config)
    try:
        dialog._reset()

        assert dialog.values()["language"] == "auto"
    finally:
        dialog.deleteLater()


def test_edit_appearance_applies_language_and_saves_it(
    monkeypatch, qapp, overlay, config, tmp_path
):
    path = tmp_path / "config.json"
    config.path = path
    emitted: list[str] = []
    overlay.language_changed.connect(emitted.append)

    class FakeDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"language": "en", "opacity": 0.5}

    monkeypatch.setattr(overlay_module, "AppearanceDialog", FakeDialog)

    overlay.edit_appearance()

    assert emitted == ["en"]
    assert config.language == "en"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["language"] == "en"
    assert data["opacity"] == 0.5


def test_edit_appearance_keeps_language_silent_when_unchanged(
    monkeypatch, qapp, overlay, config
):
    emitted: list[str] = []
    overlay.language_changed.connect(emitted.append)

    class FakeDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"language": "auto"}

    monkeypatch.setattr(overlay_module, "AppearanceDialog", FakeDialog)

    overlay.edit_appearance()

    assert emitted == []


def test_color_button_ignores_invalid_colors(qapp):
    button = pressvisual.ColorButton(QColor("#123456"))
    try:
        button.set_color(QColor())
        assert button.color().name() == "#123456"

        button.set_color(QColor("#abcdef"))
        assert button.color().name() == "#abcdef"
    finally:
        button.deleteLater()


# ---------------------------------------------------------------------------
# Police
# ---------------------------------------------------------------------------


def test_choose_font_family_keeps_configured_family(config):
    config.font_family = "Ma Police Maison"

    assert pressvisual._choose_font_family(config) == "Ma Police Maison"


def test_choose_font_family_returns_available_default(config):
    family = pressvisual._choose_font_family(config)

    assert family
    assert family in QFontDatabase.families() or family == QApplication.font().family()
