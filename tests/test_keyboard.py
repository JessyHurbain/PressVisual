"""Clavier compact : dispositions, touches allumées et mode d'affichage."""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QFont

import pressvisual
from pressvisual import KeyEvent, MouseEvent

LAYOUTS = (pressvisual.AZERTY, pressvisual.QWERTY)
LAYOUT_IDS = ("azerty", "qwerty")


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("layout", LAYOUTS, ids=LAYOUT_IDS)
def test_rows_fill_the_same_width(layout):
    assert len(layout.rows) == 5
    assert layout.width == pytest.approx(15.0)
    for row in layout.rows:
        assert sum(key.width for key in row) == pytest.approx(layout.width)


@pytest.mark.parametrize("layout", LAYOUTS, ids=LAYOUT_IDS)
def test_no_token_is_claimed_by_two_keys(layout):
    seen: dict[str, str] = {}
    for key in layout.keys():
        for token in key.tokens:
            assert token not in seen, f"{token} sur {key.label} et {seen.get(token)}"
            seen[token] = key.label


@pytest.mark.parametrize("layout", LAYOUTS, ids=LAYOUT_IDS)
def test_rows_are_not_empty(layout):
    for row in layout.rows:
        assert len(row) >= 5


def test_unknown_layout_falls_back_to_azerty():
    assert pressvisual.layout_for("bépo").name == "azerty"
    assert pressvisual.layout_for("").name == "azerty"


def test_layout_name_is_case_insensitive():
    assert pressvisual.layout_for("QWERTY").name == "qwerty"
    assert pressvisual.layout_for(" Azerty ").name == "azerty"


@pytest.mark.parametrize("layout", LAYOUTS, ids=LAYOUT_IDS)
def test_letters_light_exactly_one_key(layout):
    for letter in "azerty":
        keys = layout.keys_for_token(letter)
        assert len(keys) == 1
        assert keys[0].label == letter.upper()


def test_accented_key_matches_its_two_glyphs():
    assert [key.label for key in pressvisual.AZERTY.keys_for_token("é")] == ["é"]
    assert [key.label for key in pressvisual.AZERTY.keys_for_token("2")] == ["é"]


def test_shifted_symbol_lights_the_same_key_as_the_digit():
    for layout in LAYOUTS:
        for key in layout.keys():
            if key.secondary:
                assert layout.keys_for_token(key.secondary) == (key,)


@pytest.mark.parametrize(
    ("token", "label"),
    [
        ("esc", "Échap"),
        ("tab", "Tab"),
        ("enter", "Entrée"),
        ("backspace", "Retour"),
        ("space", "Espace"),
        ("caps_lock", "Verr Maj"),
        ("left", "←"),
        ("up", "↑"),
        ("down", "↓"),
        ("right", "→"),
    ],
)
def test_special_tokens_have_their_key(token, label):
    for layout in LAYOUTS:
        assert [key.label for key in layout.keys_for_token(token)] == [label]


def test_unknown_token_lights_nothing():
    assert pressvisual.AZERTY.keys_for_token("inconnu") == ()


# ---------------------------------------------------------------------------
# Vue
# ---------------------------------------------------------------------------


def make_view(config, qapp):  # noqa: ARG001 - QApplication requise
    font = QFont(pressvisual._choose_font_family(config))
    font.setPointSize(max(9, config.font_size - 1))
    view = pressvisual.KeyboardView(
        config, font, pressvisual.Palette.from_config(config)
    )
    view.resize(view.sizeHint())
    return view


def test_view_has_a_positive_size(qapp, config):
    view = make_view(config, qapp)
    try:
        assert view.sizeHint().width() > 300
        assert view.sizeHint().height() > 100
    finally:
        view.deleteLater()


def test_bigger_font_gives_a_bigger_keyboard(qapp, config):
    small = make_view(config, qapp)
    config.font_size = 28
    big = make_view(config, qapp)
    try:
        assert big.sizeHint().width() > small.sizeHint().width()
        assert big.sizeHint().height() > small.sizeHint().height()
    finally:
        small.deleteLater()
        big.deleteLater()


def test_pressed_letter_lights_its_key(qapp, config):
    view = make_view(config, qapp)
    try:
        view.set_active(["a"])

        assert view.active_labels() == ["A"]
    finally:
        view.deleteLater()


def test_several_keys_can_be_lit_at_once(qapp, config):
    view = make_view(config, qapp)
    try:
        view.set_active(["c", "t", "r", "l"])

        assert sorted(view.active_labels()) == ["C", "L", "R", "T"]
    finally:
        view.deleteLater()


def test_held_modifiers_stay_lit(qapp, config):
    view = make_view(config, qapp)
    try:
        view.set_modifiers(["ctrl", "shift"])
        labels = view.active_labels()

        assert labels.count("Ctrl") == 2
        assert labels.count("Maj") == 2
    finally:
        view.deleteLater()


def test_modifier_labels_follow_the_configuration(qapp, config):
    config.ctrl_label = "Cmd"
    view = make_view(config, qapp)
    try:
        view.set_modifiers(["ctrl"])

        assert view.active_labels() == ["Cmd", "Cmd"]
    finally:
        view.deleteLater()


def test_masking_hides_character_keys(qapp, config):
    view = make_view(config, qapp)
    try:
        view.set_masked(True)
        view.set_active(["a"])

        assert view.active_labels() == []

        view.set_active(["enter"])

        assert view.active_labels() == ["Entrée"]
    finally:
        view.deleteLater()


