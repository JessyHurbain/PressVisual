"""Comportement de l'overlay : lignes, combinaisons, molette, apparence."""

from __future__ import annotations

import time

import pytest
from PyQt6.QtCore import QAbstractAnimation, QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QGuiApplication, QMouseEvent

import pressvisual
from pressvisual import KeyEvent, MouseEvent


def items(overlay) -> list[list[tuple[str, str]]]:
    return [list(row._items) for row in overlay._rows]


def last_items(overlay) -> list[tuple[str, str]]:
    assert overlay._rows, "aucune ligne affichée"
    return list(overlay._rows[-1]._items)


# ---------------------------------------------------------------------------
# Clavier
# ---------------------------------------------------------------------------


def test_plain_character_shows_one_key(overlay):
    overlay._on_key(KeyEvent(token="a", char="a"))

    assert items(overlay) == [[("a", "key")]]


def test_special_key_uses_french_label(overlay):
    overlay._on_key(KeyEvent(token="enter", char=None))

    assert items(overlay) == [[("Entrée", "key")]]


def test_combination_order_is_fixed(overlay):
    overlay._on_key(KeyEvent(token="c", char="c", mods=("shift", "ctrl")))

    assert items(overlay) == [
        [
            ("Ctrl", "mod"),
            ("+", "plus"),
            ("Maj", "mod"),
            ("+", "plus"),
            ("C", "key"),
        ]
    ]


def test_modifier_row_is_reused_then_updated(overlay):
    overlay._on_modifiers(("ctrl",))
    row = overlay._combo_row
    assert items(overlay) == [[("Ctrl", "mod")]]

    overlay._on_modifiers(("ctrl", "alt"))

    assert overlay._combo_row is row
    assert items(overlay) == [
        [("Ctrl", "mod"), ("+", "plus"), ("Alt", "mod")]
    ]


def test_shift_alone_does_not_open_a_row(overlay):
    overlay._on_modifiers(("shift",))

    assert items(overlay) == []


def test_key_replaces_modifier_row(overlay):
    overlay._on_modifiers(("ctrl",))

    overlay._on_key(KeyEvent(token="c", char=None, mods=("ctrl",)))

    assert len(overlay._rows) == 1
    assert items(overlay) == [
        [("Ctrl", "mod"), ("+", "plus"), ("C", "key")]
    ]
    assert overlay._combo_row is None


def test_max_rows_keeps_the_most_recent(overlay, config):
    config.max_rows = 2

    for char in "abcd":
        overlay._on_key(KeyEvent(token=char, char=char))

    assert items(overlay) == [[("c", "key")], [("d", "key")]]


def test_row_levels_fade_with_age(overlay, config):
    config.max_rows = 3
    for char in "abc":
        overlay._on_key(KeyEvent(token=char, char=char))

    assert [row._alpha for row in overlay._rows] == [0.34, 0.62, 1.0]


def test_capture_disabled_ignores_events(overlay):
    overlay.set_capture_enabled(False)

    overlay._on_key(KeyEvent(token="a", char="a"))
    overlay._on_modifiers(("ctrl",))
    overlay._on_mouse(MouseEvent(kind="click", button="left"))

    assert items(overlay) == []


def test_status_row(overlay):
    overlay._status("Capture activée")

    assert last_items(overlay) == [("Capture activée", "status")]


# ---------------------------------------------------------------------------
# Texte continu
# ---------------------------------------------------------------------------


def test_concat_text_groups_characters(overlay, config):
    config.concat_text = True

    for char in "abc":
        overlay._on_key(KeyEvent(token=char, char=char))

    assert items(overlay) == [[("abc", "text")]]
    assert overlay._combo_row is None


def test_finish_text_keeps_the_row(overlay, config):
    config.concat_text = True
    overlay._on_key(KeyEvent(token="a", char="a"))

    overlay._finish_text()

    assert items(overlay) == [[("a", "text")]]
    assert overlay._text_row is None
    assert overlay._text == ""


