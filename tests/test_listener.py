"""Fil de capture pynput : événements émis vers l'interface."""

from __future__ import annotations

import pytest
from pynput import keyboard, mouse

import pressvisual
from pressvisual_app import capture as capture_module


class Recorder:
    """Collecte les signaux émis par ``InputBridge``."""

    def __init__(self, qapp) -> None:  # noqa: ARG002 - QApplication requise
        self.bridge = pressvisual.InputBridge()
        self.keys: list[pressvisual.KeyEvent] = []
        self.mouse: list[pressvisual.MouseEvent] = []
        self.modifiers: list[tuple[str, ...]] = []
        self.modifier_sides: list[tuple[str, ...]] = []
        self.hotkeys: list[str] = []
        self.errors: list[str] = []
        self.releases: list[str] = []
        self.mouse_releases: list[str] = []
        self.bridge.key_event.connect(self.keys.append)
        self.bridge.key_release.connect(self.releases.append)
        self.bridge.mouse_event.connect(self.mouse.append)
        self.bridge.mouse_release.connect(self.mouse_releases.append)
        self.bridge.modifiers_changed.connect(self.modifiers.append)
        self.bridge.modifier_sides_changed.connect(self.modifier_sides.append)
        self.bridge.hotkey.connect(self.hotkeys.append)
        self.bridge.error.connect(self.errors.append)


def make_listener(recorder, config, hotkeys=None) -> pressvisual.InputListener:
    return pressvisual.InputListener(
        recorder.bridge, config, hotkeys or {}
    )


@pytest.fixture
def recorder(qapp):
    return Recorder(qapp)


# ---------------------------------------------------------------------------
# Clavier
# ---------------------------------------------------------------------------


def test_modifier_press_emits_sorted_modifiers(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.shift)
    listener._on_press(keyboard.Key.ctrl)

    assert recorder.modifiers == [("shift",), ("ctrl", "shift")]
    assert recorder.keys == []


def test_modifier_release_removes_it(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_release(keyboard.Key.ctrl)

    assert recorder.modifiers[-1] == ()


def test_modifier_press_reports_its_physical_side(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl_l)
    listener._on_press(keyboard.Key.shift_r)

    assert recorder.modifier_sides == [("ctrl_l",), ("ctrl_l", "shift_r")]
    assert recorder.modifiers == [("ctrl",), ("ctrl", "shift")]


def test_modifier_release_clears_its_side(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl_l)
    listener._on_release(keyboard.Key.ctrl_l)

    assert recorder.modifier_sides == [("ctrl_l",), ()]


def test_generic_modifier_counts_as_the_left_key(recorder, config):
    """Sous X11 et macOS, le jeton sans suffixe est la touche de gauche."""
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_release(keyboard.Key.ctrl)
    listener._on_press(keyboard.Key.ctrl_r)

    assert recorder.modifier_sides == [("ctrl_l",), (), ("ctrl_r",)]


def test_printable_key_carries_modifiers(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_press(keyboard.KeyCode.from_char("c"))

    assert recorder.keys == [
        pressvisual.KeyEvent(token="c", char="c", mods=("ctrl",))
    ]


def test_key_repeat_is_ignored_by_default(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.KeyCode.from_char("a"))
    listener._on_press(keyboard.KeyCode.from_char("a"))
    listener._on_release(keyboard.KeyCode.from_char("a"))
    listener._on_press(keyboard.KeyCode.from_char("a"))

    assert [event.repeat for event in recorder.keys] == [False, False]


def test_key_repeat_is_kept_when_enabled(recorder, config):
    config.ignore_key_repeats = False
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.KeyCode.from_char("a"))
    listener._on_press(keyboard.KeyCode.from_char("a"))

    assert [event.repeat for event in recorder.keys] == [False, True]


def test_filtered_keys_are_dropped(recorder, config):
    config.filtered_keys = ["a"]
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.KeyCode.from_char("a"))
    listener._on_press(keyboard.KeyCode.from_char("b"))

    assert [event.token for event in recorder.keys] == ["b"]


def test_keyboard_capture_disabled_emits_nothing(recorder, config):
    config.capture_keyboard = False
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_press(keyboard.KeyCode.from_char("a"))

    assert recorder.keys == []
    assert recorder.modifiers == []


def test_hotkey_is_reported_once(recorder, config):
    hotkeys = {pressvisual.parse_hotkey("ctrl+f12"): "toggle"}
    listener = make_listener(recorder, config, hotkeys)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_press(keyboard.Key.f12)
    listener._on_press(keyboard.Key.f12)  # répétition : pas de second signal

    assert recorder.hotkeys == ["toggle"]
    assert recorder.keys == []


