"""Souris compacte affichée à côté du clavier complet."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QFont, QPainter, QPixmap, QRegion
from PyQt6.QtWidgets import QWidget

import pressvisual
from pressvisual import MouseEvent
from pressvisual_app import mouse as mouse_module


def make_view(qapp, config, height: float = 170.0):  # noqa: ARG001 - QApplication
    view = pressvisual.MouseView(pressvisual.Palette.from_config(config))
    view.set_height(height)
    return view


def make_keyboard_overlay(qapp, config):  # noqa: ARG001 - QApplication requise
    config.display_mode = "keyboard"
    config.validate()
    return pressvisual.Overlay(config)


def close_overlay(overlay, qapp) -> None:
    overlay._hide_now()
    overlay.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# Vue seule
# ---------------------------------------------------------------------------


def test_view_has_a_mouse_like_size(qapp, config):
    view = make_view(qapp, config)
    try:
        view.resize(view.sizeHint())

        assert view.height() == 170
        assert view.width() == round(170 * mouse_module.WIDTH_RATIO)
        assert 0.5 < view.width() / view.height() < 0.7
    finally:
        view.deleteLater()


def test_pressed_button_lights_up(qapp, config):
    view = make_view(qapp, config)
    try:
        view.set_buttons(["left"])

        assert view.active_buttons() == ["left"]
    finally:
        view.deleteLater()


def test_buttons_are_listed_in_mouse_order(qapp, config):
    view = make_view(qapp, config)
    try:
        view.set_buttons(["forward", "left", "middle"])

        assert view.active_buttons() == ["left", "middle", "forward"]
    finally:
        view.deleteLater()


def test_unknown_button_is_ignored(qapp, config):
    view = make_view(qapp, config)
    try:
        view.set_buttons(["wheel", "left"])

        assert view.active_buttons() == ["left"]
    finally:
        view.deleteLater()


def test_releasing_a_button_turns_it_off(qapp, config):
    view = make_view(qapp, config)
    try:
        view.set_buttons(["left", "right"])
        view.set_buttons(["right"])

        assert view.active_buttons() == ["right"]
    finally:
        view.deleteLater()


def test_scroll_direction_is_kept(qapp, config):
    view = make_view(qapp, config)
    try:
        view.set_scroll("vertical", -1)
        assert view.scroll == ("vertical", -1)

        view.set_scroll("horizontal", 1)
        assert view.scroll == ("horizontal", 1)

        view.clear_scroll()
        assert view.scroll is None
    finally:
        view.deleteLater()


def test_clear_turns_everything_off(qapp, config):
    view = make_view(qapp, config)
    try:
        view.set_buttons(["left", "back"])
        view.set_scroll("vertical", 1)

        view.clear()

        assert view.active_buttons() == []
        assert view.scroll is None
    finally:
        view.deleteLater()


def test_view_paints_with_and_without_highlights(qapp, config):
    view = make_view(qapp, config, height=200)
    try:
        view.resize(view.sizeHint())
        empty = view.grab().toImage()

        view.set_buttons(["left", "middle"])
        view.set_scroll("vertical", 1)
        lit = view.grab().toImage()

        assert not empty.isNull() and not lit.isNull()
        assert empty != lit
    finally:
        view.deleteLater()


# ---------------------------------------------------------------------------
# Designs
# ---------------------------------------------------------------------------


def test_mouse_style_defaults_to_classic(qapp, config):
    view = make_view(qapp, config)
    try:
        assert pressvisual.Config().mouse_style == "classic"
        assert view.style == "classic"
    finally:
        view.deleteLater()


def test_each_style_draws_differently(qapp, config):
    view = make_view(qapp, config, height=200)
    try:
        view.resize(view.sizeHint())
        classic = view.grab().toImage()

        view.set_style("outline")
        outline = view.grab().toImage()

        view.set_style("minimal")
        minimal = view.grab().toImage()

        assert view.style == "minimal"
        assert classic != outline
        assert outline != minimal
        assert classic != minimal
    finally:
        view.deleteLater()


def test_style_fills_are_distinct(qapp, config):
    """Fond plein, traits seuls, silhouette translucide : trois rendus."""
    font = QFont("DejaVu Sans")
    font.setPointSize(14)
    palette = pressvisual.Palette.from_config(config)
    alpha: dict[str, int] = {}

    for style in pressvisual.MOUSE_STYLES:
        view = pressvisual.InputView(
            pressvisual.Config(display_mode="keyboard", mouse_style=style),
            font,
            palette,
        )
        try:
            mouse = view.mouse
            mouse.resize(mouse.sizeHint())
            pixmap = QPixmap(mouse.size())
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            mouse.render(
                painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren
            )
            painter.end()
            point = pixmap.toImage().pixelColor(
                mouse.width() // 2, mouse.height() - 30
            )
            alpha[style] = point.alpha()
        finally:
            view.deleteLater()

    assert alpha["classic"] > 200
    assert alpha["outline"] == 0
    assert 0 < alpha["minimal"] < 100


def test_unknown_style_falls_back_to_classic(qapp, config):
    view = make_view(qapp, config)
    try:
        view.set_style("imaginaire")

        assert view.style == "classic"
    finally:
        view.deleteLater()


def test_style_survives_a_lit_button(qapp, config):
    view = make_view(qapp, config, height=200)
    try:
        view.set_buttons(["left"])
        view.set_style("outline")

        assert view.active_buttons() == ["left"]
        assert not view.grab().isNull()
    finally:
        view.deleteLater()


# ---------------------------------------------------------------------------
# Clavier et souris côte à côte
# ---------------------------------------------------------------------------


def test_mouse_sits_right_of_the_keyboard(qapp, config):
    font = QFont("DejaVu Sans")
    font.setPointSize(15)
    view = pressvisual.InputView(config, font, pressvisual.Palette.from_config(config))
    try:
        assert view.mouse.x() > view.keyboard.x() + view.keyboard.width() - 1
        assert view.mouse.height() == view.keyboard.sizeHint().height()
        assert view.width() == pytest.approx(
            view.keyboard.width() + view.GAP + view.mouse.width(), abs=2
        )
    finally:
        view.deleteLater()


def test_mouse_grows_with_the_font(qapp, config):
    small = QFont("DejaVu Sans")
    small.setPointSize(10)
    big = QFont("DejaVu Sans")
    big.setPointSize(24)
    palette = pressvisual.Palette.from_config(config)
    narrow = pressvisual.InputView(config, small, palette)
    wide = pressvisual.InputView(config, big, palette)
    try:
        assert wide.mouse.height() > narrow.mouse.height()
        assert wide.mouse.width() > narrow.mouse.width()
        assert wide.mouse.height() == wide.keyboard.sizeHint().height()
    finally:
        narrow.deleteLater()
        wide.deleteLater()


def test_mouse_is_hidden_when_clicks_are_not_captured(qapp, config):
    font = QFont("DejaVu Sans")
    view = pressvisual.InputView(config, font, pressvisual.Palette.from_config(config))
    try:
        assert view.mouse.isHidden() is False

        config.capture_mouse = False
        view.set_config(config)

        assert view.mouse.isHidden() is True
        assert view.keyboard.isHidden() is False
    finally:
        view.deleteLater()


def test_mouse_can_be_hidden_by_the_setting(qapp, config):
    font = QFont("DejaVu Sans")
    config.show_mouse = False
    view = pressvisual.InputView(config, font, pressvisual.Palette.from_config(config))
    try:
        assert view.mouse.isHidden() is True
        assert view.keyboard.isHidden() is False

        config.show_mouse = True
        view.set_config(config)

        assert view.mouse.isHidden() is False
    finally:
        view.deleteLater()


def test_switching_to_badges_hides_both_views(qapp, config):
    font = QFont("DejaVu Sans")
    view = pressvisual.InputView(config, font, pressvisual.Palette.from_config(config))
    try:
        view.set_mode_visible(False)

        assert view.isHidden() is True
        assert view.mouse.isHidden() is True
        assert view.keyboard.isHidden() is True

        view.set_mode_visible(True)

        assert view.mouse.isHidden() is False
        assert view.keyboard.isHidden() is False
    finally:
        view.deleteLater()


# ---------------------------------------------------------------------------
# Overlay en mode clavier
# ---------------------------------------------------------------------------


def test_click_lights_the_mouse_without_a_badge(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="left"))

        assert overlay._mouse.active_buttons() == ["left"]
        assert overlay._rows == []
    finally:
        close_overlay(overlay, qapp)


def test_mouse_release_turns_the_button_off(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="right"))
        assert overlay._mouse.active_buttons() == ["right"]

        overlay._on_mouse_release("right")

        assert overlay._mouse.active_buttons() == []
    finally:
        close_overlay(overlay, qapp)


def test_side_button_lights_the_same_way(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="back"))

        assert overlay._mouse.active_buttons() == ["back"]
    finally:
        close_overlay(overlay, qapp)


def test_held_mouse_buttons_stay_lit_together(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="left"))
        overlay._on_mouse(MouseEvent(kind="click", button="middle"))

        assert overlay._mouse.active_buttons() == ["left", "middle"]
    finally:
        close_overlay(overlay, qapp)


def test_scroll_shows_its_direction_then_fades(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="scroll", direction=-1))

        assert overlay._mouse.scroll == ("vertical", -1)
        assert overlay._mouse_scroll_timer.isActive()
        assert overlay._mouse_scroll_timer.interval() == (
            pressvisual.MOUSE_SCROLL_FLASH_MS
        )

        overlay._end_mouse_scroll()

        assert overlay._mouse.scroll is None
    finally:
        close_overlay(overlay, qapp)


def test_horizontal_scroll_uses_its_own_axis(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="scroll", axis="horizontal", direction=1))

        assert overlay._mouse.scroll == ("horizontal", 1)
    finally:
        close_overlay(overlay, qapp)


def test_scroll_ending_twice_is_harmless(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._end_mouse_scroll()

        assert overlay._mouse.scroll is None
    finally:
        close_overlay(overlay, qapp)


def test_mouse_release_in_overlay_mode_is_harmless(qapp, config):
    overlay = pressvisual.Overlay(config)
    try:
        overlay._on_mouse_release("left")

        assert overlay._mouse.active_buttons() == []
    finally:
        close_overlay(overlay, qapp)


def test_badges_mode_still_shows_clicks(qapp, config):
    overlay = pressvisual.Overlay(config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="left"))

        assert overlay._mouse.active_buttons() == []
        assert [list(row._items) for row in overlay._rows] == [
            [("Clic gauche", "mouse")]
        ]
    finally:
        close_overlay(overlay, qapp)


def test_switching_modes_clears_the_mouse(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="left"))
        overlay._on_mouse(MouseEvent(kind="scroll", direction=1))

        overlay.apply_appearance({"display_mode": "overlay"})

        assert overlay._mouse.active_buttons() == []
        assert overlay._mouse.scroll is None
        assert overlay._mouse.isHidden() is True

        overlay.apply_appearance({"display_mode": "keyboard"})

        assert overlay._mouse.isHidden() is False
    finally:
        close_overlay(overlay, qapp)


def test_hidden_mouse_stays_hidden_after_a_mode_change(qapp, config):
    config.show_mouse = False
    overlay = make_keyboard_overlay(qapp, config)
    try:
        assert overlay._mouse.isHidden() is True

        overlay.apply_appearance({"display_mode": "overlay"})
        overlay.apply_appearance({"display_mode": "keyboard"})

        assert overlay._mouse.isHidden() is True

        overlay.apply_appearance({"show_mouse": True})

        assert overlay._mouse.isHidden() is False
    finally:
        close_overlay(overlay, qapp)


def test_masking_keeps_the_mouse_visible(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay.toggle_masking()
        overlay._on_mouse(MouseEvent(kind="click", button="left"))

        assert overlay._mouse.active_buttons() == ["left"]
    finally:
        close_overlay(overlay, qapp)


def test_keyboard_mode_paints_the_mouse(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="left"))
        overlay._on_key(pressvisual.KeyEvent(token="a", char="a"))
        overlay._relayout()
        overlay.show()
        qapp.processEvents()

        image = overlay._mouse.grab().toImage()

        assert not image.isNull()
        assert image.width() == overlay._mouse.width()
    finally:
        close_overlay(overlay, qapp)


# ---------------------------------------------------------------------------
# Fenêtre d'apparence
# ---------------------------------------------------------------------------


def test_preview_follows_the_mouse_style(qapp, config):
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    qapp.processEvents()
    try:
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))
        assert dialog.preview._mouse.style == "classic"

        dialog.mouse_style_combo.setCurrentIndex(
            dialog.mouse_style_combo.findData("minimal")
        )

        assert dialog.values()["mouse_style"] == "minimal"
        assert dialog.preview._mouse.style == "minimal"
    finally:
        dialog.deleteLater()


def test_preview_hides_the_mouse_when_unchecked(qapp, config):
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    qapp.processEvents()
    try:
        assert dialog.show_mouse.isChecked() is True
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))
        assert dialog.preview._mouse.isHidden() is False

        dialog.show_mouse.setChecked(False)

        assert dialog.values()["show_mouse"] is False
        assert dialog.preview._mouse.isHidden() is True
        assert dialog.preview._keyboard.isHidden() is False
    finally:
        dialog.deleteLater()


def test_preview_shows_the_mouse_with_the_keyboard(qapp, config):
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    qapp.processEvents()
    try:
        assert dialog.preview._mouse.isHidden() is True

        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))

        assert dialog.preview._mouse.isHidden() is False
        assert dialog.preview._keyboard.isHidden() is False

        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("overlay"))

        assert dialog.preview._mouse.isHidden() is True
    finally:
        dialog.deleteLater()