def test_backspace_edits_text(overlay, config):
    config.concat_text = True
    for char in "abc":
        overlay._on_key(KeyEvent(token=char, char=char))

    overlay._on_key(KeyEvent(token="backspace", char=None))

    assert items(overlay) == [[("ab", "text")]]
    assert overlay._text == "ab"


def test_backspace_on_single_character_removes_row(overlay, config):
    config.concat_text = True
    overlay._on_key(KeyEvent(token="a", char="a"))

    overlay._on_key(KeyEvent(token="backspace", char=None))

    assert items(overlay) == []
    assert overlay._text_row is None


def test_space_extends_current_word(overlay, config):
    config.concat_text = True
    overlay._on_key(KeyEvent(token="a", char="a"))

    overlay._on_key(KeyEvent(token="space", char=" "))
    overlay._on_key(KeyEvent(token="b", char="b"))

    assert items(overlay) == [[("a b", "text")]]


def test_space_at_start_shows_a_key(overlay, config):
    config.concat_text = True

    overlay._on_key(KeyEvent(token="space", char=" "))

    assert items(overlay) == [[("Espace", "key")]]


def test_masking_replaces_characters(overlay, config):
    config.concat_text = True
    overlay.toggle_masking()

    overlay._on_key(KeyEvent(token="x", char="x"))

    assert items(overlay)[-1] == [("•", "text")]
    assert overlay.masked is True


def test_long_text_is_truncated_from_the_start(overlay, config):
    config.concat_text = True
    text = "m" * 200

    fitted = overlay._fit_text(text)

    assert fitted.startswith("… ")
    assert len(fitted) < len(text)
    limit = max(140, config.max_width - 40)
    assert overlay._text_metrics.horizontalAdvance(fitted) <= limit


def test_short_text_is_untouched(overlay):
    assert overlay._fit_text("bonjour") == "bonjour"


# ---------------------------------------------------------------------------
# Souris
# ---------------------------------------------------------------------------


def test_click_with_control_shows_both_badges(overlay):
    overlay._on_click(MouseEvent(kind="click", button="middle", mods=("ctrl",)))

    assert items(overlay) == [
        [("Ctrl", "mod"), ("+", "plus"), ("Clic milieu", "mouse")]
    ]


@pytest.mark.parametrize(
    ("button", "label"),
    [
        ("left", "Clic gauche"),
        ("right", "Clic droit"),
        ("middle", "Clic milieu"),
        ("back", "Précédent"),
        ("forward", "Suivant"),
    ],
)
def test_click_labels(overlay, button, label):
    overlay._on_click(MouseEvent(kind="click", button=button))

    assert items(overlay) == [[(label, "mouse")]]


def test_side_click_with_control_shows_both_badges(overlay):
    overlay._on_click(MouseEvent(kind="click", button="back", mods=("ctrl",)))

    assert items(overlay) == [
        [("Ctrl", "mod"), ("+", "plus"), ("Précédent", "mouse")]
    ]


def test_side_button_labels_are_configurable(overlay, config):
    config.click_forward_label = "Bouton 5"

    overlay._on_click(MouseEvent(kind="click", button="forward"))

    assert items(overlay) == [[("Bouton 5", "mouse")]]


def test_side_click_is_never_a_double_click(overlay):
    overlay._on_click(MouseEvent(kind="click", button="back", count=2))

    assert items(overlay) == [[("Précédent", "mouse")]]


def test_scroll_is_aggregated(overlay):
    overlay._on_scroll(MouseEvent(kind="scroll", direction=1))
    overlay._on_scroll(MouseEvent(kind="scroll", direction=1))
    overlay._on_scroll(MouseEvent(kind="scroll", direction=1))

    assert items(overlay) == [[("Scroll ↑ ×3", "mouse")]]


def test_horizontal_scroll_has_its_own_labels(overlay):
    overlay._on_scroll(MouseEvent(kind="scroll", axis="horizontal", direction=1))
    overlay._on_scroll(MouseEvent(kind="scroll", axis="horizontal", direction=-1))

    assert items(overlay) == [
        [("Scroll →", "mouse")],
        [("Scroll ←", "mouse")],
    ]


