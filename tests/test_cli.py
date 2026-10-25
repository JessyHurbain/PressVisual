"""Interface en ligne de commande."""

from __future__ import annotations

import pytest

import pressvisual
from pressvisual_app import cli as cli_module


def test_defaults_are_all_optional():
    args = pressvisual.build_arg_parser().parse_args([])

    for name in (
        "config",
        "duration",
        "opacity",
        "font_size",
        "max_rows",
        "max_width",
        "margin",
        "position",
        "toggle_hotkey",
    ):
        assert getattr(args, name) is None
    for name in (
        "no_keyboard",
        "no_mouse",
        "group_text",
        "start_hidden",
        "click_through",
    ):
        assert getattr(args, name) is False


def test_values_are_parsed():
    args = pressvisual.build_arg_parser().parse_args(
        [
            "--config",
            "perso.json",
            "--duration",
            "3.5",
            "--opacity",
            "0.7",
            "--font-size",
            "22",
            "--max-rows",
            "6",
            "--max-width",
            "800",
            "--margin",
            "12",
            "--position",
            "top-left",
            "--toggle-hotkey",
            "ctrl+f8",
            "--group-text",
            "--no-mouse",
            "--no-keyboard",
            "--start-hidden",
            "--click-through",
        ]
    )

    assert args.config == "perso.json"
    assert args.duration == 3.5
    assert args.opacity == 0.7
    assert args.font_size == 22
    assert args.max_rows == 6
    assert args.max_width == 800
    assert args.margin == 12
    assert args.position == "top-left"
    assert args.toggle_hotkey == "ctrl+f8"
    assert args.group_text is True
    assert args.no_mouse is True
    assert args.no_keyboard is True
    assert args.start_hidden is True
    assert args.click_through is True


def _args(*argv):
    return pressvisual.build_arg_parser().parse_args(list(argv))


def test_apply_arguments_copies_the_main_options():
    config = pressvisual.Config()

    pressvisual.apply_arguments(
        config, _args("--duration", "3", "--no-mouse", "--lang", "en")
    )

    assert config.display_duration == 3.0
    assert config.capture_mouse is False
    assert config.language == "en"


def test_position_option_clears_the_saved_free_position():
    config = pressvisual.Config(free_position=(120, 80))

    pressvisual.apply_arguments(config, _args("--position", "top-left"))

    assert config.position == "top-left"
    assert config.free_position is None


def test_free_position_is_kept_without_the_position_option():
    config = pressvisual.Config(free_position=(120, 80))

    pressvisual.apply_arguments(config, _args("--opacity", "0.5"))

    assert config.free_position == (120, 80)
    assert config.opacity == pytest.approx(0.5)


def test_instance_lock_path_is_per_user():
    path = pressvisual._instance_lock_path()

    assert path.name.startswith("pressvisual-")
    assert path.name.endswith(".lock")
    assert path.is_absolute()


def test_second_instance_cannot_take_the_lock(qapp, tmp_path, monkeypatch):  # noqa: ARG001
    monkeypatch.setattr(
        cli_module, "_instance_lock_path", lambda: tmp_path / "pv.lock"
    )
    first = pressvisual.acquire_instance_lock()
    assert first is not None
    try:
        assert pressvisual.acquire_instance_lock() is None
    finally:
        first.unlock()


def test_lock_is_released_when_the_first_instance_exits(qapp, tmp_path, monkeypatch):  # noqa: ARG001
    monkeypatch.setattr(
        cli_module, "_instance_lock_path", lambda: tmp_path / "pv.lock"
    )
    first = pressvisual.acquire_instance_lock()
    assert first is not None
    first.unlock()

    second = pressvisual.acquire_instance_lock()

    assert second is not None
    second.unlock()


def test_main_refuses_to_start_a_second_instance(
    qapp, tmp_path, monkeypatch, capsys  # noqa: ARG001 - QApplication requise
):
    monkeypatch.setattr(
        cli_module, "_instance_lock_path", lambda: tmp_path / "pv.lock"
    )
    first = pressvisual.acquire_instance_lock()
    assert first is not None
    try:
        code = pressvisual.main(["--lang", "fr"])
    finally:
        first.unlock()

    assert code == 1
    assert "déjà lancé" in capsys.readouterr().err


def test_unknown_position_is_rejected(capsys):
    with pytest.raises(SystemExit) as excinfo:
        pressvisual.build_arg_parser().parse_args(["--position", "milieu"])

    assert excinfo.value.code == 2
    assert "milieu" in capsys.readouterr().err


def test_help_lists_the_main_options():
    help_text = pressvisual.build_arg_parser().format_help()

    for option in (
        "--config",
        "--duration",
        "--position",
        "--group-text",
        "--click-through",
        "--toggle-hotkey",
    ):
        assert option in help_text


def test_help_exits_without_starting_the_application(capsys):
    # --lang fr évite d'installer un traducteur global pour la session.
    with pytest.raises(SystemExit) as excinfo:
        pressvisual.main(["--lang", "fr", "--help"])

    assert excinfo.value.code == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_default_config_path_points_to_config_json():
    path = pressvisual._default_config_path()

    assert path.name == "config.json"
    assert path.is_absolute()
