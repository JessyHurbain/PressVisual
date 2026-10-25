"""Poignée de redimensionnement : taille du clavier réglée à la souris."""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QFont, QMouseEvent
from PyQt6.QtWidgets import QApplication

import pressvisual


def make_keyboard_overlay(qapp, config):  # noqa: ARG001 - QApplication requise
    config.display_mode = "keyboard"
    config.validate()
    overlay = pressvisual.Overlay(config)
    overlay._relayout()
    return overlay


def close_overlay(overlay, qapp) -> None:
    overlay._hide_now()
    overlay.deleteLater()
    qapp.processEvents()


def send_press(overlay, local: QPoint) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(local),
        QPointF(overlay.mapToGlobal(local)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(overlay, event)


def send_move(overlay, local: QPoint) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(local),
        QPointF(overlay.mapToGlobal(local)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(overlay, event)


def send_release(overlay, local: QPoint) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(local),
        QPointF(overlay.mapToGlobal(local)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(overlay, event)


def grip_center(overlay) -> QPoint:
    return overlay._grip_rect().center()


def drag_grip(overlay, dx: int, dy: int = 0) -> None:
    """Appuie sur la poignée, la déplace de ``dx``/``dy`` et la relâche."""
    start = grip_center(overlay)
    send_press(overlay, start)
    send_move(overlay, start + QPoint(dx, dy))
    send_release(overlay, start + QPoint(dx, dy))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_scale_is_one_by_default():
    assert pressvisual.Config().keyboard_scale == 1.0


def test_scale_is_clamped_to_its_bounds():
    too_big = pressvisual.Config(keyboard_scale=5.0)
    too_small = pressvisual.Config(keyboard_scale=0.1)

    assert too_big.validate()
    assert too_small.validate()

    assert too_big.keyboard_scale == pressvisual.KEYBOARD_SCALE_MAX
    assert too_small.keyboard_scale == pressvisual.KEYBOARD_SCALE_MIN


def test_invalid_scale_falls_back_to_the_default():
    config = pressvisual.Config(keyboard_scale="grand")

    assert config.validate()

    assert config.keyboard_scale == 1.0


def test_scale_is_remembered_in_the_config_file(tmp_path):
    path = tmp_path / "config.json"
    config = pressvisual.Config.load(path, lambda _message: None)

    assert config.remember_keyboard_scale(1.25)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["keyboard_scale"] == 1.25

    reloaded = pressvisual.Config.load(path, lambda _message: None)
    assert reloaded.keyboard_scale == 1.25


# ---------------------------------------------------------------------------
# Vue
# ---------------------------------------------------------------------------


def test_scale_grows_the_keyboard(qapp, config):
    font = QFont("DejaVu Sans")
    font.setPointSize(14)
    view = pressvisual.KeyboardView(
        config, font, pressvisual.Palette.from_config(config)
    )
    try:
        base = view.sizeHint()

        view.set_scale(1.5)

        assert view.scale == 1.5
        assert view.sizeHint().width() > base.width()
        assert view.sizeHint().height() > base.height()
    finally:
        view.deleteLater()


def test_scale_shrinks_the_keyboard_and_its_mouse(qapp, config):
    font = QFont("DejaVu Sans")
    font.setPointSize(14)
    palette = pressvisual.Palette.from_config(config)
    view = pressvisual.InputView(config, font, palette)
    try:
        wide = view.sizeHint()

        view.set_scale(0.7)

        assert view.sizeHint().width() < wide.width()
        assert view.mouse.height() == view.keyboard.sizeHint().height()
        assert view.mouse.width() < round(wide.height() * 0.58)
    finally:
        view.deleteLater()


def test_view_starts_at_the_configured_scale(qapp, config):
    config.keyboard_scale = 1.4
    config.validate()
    font = QFont("DejaVu Sans")
    font.setPointSize(14)

    view = pressvisual.InputView(config, font, pressvisual.Palette.from_config(config))

    try:
        plain = pressvisual.InputView(
            pressvisual.Config(), font, pressvisual.Palette.from_config(config)
        )
        try:
            assert view.sizeHint().width() > plain.sizeHint().width()
        finally:
            plain.deleteLater()
    finally:
        view.deleteLater()


def test_scale_is_bounded_in_the_view(qapp, config):
    font = QFont("DejaVu Sans")
    view = pressvisual.KeyboardView(
        config, font, pressvisual.Palette.from_config(config)
    )
    try:
        view.set_scale(9.0)
        assert view.scale == pressvisual.KEYBOARD_SCALE_MAX

        view.set_scale(0.01)
        assert view.scale == pressvisual.KEYBOARD_SCALE_MIN
    finally:
        view.deleteLater()


# ---------------------------------------------------------------------------
# Poignée sur la bulle
# ---------------------------------------------------------------------------


def test_grip_zone_sits_in_the_bottom_right_corner(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        grip = overlay._grip_rect()

        assert grip.right() == overlay.width() - 1
        assert grip.bottom() == overlay.height() - 1
        assert grip.width() == pressvisual.RESIZE_GRIP_SIZE
    finally:
        close_overlay(overlay, qapp)


def test_pressing_the_grip_starts_a_resize(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        send_press(overlay, grip_center(overlay))

        assert overlay._resizing is True
        assert overlay._dragging is False
    finally:
        close_overlay(overlay, qapp)


def test_pressing_elsewhere_still_moves_the_bubble(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        send_press(overlay, QPoint(6, 6))

        assert overlay._dragging is True
        assert overlay._resizing is False
    finally:
        close_overlay(overlay, qapp)


def test_dragging_the_grip_left_shrinks_the_keyboard(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        wide = overlay.width()
        tall = overlay._keyboard.sizeHint().height()

        drag_grip(overlay, -80)

        assert overlay._cfg.keyboard_scale < 1.0
        assert overlay._keyboard.sizeHint().height() < tall
        assert overlay.width() < wide
        assert overlay._resizing is False
    finally:
        close_overlay(overlay, qapp)


def test_dragging_the_grip_right_grows_the_keyboard(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        narrow = overlay.width()

        drag_grip(overlay, 60)

        assert overlay._cfg.keyboard_scale > 1.0
        assert overlay.width() > narrow
    finally:
        close_overlay(overlay, qapp)


def test_vertical_drag_also_resizes(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        before = overlay._cfg.keyboard_scale

        drag_grip(overlay, 0, -70)

        assert overlay._cfg.keyboard_scale < before
    finally:
        close_overlay(overlay, qapp)


def test_scale_never_goes_below_the_minimum(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        drag_grip(overlay, -4000)

        assert overlay._cfg.keyboard_scale == pressvisual.KEYBOARD_SCALE_MIN
    finally:
        close_overlay(overlay, qapp)


def test_scale_never_goes_above_the_maximum(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        drag_grip(overlay, 4000)

        assert overlay._cfg.keyboard_scale == pressvisual.KEYBOARD_SCALE_MAX
    finally:
        close_overlay(overlay, qapp)


def test_resize_is_saved_for_the_next_start(tmp_path, qapp):
    path = tmp_path / "config.json"
    config = pressvisual.Config.load(path, lambda _message: None)
    overlay = make_keyboard_overlay(qapp, config)
    try:
        drag_grip(overlay, -70)
        stored = overlay._cfg.keyboard_scale
    finally:
        close_overlay(overlay, qapp)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["keyboard_scale"] == pytest.approx(stored)
    assert stored < 1.0


def test_badges_mode_has_no_grip(qapp, config):
    overlay = pressvisual.Overlay(config)
    try:
        send_press(overlay, QPoint(overlay.width() - 8, overlay.height() - 8))

        assert overlay._resizing is False
        assert overlay._dragging is True
    finally:
        close_overlay(overlay, qapp)
