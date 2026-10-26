"""Transitions de disparition de la bulle : fondu, glissement ou aucune."""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QAbstractAnimation, QSize

import pressvisual
from pressvisual_app.keymap import SLIDE_DIRECTIONS, ZOOM_SCALE, transition_geometry


def finish_entry(overlay, qapp) -> None:
    """Termine la transition d'apparition en cours, quelle qu'elle soit."""
    overlay._fade.setCurrentTime(overlay._fade.duration())
    overlay._slide.setCurrentTime(overlay._slide.duration())
    qapp.processEvents()


def shown_overlay(qapp, config):
    """Overlay clavier affiché, transition d'apparition terminée."""
    config.display_mode = "keyboard"
    config.validate()
    overlay = pressvisual.Overlay(config)
    overlay._bump()
    finish_entry(overlay, qapp)
    return overlay


def close_overlay(overlay, qapp) -> None:
    overlay._hide_now()
    overlay.deleteLater()
    qapp.processEvents()


def make_config(config, transition: str, duration: int = 300):
    config.transition = transition
    config.transition_out_ms = duration
    config.validate()
    return config


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_transition_defaults_to_fade():
    assert pressvisual.Config().transition == "fade"


def test_unknown_transition_falls_back_to_fade():
    config = pressvisual.Config(transition="tourbillon")

    assert config.validate()

    assert config.transition == "fade"


def test_transition_accepts_every_choice():
    for choice in pressvisual.TRANSITIONS:
        config = pressvisual.Config(transition=choice)
        assert config.validate() == []
        assert config.transition == choice


def test_every_transition_has_a_label():
    for choice in pressvisual.TRANSITIONS:
        assert choice in pressvisual.TRANSITION_LABELS
        assert pressvisual.TRANSITION_LABELS[choice]


# ---------------------------------------------------------------------------
# Géométrie commune à l'overlay et à l'aperçu
# ---------------------------------------------------------------------------


def test_geometry_starts_from_the_resting_bubble():
    """À progress = 0, aucune transition ne déplace, réduit ni estompe."""
    for choice in pressvisual.TRANSITIONS:
        dx, dy, scale, opacity = transition_geometry(choice, 200, 80, 0.0)
        assert (dx, dy) == pytest.approx((0.0, 0.0))
        assert scale == pytest.approx(1.0)
        assert opacity == pytest.approx(1.0)


def test_every_slide_transition_has_a_direction():
    for choice in pressvisual.TRANSITIONS:
        if choice != "slide" and not choice.startswith("slide-"):
            continue
        assert choice in SLIDE_DIRECTIONS


def test_geometry_slides_the_bubble_by_its_own_size():
    expected = {
        "slide": (0.0, 80.0),
        "slide-up": (0.0, -80.0),
        "slide-left": (-200.0, 0.0),
        "slide-right": (200.0, 0.0),
    }
    for choice, (dx, dy) in expected.items():
        got = transition_geometry(choice, 200, 80, 1.0)
        assert (got[0], got[1]) == pytest.approx((dx, dy))
        # Glisser ne change ni la taille ni l'opacité.
        assert got[2] == pytest.approx(1.0)
        assert got[3] == pytest.approx(1.0)


def test_geometry_fades_without_moving():
    dx, dy, scale, opacity = transition_geometry("fade", 200, 80, 0.25)
    assert (dx, dy) == pytest.approx((0.0, 0.0))
    assert scale == pytest.approx(1.0)
    assert opacity == pytest.approx(0.75)


def test_geometry_shrinks_and_fades_for_zoom():
    dx, dy, scale, opacity = transition_geometry("zoom", 200, 80, 0.5)
    assert (dx, dy) == pytest.approx((0.0, 0.0))
    assert scale == pytest.approx(1.0 + (ZOOM_SCALE - 1.0) * 0.5)
    assert opacity == pytest.approx(0.5)