def test_altgr_produces_text_without_modifiers(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_press(keyboard.Key.alt_gr)
    listener._on_press(keyboard.KeyCode.from_char("é"))

    assert recorder.keys == [
        pressvisual.KeyEvent(token="é", char="é", mods=())
    ]


def test_errors_are_reported_only_once(recorder, config):
    listener = make_listener(recorder, config)

    listener._report_error("premier")
    listener._report_error("second")

    assert recorder.errors == ["premier"]


# ---------------------------------------------------------------------------
# Souris
# ---------------------------------------------------------------------------


def test_click_carries_modifiers(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_click(120, 240, mouse.Button.middle, True)

    assert recorder.mouse == [
        pressvisual.MouseEvent(
            kind="click",
            button="middle",
            count=1,
            x=120,
            y=240,
            mods=("ctrl",),
        )
    ]


def test_release_emits_the_key_token(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.KeyCode.from_char("a"))
    listener._on_release(keyboard.KeyCode.from_char("a"))

    assert recorder.releases == ["a"]


def test_release_is_emitted_for_special_keys(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_release(keyboard.Key.enter)

    assert recorder.releases == ["enter"]


def test_modifier_release_does_not_emit_a_key_release(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.ctrl)
    listener._on_release(keyboard.Key.ctrl)

    assert recorder.releases == []


def test_unidentified_release_is_ignored(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_release(keyboard.KeyCode(vk=0))

    assert recorder.releases == []


def test_click_release_emits_the_button_without_a_click(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_click(10, 10, mouse.Button.left, False)

    assert recorder.mouse == []
    assert recorder.mouse_releases == ["left"]


def test_click_press_does_not_emit_a_release(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_click(10, 10, mouse.Button.right, True)

    assert len(recorder.mouse) == 1
    assert recorder.mouse_releases == []


def test_unknown_button_is_ignored(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_click(10, 10, mouse.Button.unknown, True)

    assert recorder.mouse == []


def _side_button(canonical: str):
    """Bouton pynput correspondant au bouton latéral demandé."""
    for button, name in pressvisual.MOUSE_BUTTON_NAMES.items():
        if name == canonical:
            return button
    pytest.skip(f"pynput n'expose pas {canonical} sur cette plateforme")


def test_side_button_names_use_windows_attributes(monkeypatch):
    class FakeButton:
        x1 = object()
        x2 = object()

    class FakeMouse:
        Button = FakeButton

    monkeypatch.setattr(capture_module, "mouse", FakeMouse)

    assert capture_module._side_button_names() == {
        FakeButton.x1: "back",
        FakeButton.x2: "forward",
    }


def test_side_button_names_use_x11_numbers(monkeypatch):
    class FakeButton:
        button8 = object()
        button9 = object()

    class FakeMouse:
        Button = FakeButton

    monkeypatch.setattr(capture_module, "mouse", FakeMouse)

    assert capture_module._side_button_names() == {
        FakeButton.button8: "back",
        FakeButton.button9: "forward",
    }


def test_side_button_names_empty_without_support(monkeypatch):
    class FakeButton:
        pass

    class FakeMouse:
        Button = FakeButton

    monkeypatch.setattr(capture_module, "mouse", FakeMouse)

    assert capture_module._side_button_names() == {}


def test_side_buttons_are_reported(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_click(10, 10, _side_button("back"), True)
    listener._on_click(10, 10, _side_button("forward"), True)

    assert [(event.kind, event.button) for event in recorder.mouse] == [
        ("click", "back"),
        ("click", "forward"),
    ]


def test_side_click_carries_modifiers(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.shift)
    listener._on_click(10, 10, _side_button("back"), True)

    assert recorder.mouse[0].mods == ("shift",)


def test_side_clicks_are_never_aggregated(recorder, config):
    listener = make_listener(recorder, config)
    button = _side_button("back")

    listener._on_click(10, 10, button, True)
    listener._on_click(11, 10, button, True)

    assert [event.count for event in recorder.mouse] == [1, 1]


def test_double_click_is_detected(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_click(10, 10, mouse.Button.left, True)
    listener._on_click(12, 11, mouse.Button.left, True)

    assert [event.count for event in recorder.mouse] == [1, 2]


def test_right_click_is_never_aggregated(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_click(10, 10, mouse.Button.right, True)
    listener._on_click(10, 10, mouse.Button.right, True)

    assert [event.count for event in recorder.mouse] == [1, 1]


def test_distant_clicks_are_not_a_double_click(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_click(10, 10, mouse.Button.left, True)
    listener._on_click(200, 200, mouse.Button.left, True)

    assert [event.count for event in recorder.mouse] == [1, 1]


def test_vertical_scroll_carries_modifiers(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_press(keyboard.Key.shift)
    listener._on_scroll(5, 5, 0, 1)
    listener._on_scroll(5, 5, 0, -2)

    assert [
        (event.kind, event.axis, event.direction) for event in recorder.mouse
    ] == [
        ("scroll", "vertical", 1),
        ("scroll", "vertical", -1),
    ]
    assert all(event.mods == ("shift",) for event in recorder.mouse)


def test_horizontal_scroll_is_supported(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_scroll(0, 0, -1, 0)
    listener._on_scroll(0, 0, 2, 0)

    assert [
        (event.kind, event.axis, event.direction) for event in recorder.mouse
    ] == [("scroll", "horizontal", -1), ("scroll", "horizontal", 1)]


def test_diagonal_scroll_uses_vertical_axis(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_scroll(0, 0, -1, 1)

    assert [
        (event.kind, event.axis, event.direction) for event in recorder.mouse
    ] == [("scroll", "vertical", 1)]


def test_empty_scroll_is_ignored(recorder, config):
    listener = make_listener(recorder, config)

    listener._on_scroll(0, 0, 0, 0)

    assert recorder.mouse == []


def test_mouse_capture_disabled_ignores_listeners(recorder, config):
    # Le fil ne démarre pas l'écouteur souris ; les rappels restent inertes
    # uniquement si l'interface les filtre, mais aucun signal parasite ne doit
    # être émis si pynput n'appelle pas les rappels.
    assert config.capture_mouse is True
    listener = make_listener(recorder, config)
    assert listener._mouse_listener is None


def test_stop_without_start_returns_immediately(recorder, config):
    listener = make_listener(recorder, config)

    listener.stop()  # ne doit ni lever ni bloquer

    assert listener.is_alive() is False