def test_layout_change_updates_the_mapping(qapp, config):
    view = make_view(config, qapp)
    try:
        view.set_active(["1"])
        assert view.active_labels() == ["&"]

        config.keyboard_layout = "qwerty"
        view.set_config(config)
        view.set_active(["1"])

        assert view.layout.name == "qwerty"
        assert view.active_labels() == ["1"]
    finally:
        view.deleteLater()


def test_view_paints_with_and_without_highlights(qapp, config):
    view = make_view(config, qapp)
    try:
        assert not view.grab().isNull()

        view.set_active(["a", "enter"])
        view.set_modifiers(["shift"])

        assert not view.grab().isNull()
    finally:
        view.deleteLater()


def test_english_labels_are_translated(qapp, config):
    translator = pressvisual.install_translator(qapp, "en")
    assert translator is not None
    try:
        view = make_view(config, qapp)
        try:
            view.set_modifiers(["shift"])
            view.set_active(["enter"])

            labels = view.active_labels()

            assert sorted(labels) == ["Enter", "Shift", "Shift"]
        finally:
            view.deleteLater()
    finally:
        qapp.removeTranslator(translator)


# ---------------------------------------------------------------------------
# Mode d'affichage de l'overlay
# ---------------------------------------------------------------------------


def make_keyboard_overlay(qapp, config):  # noqa: ARG001 - QApplication requise
    config.display_mode = "keyboard"
    config.validate()
    return pressvisual.Overlay(config)


def test_keyboard_mode_hides_the_badges(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        assert overlay._mode == "keyboard"
        assert overlay._keyboard.isHidden() is False

        overlay._on_key(KeyEvent(token="a", char="a"))

        assert overlay._rows == []
        assert overlay._keyboard.active_labels() == ["A"]
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_keyboard_mode_turns_the_key_off_on_release(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_key(KeyEvent(token="a", char="a"))
        assert overlay._keyboard.active_labels() == ["A"]

        overlay._on_key_release("a")

        assert overlay._keyboard.active_labels() == []
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_releasing_one_key_keeps_the_others_lit(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_key(KeyEvent(token="a", char="a"))
        overlay._on_key(KeyEvent(token="b", char="b"))

        overlay._on_key_release("a")

        assert overlay._keyboard.active_labels() == ["B"]
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_a_release_without_press_is_harmless(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_key_release("z")

        assert overlay._keyboard.active_labels() == []
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_lit_keys_are_capped_without_losing_the_last_one(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        for letter in "abcdefghijklmnopqrstuvwxyz":
            overlay._on_key(KeyEvent(token=letter, char=letter))

        assert len(overlay._kb_active) <= pressvisual.KEYBOARD_MAX_LIT
        assert "z" in overlay._kb_active
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_keyboard_mode_shows_held_modifiers(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_modifiers(("ctrl",))
        overlay._on_key(KeyEvent(token="c", char="c", mods=("ctrl",)))

        labels = overlay._keyboard.active_labels()

        assert "C" in labels
        assert labels.count("Ctrl") == 2
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_keyboard_mode_shows_clicks_on_the_mouse(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay._on_mouse(MouseEvent(kind="click", button="left"))
        overlay._on_mouse(MouseEvent(kind="scroll", direction=1))

        assert overlay._rows == []
        assert overlay._keyboard.active_labels() == []
        assert overlay._mouse.active_buttons() == ["left"]
        assert overlay._mouse.scroll == ("vertical", 1)
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_keyboard_mode_respects_masking(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay.toggle_masking()
        overlay._on_key(KeyEvent(token="a", char="a"))

        assert overlay._keyboard.active_labels() == []

        overlay._on_key(KeyEvent(token="enter", char=None))

        assert overlay._keyboard.active_labels() == ["Entrée"]
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_switching_back_to_the_standard_overlay(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay.apply_appearance({"display_mode": "overlay"})

        assert overlay._mode == "overlay"
        assert overlay._keyboard.isHidden() is True

        overlay._on_key(KeyEvent(token="a", char="a"))

        assert [list(row._items) for row in overlay._rows] == [[("a", "key")]]
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_switching_to_the_keyboard_clears_the_badges(qapp, config):
    overlay = pressvisual.Overlay(config)
    try:
        overlay._on_key(KeyEvent(token="a", char="a"))
        assert overlay._rows

        overlay.apply_appearance({"display_mode": "keyboard"})

        assert overlay._mode == "keyboard"
        assert overlay._rows == []
        assert overlay._keyboard.isHidden() is False
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_keyboard_layout_change_applies_immediately(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay.apply_appearance({"keyboard_layout": "qwerty"})

        assert overlay._keyboard.layout.name == "qwerty"
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()


def test_overlay_paints_the_keyboard(qapp, config):
    overlay = make_keyboard_overlay(qapp, config)
    try:
        overlay.show()
        overlay._on_key(KeyEvent(token="a", char="a"))
        overlay._on_modifiers(("shift",))
        qapp.processEvents()

        pixmap = overlay.grab()

        assert not pixmap.isNull()
        assert pixmap.width() > 300
        assert pixmap.height() > 100
    finally:
        overlay._hide_now()
        overlay.deleteLater()
        qapp.processEvents()