def test_geometry_leaves_none_untouched():
    for progress in (0.0, 0.5, 1.0):
        dx, dy, scale, opacity = transition_geometry("none", 200, 80, progress)
        assert (dx, dy) == pytest.approx((0.0, 0.0))
        assert scale == pytest.approx(1.0)
        assert opacity == pytest.approx(1.0)


def test_slide_transition_settings_are_saved(tmp_path):
    path = tmp_path / "config.json"
    config = pressvisual.Config.load(path, lambda _message: None)

    assert config.save_appearance({"transition": "slide-left"})

    reloaded = pressvisual.Config.load(path, lambda _message: None)
    assert reloaded.transition == "slide-left"


def test_transition_settings_are_saved(tmp_path):
    path = tmp_path / "config.json"
    config = pressvisual.Config.load(path, lambda _message: None)
    config.transition = "slide"
    config.transition_out_ms = 750

    assert config.save_appearance({"transition": "slide", "transition_out_ms": 750})

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["transition"] == "slide"
    assert data["transition_out_ms"] == 750

    reloaded = pressvisual.Config.load(path, lambda _message: None)
    assert reloaded.transition == "slide"
    assert reloaded.transition_out_ms == 750


def test_duration_is_bounded():
    config = pressvisual.Config(transition_out_ms=9000)

    assert config.validate()

    assert config.transition_out_ms == 3000


# ---------------------------------------------------------------------------
# Fondu
# ---------------------------------------------------------------------------


def test_fade_animates_the_opacity(qapp, config):
    make_config(config, "fade", 400)
    overlay = shown_overlay(qapp, config)
    try:
        overlay._fade_out()

        assert overlay._fade.state() == QAbstractAnimation.State.Running
        overlay._fade.setCurrentTime(200)
        assert overlay.windowOpacity() < 0.9

        overlay._fade.setCurrentTime(400)
        qapp.processEvents()

        assert overlay.isVisible() is False
        assert overlay.windowOpacity() == pytest.approx(1.0)
    finally:
        close_overlay(overlay, qapp)


# ---------------------------------------------------------------------------
# Glissement
# ---------------------------------------------------------------------------


def test_slide_moves_the_overlay_down(qapp, config):
    make_config(config, "slide", 400)
    overlay = shown_overlay(qapp, config)
    try:
        start = overlay.pos()
        overlay._fade_out()

        assert overlay._slide.state() == QAbstractAnimation.State.Running
        overlay._slide.setCurrentTime(200)
        assert overlay.pos().y() > start.y()
        assert overlay.pos().x() == start.x()

        overlay._slide.setCurrentTime(400)
        qapp.processEvents()

        assert overlay.isVisible() is False

        # La bulle retrouve sa place au retour des frappes.
        overlay._bump()
        finish_entry(overlay, qapp)

        assert overlay.pos() == start
        assert overlay.isVisible() is True
    finally:
        close_overlay(overlay, qapp)


def test_slide_is_undone_when_input_returns(qapp, config):
    make_config(config, "slide", 400)
    overlay = shown_overlay(qapp, config)
    try:
        start = overlay.pos()
        overlay._fade_out()
        overlay._slide.setCurrentTime(300)
        moved = overlay.pos()

        overlay._bump()

        assert moved.y() > start.y()
        assert overlay.pos() == start
        assert overlay.isVisible() is True
    finally:
        close_overlay(overlay, qapp)


# ---------------------------------------------------------------------------
# Glissements dans les quatre directions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("transition", "axis", "sign"),
    [
        ("slide", "y", 1),
        ("slide-up", "y", -1),
        ("slide-left", "x", -1),
        ("slide-right", "x", 1),
    ],
)
def test_slide_uses_the_configured_direction(
    qapp, config, transition, axis, sign
):
    make_config(config, transition, 400)
    overlay = shown_overlay(qapp, config)
    try:
        start = overlay.pos()
        overlay._fade_out()

        assert overlay._slide.state() == QAbstractAnimation.State.Running
        overlay._slide.setCurrentTime(200)
        moved = overlay.pos()

        if axis == "y":
            assert (moved.y() - start.y()) * sign > 0
            assert moved.x() == start.x()
        else:
            assert (moved.x() - start.x()) * sign > 0
            assert moved.y() == start.y()

        overlay._slide.setCurrentTime(400)
        qapp.processEvents()

        assert overlay.isVisible() is False
        assert overlay.pos() == start
    finally:
        close_overlay(overlay, qapp)


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------


