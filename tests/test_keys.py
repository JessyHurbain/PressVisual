"""Classification des touches pynput et conversions de configuration."""

from __future__ import annotations

import sys

import pytest
from pynput import keyboard

import pressvisual


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        (keyboard.Key.ctrl, ("ctrl", None, True)),
        (keyboard.Key.ctrl_l, ("ctrl", None, True)),
        (keyboard.Key.ctrl_r, ("ctrl", None, True)),
        (keyboard.Key.alt_l, ("alt", None, True)),
        (keyboard.Key.shift, ("shift", None, True)),
        (keyboard.Key.cmd, ("win", None, True)),
        (keyboard.Key.space, ("space", None, False)),
        (keyboard.Key.f12, ("f12", None, False)),
        (keyboard.Key.alt_gr, (None, None, False)),
    ],
)
def test_classify_special_keys(key, expected):
    assert pressvisual._classify_key(key) == expected


def test_classify_prints_lowercase_token_and_raw_char():
    token, char, modifier = pressvisual._classify_key(
        keyboard.KeyCode.from_char("A")
    )

    assert (token, char, modifier) == ("a", "A", False)


def test_classify_accented_char():
    token, char, modifier = pressvisual._classify_key(
        keyboard.KeyCode.from_char("é")
    )

    assert (token, char, modifier) == ("é", "é", False)


def test_classify_letter_without_char_uses_virtual_key():
    token, char, modifier = pressvisual._classify_key(keyboard.KeyCode(vk=67))

    assert (token, char, modifier) == ("c", "C", False)


def test_classify_digit_without_char_uses_virtual_key():
    assert pressvisual._classify_key(keyboard.KeyCode(vk=57)) == ("9", "9", False)


def test_classify_numpad_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    assert pressvisual._classify_key(keyboard.KeyCode(vk=96)) == ("0", "0", False)
    assert pressvisual._classify_key(keyboard.KeyCode(vk=110)) == (".", ".", False)


def test_classify_numpad_ignored_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    # Hors Windows, un pavé numérique sans caractère n'est pas devinable.
    assert pressvisual._classify_key(keyboard.KeyCode(vk=96)) == (None, None, False)


def test_classify_unknown_object():
    assert pressvisual._classify_key(object()) == (None, None, False)


def test_is_altgr():
    assert pressvisual._is_altgr(keyboard.Key.alt_gr) is True
    assert pressvisual._is_altgr(keyboard.Key.ctrl) is False
    assert pressvisual._is_altgr(keyboard.KeyCode.from_char("a")) is False


@pytest.mark.parametrize(
    ("value", "default", "expected"),
    [
        (True, False, True),
        (False, True, False),
        ("oui", False, True),
        (" NON ", True, False),
        ("1", False, True),
        ("off", True, False),
        (0, True, False),
        (2, False, True),
        (None, True, True),
        (object(), False, False),
    ],
)
def test_as_bool(value, default, expected):
    assert pressvisual._as_bool(value, default) is expected