def test_horizontal_scroll_is_aggregated_separately(overlay):
    overlay._on_scroll(MouseEvent(kind="scroll", axis="vertical", direction=1))
    overlay._on_scroll(MouseEvent(kind="scroll", axis="horizontal", direction=1))
    overlay._on_scroll(MouseEvent(kind="scroll", axis="horizontal", direction=1))

    assert items(overlay) == [
        [("Scroll ↑", "mouse")],
        [("Scroll → ×2", "mouse")],
    ]


def test_horizontal_scroll_carries_modifiers(overlay):
    overlay._on_scroll(
        MouseEvent(kind="scroll", axis="horizontal", direction=-1, mods=("shift",))
    )

    assert items(overlay) == [
        [("Maj", "mod"), ("+", "plus"), ("Scroll ←", "mouse")]
    ]


def test_scroll_direction_change_starts_new_row(overlay):
    overlay._on_scroll(MouseEvent(kind="scroll", direction=1))
    overlay._on_scroll(MouseEvent(kind="scroll", direction=-1))

    assert items(overlay) == [[("Scroll ↑", "mouse")], [("Scroll ↓", "mouse")]]


def test_scroll_modifiers_start_a_new_row(overlay):
    overlay._on_scroll(MouseEvent(kind="scroll", direction=1, mods=("ctrl",)))
    overlay._on_scroll(MouseEvent(kind="scroll", direction=1))

    assert items(overlay) == [
        [("Ctrl", "mod"), ("+", "plus"), ("Scroll ↑", "mouse")],
        [("Scroll ↑", "mouse")],
    ]


def test_double_click_updates_the_previous_row(overlay):
    overlay._on_click(MouseEvent(kind="click", button="left", count=1))
    overlay._on_click(MouseEvent(kind="click", button="left", count=2))

    assert items(overlay) == [[("Double clic", "mouse")]]


def test_late_double_click_starts_a_new_row(overlay):
    overlay._on_click(MouseEvent(kind="click", button="left", count=1))
    overlay._last_left_time = time.monotonic() - 5

    overlay._on_click(MouseEvent(kind="click", button="left", count=2))

    assert items(overlay) == [
        [("Clic gauche", "mouse")],
        [("Double clic", "mouse")],
    ]


def test_mouse_capture_disabled_ignores_events(overlay, config):
    config.capture_mouse = False

    overlay._on_mouse(MouseEvent(kind="click", button="left"))
    overlay._on_mouse(MouseEvent(kind="scroll", direction=1))

    assert items(overlay) == []


def test_scroll_closes_text_and_combo(overlay, config):
    config.concat_text = True
    overlay._on_key(KeyEvent(token="a", char="a"))
    overlay._on_modifiers(("ctrl",))

    overlay._on_scroll(MouseEvent(kind="scroll", direction=-1))

    labels = items(overlay)
    assert [("a", "text")] in labels
    assert labels[-1] == [("Scroll ↓", "mouse")]
    assert overlay._combo_row is None


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------


def test_position_preset_uses_margin(overlay, config):
    overlay.set_position("top-left", announce=False)

    available = QGuiApplication.primaryScreen().availableGeometry()
    assert overlay.position_name == "top-left"
    assert overlay.x() == available.left() + config.margin
    assert overlay.y() == available.top() + config.margin


def test_unknown_position_falls_back_to_configured_one(overlay):
    overlay.set_position("nope", announce=False)

    assert overlay.position_name == overlay._cfg.position


def test_snapping_after_drag_clears_preset(overlay):
    available = QGuiApplication.primaryScreen().availableGeometry()
    overlay.move(available.right() - overlay.width() - 2, available.top() + 2)

    overlay._snap_anchor_to_position()

    assert overlay.position_name == ""
    assert overlay._anchor_mode == "right"
    assert overlay._vertical_mode == "top"


def test_hidden_overlay_does_not_move_on_relayout(overlay):
    overlay.set_position("bottom-right", announce=False)
    before = overlay.pos()

    overlay._relayout()

    assert overlay.pos() == before