def test_zoom_shrinks_the_overlay(qapp, config):
    make_config(config, "zoom", 400)
    overlay = shown_overlay(qapp, config)
    try:
        start = overlay.pos()
        size = overlay.size()
        centre = overlay.geometry().center()
        overlay._fade_out()

        assert overlay._slide.state() == QAbstractAnimation.State.Running
        overlay._slide.setCurrentTime(200)

        assert overlay.width() < size.width()
        assert overlay.height() < size.height()
        assert 0.0 < overlay.windowOpacity() < 1.0
        # Le rétrécissement se fait autour du centre de la bulle.
        assert abs(overlay.geometry().center().x() - centre.x()) <= 1
        assert abs(overlay.geometry().center().y() - centre.y()) <= 1

        overlay._slide.setCurrentTime(400)
        qapp.processEvents()

        assert overlay.isVisible() is False
        assert overlay.size() == size
        assert overlay.pos() == start
        assert overlay.windowOpacity() == pytest.approx(1.0)
    finally:
        close_overlay(overlay, qapp)


def test_hold_visible_stops_a_zoom(qapp, config):
    make_config(config, "zoom", 400)
    overlay = shown_overlay(qapp, config)
    try:
        size = overlay.size()
        start = overlay.pos()
        overlay._fade_out()
        overlay._slide.setCurrentTime(200)
        assert overlay.width() < size.width()

        # Saisir la bulle pendant la transition la laisse intacte sous la main.
        overlay._hold_visible()

        assert overlay.isVisible() is True
        assert overlay.size() == QSize(size.width(), size.height())
        assert overlay.pos() == start
        assert overlay.windowOpacity() == pytest.approx(1.0)
        assert overlay._slide.state() != QAbstractAnimation.State.Running
    finally:
        close_overlay(overlay, qapp)


def test_zoom_keeps_the_full_size_for_the_next_show(qapp, config):
    make_config(config, "zoom", 300)
    overlay = shown_overlay(qapp, config)
    try:
        size = overlay.size()
        start = overlay.pos()
        overlay._fade_out()
        overlay._slide.setCurrentTime(300)
        qapp.processEvents()

        overlay._bump()
        finish_entry(overlay, qapp)

        assert overlay.isVisible() is True
        assert overlay.size() == QSize(size.width(), size.height())
        assert overlay.pos() == start
    finally:
        close_overlay(overlay, qapp)


# ---------------------------------------------------------------------------
# Apparition
# ---------------------------------------------------------------------------


def test_entry_replays_the_slide_from_the_same_side(qapp, config):
    make_config(config, "slide", 300)
    config.display_mode = "keyboard"
    config.validate()
    overlay = pressvisual.Overlay(config)
    try:
        overlay._bump()

        assert overlay._slide.state() == QAbstractAnimation.State.Running
        entry = overlay.pos()
        finish_entry(overlay, qapp)
        anchor = overlay.pos()

        # La bulle arrive par le bas : elle démarre sous sa place.
        assert entry.y() > anchor.y()
        assert entry.x() == anchor.x()
    finally:
        close_overlay(overlay, qapp)


