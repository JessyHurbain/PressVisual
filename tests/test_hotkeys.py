"""Raccourcis globaux, libellés et décision « combinaison ou texte »."""

from __future__ import annotations

import pytest

import pressvisual

# ---------------------------------------------------------------------------
# parse_hotkey
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("ctrl+f12", (frozenset({"ctrl"}), "f12")),
        ("Ctrl + Shift + F11", (frozenset({"ctrl", "shift"}), "f11")),
        ("maj+alt+a", (frozenset({"shift", "alt"}), "a")),
        ("control+cmd+space", (frozenset({"ctrl", "win"}), "space")),
        ("super+x", (frozenset({"win"}), "x")),
        ("meta+option+x", (frozenset({"win", "alt"}), "x")),
        ("F9", (frozenset(), "f9")),
    ],
)
def test_parse_hotkey_valid(spec, expected):
    assert pressvisual.parse_hotkey(spec) == expected


@pytest.mark.parametrize(
    "spec",
    ["", "   ", "ctrl+", "+f12", "ctrl+a+b", "ctrl+shift", "ctrl++f12"],
)
def test_parse_hotkey_rejects_invalid_specs(spec):
    assert pressvisual.parse_hotkey(spec) is None


def test_parse_hotkey_is_case_insensitive():
    upper = pressvisual.parse_hotkey("CTRL+F12")
    lower = pressvisual.parse_hotkey("ctrl+f12")

    assert upper == lower == (frozenset({"ctrl"}), "f12")


# ---------------------------------------------------------------------------
# Libellés
# ---------------------------------------------------------------------------


def test_modifier_label_uses_configured_text(config):
    assert pressvisual.modifier_label(config, "ctrl") == "Ctrl"
    assert pressvisual.modifier_label(config, "shift") == "Maj"

    config.ctrl_label = "Ctl"
    assert pressvisual.modifier_label(config, "ctrl") == "Ctl"


def test_modifier_label_falls_back_for_unknown_modifier(config):
    assert pressvisual.modifier_label(config, "hyper") == "Hyper"


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("space", "Espace"),
        ("enter", "Entrée"),
        ("page_down", "Page ↓"),
        ("f12", "F12"),
        ("a", "A"),
        ("echap", "Echap"),
        ("ctrl", "Ctrl"),
    ],
)
def test_key_label(config, token, expected):
    assert pressvisual.key_label(config, token) == expected


def test_describe_hotkey_orders_modifiers(config):
    assert pressvisual.describe_hotkey(config, "shift+ctrl+f12") == "Ctrl + Maj + F12"
    assert pressvisual.describe_hotkey(config, "win+alt+x") == "Alt + Win + X"
    assert pressvisual.describe_hotkey(config, "space") == "Espace"


@pytest.mark.parametrize("spec", ["", "ctrl+", "invalide+raccourci+x"])
def test_describe_hotkey_empty_for_invalid_specs(config, spec):
    assert pressvisual.describe_hotkey(config, spec) == ""


# ---------------------------------------------------------------------------
# should_use_combo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mods", "char", "expected"),
    [
        ((), None, False),
        (("shift",), None, False),
        (("ctrl",), None, True),
        (("alt",), None, True),
        (("ctrl",), "a", True),
        (("alt",), "a", True),
        (("ctrl",), "é", False),
        (("alt",), "é", False),
        (("shift",), "É", False),
        (("win",), "é", True),
        (("win", "ctrl"), "a", True),
    ],
)
def test_should_use_combo(mods, char, expected):
    assert pressvisual.should_use_combo(mods, char) is expected