# ---------------------------------------------------------------------------
# Déplacement manuel
# ---------------------------------------------------------------------------


def _mouse(kind, overlay, global_pos, buttons=Qt.MouseButton.LeftButton):
    local = QPointF(global_pos - overlay.frameGeometry().topLeft())
    return QMouseEvent(
        kind,
        local,
        QPointF(global_pos),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def _drag(overlay, delta: QPoint) -> QPoint:
    """Simule un glisser complet depuis le centre de la bulle."""
    start = overlay.frameGeometry().center()
    end = start + delta
    overlay.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, overlay, start))
    overlay.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, overlay, end))
    overlay.mouseReleaseEvent(
        _mouse(QEvent.Type.MouseButtonRelease, overlay, end, Qt.MouseButton.NoButton)
    )
    return end


def test_press_suspends_the_hide_timer(overlay):
    overlay.show()
    overlay._on_key(KeyEvent(token="a", char="a"))
    assert overlay._idle_timer.isActive()

    start = overlay.frameGeometry().center()
    overlay.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, overlay, start))

    assert overlay._dragging is True
    assert not overlay._idle_timer.isActive()
    overlay.mouseReleaseEvent(
        _mouse(QEvent.Type.MouseButtonRelease, overlay, start, Qt.MouseButton.NoButton)
    )


def test_press_cancels_a_running_fade_out(overlay):
    overlay.show()
    overlay._fade_out()
    assert overlay._fade_target == "out"

    overlay.mousePressEvent(
        _mouse(QEvent.Type.MouseButtonPress, overlay, overlay.frameGeometry().center())
    )

    assert overlay._fade_target == "idle"
    assert overlay._fade.state() == QAbstractAnimation.State.Stopped
    assert overlay.isVisible()


def test_release_restarts_the_hide_timer(overlay):
    overlay.show()
    overlay._idle_timer.stop()

    end = _drag(overlay, QPoint(-120, -80))

    assert overlay._dragging is False
    assert overlay._idle_timer.isActive()
    assert overlay.isVisible()
    assert overlay.frameGeometry().center() != end, "la bulle doit avoir bougé"


def test_drag_outside_the_screen_is_clamped_back_inside(overlay):
    overlay.show()
    available = QGuiApplication.primaryScreen().availableGeometry()

    # Glisser très au-delà du coin haut-gauche de l'écran.
    _drag(overlay, QPoint(-available.left() - 400, -available.top() - 400))

    assert overlay.x() >= available.left()
    assert overlay.y() >= available.top()


# ---------------------------------------------------------------------------
# Apparence et peinture
# ---------------------------------------------------------------------------


def test_apply_appearance_updates_palette_and_fonts(overlay):
    overlay._on_key(KeyEvent(token="a", char="a"))

    overlay.apply_appearance(
        {
            "text_color": "#00ff00",
            "accent_color": "#ffe066",
            "font_size": 24,
            "margin": 12,
        }
    )

    assert overlay._cfg.text_color == "#00ff00"
    assert overlay._palette.text.name() == "#00ff00"
    assert overlay._palette.on_accent.name() == "#000000"
    assert overlay._badge_font.pointSize() == 23
    assert overlay._text_font.pointSize() == 24


def test_apply_appearance_clamps_out_of_range_values(overlay):
    overlay.apply_appearance({"font_size": 999, "opacity": 0.0})

    assert overlay._cfg.font_size == 40
    assert overlay._cfg.opacity == 0.15


def test_overlay_paints_without_error(qapp, overlay, config):
    config.concat_text = False
    overlay.show()
    overlay._on_key(KeyEvent(token="a", char="a"))
    overlay._on_modifiers(("ctrl",))
    overlay._on_click(MouseEvent(kind="click", button="middle", mods=("ctrl",)))
    overlay._status("Prêt")
    qapp.processEvents()

    pixmap = overlay.grab()

    assert not pixmap.isNull()
    assert pixmap.width() > 0