def test_entry_grows_the_overlay_on_zoom(qapp, config):
    make_config(config, "zoom", 300)
    config.display_mode = "keyboard"
    config.validate()
    overlay = pressvisual.Overlay(config)
    try:
        overlay._bump()

        assert overlay._slide.state() == QAbstractAnimation.State.Running
        small = overlay.size()
        assert overlay.windowOpacity() < 0.5

        finish_entry(overlay, qapp)

        assert overlay.width() > small.width()
        assert overlay.height() > small.height()
        assert overlay.windowOpacity() == pytest.approx(1.0)
    finally:
        close_overlay(overlay, qapp)


def test_entry_animation_is_capped_by_the_exit_duration(qapp, config):
    make_config(config, "fade", 60)
    config.transition_in_ms = 400
    config.display_mode = "keyboard"
    config.validate()
    overlay = pressvisual.Overlay(config)
    try:
        assert overlay._entry_duration() == 60
    finally:
        close_overlay(overlay, qapp)


# ---------------------------------------------------------------------------
# Aucune transition
# ---------------------------------------------------------------------------


def test_no_transition_shows_at_once(qapp, config):
    make_config(config, "none", 400)
    overlay = shown_overlay(qapp, config)
    try:
        overlay._hide_now()
        overlay._bump()

        assert overlay.isVisible() is True
        assert overlay._fade.state() != QAbstractAnimation.State.Running
        assert overlay._slide.state() != QAbstractAnimation.State.Running
        assert overlay.windowOpacity() == pytest.approx(1.0)
    finally:
        close_overlay(overlay, qapp)


def test_no_transition_hides_at_once(qapp, config):
    make_config(config, "none", 400)
    overlay = shown_overlay(qapp, config)
    try:
        overlay._fade_out()

        assert overlay.isVisible() is False
        assert overlay._fade.state() != QAbstractAnimation.State.Running
        assert overlay._slide.state() != QAbstractAnimation.State.Running
    finally:
        close_overlay(overlay, qapp)


def test_zero_duration_hides_at_once(qapp, config):
    make_config(config, "fade", 0)
    overlay = shown_overlay(qapp, config)
    try:
        overlay._fade_out()

        assert overlay.isVisible() is False
    finally:
        close_overlay(overlay, qapp)


def test_overlay_still_reappears_after_each_transition(qapp, config):
    for transition in pressvisual.TRANSITIONS:
        make_config(config, transition, 200)
        overlay = shown_overlay(qapp, config)
        try:
            start = overlay.pos()
            overlay._fade_out()
            overlay._fade.setCurrentTime(200)
            overlay._slide.setCurrentTime(200)
            qapp.processEvents()
            assert overlay.isVisible() is False

            overlay._bump()
            finish_entry(overlay, qapp)

            assert overlay.isVisible() is True
            assert overlay.pos() == start
        finally:
            close_overlay(overlay, qapp)


# ---------------------------------------------------------------------------
# Fenêtre d'apparence
# ---------------------------------------------------------------------------


def test_dialog_exposes_the_transition_choices(qapp, config):
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    try:
        choices = [
            dialog.transition_combo.itemData(index)
            for index in range(dialog.transition_combo.count())
        ]

        assert choices == list(pressvisual.TRANSITIONS)
    finally:
        dialog.deleteLater()


def test_dialog_values_carry_the_transition(qapp, config):
    config.transition = "slide"
    config.transition_out_ms = 640
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    try:
        assert dialog.transition_combo.currentData() == "slide"
        assert dialog.transition_duration.value() == 640

        dialog.transition_combo.setCurrentIndex(
            dialog.transition_combo.findData("none")
        )
        dialog.transition_duration.setValue(120)

        values = dialog.values()
        assert values["transition"] == "none"
        assert values["transition_out_ms"] == 120
    finally:
        dialog.deleteLater()


def test_reset_restores_the_default_transition(qapp, config):
    config.transition = "none"
    config.transition_out_ms = 1500
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    try:
        dialog._reset()

        assert dialog.transition_combo.currentData() == "fade"
        assert dialog.transition_duration.value() == pressvisual.Config().transition_out_ms
    finally:
        dialog.deleteLater()
