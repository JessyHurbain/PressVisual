"""Interface en ligne de commande."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

import pressvisual
from pressvisual_app import cli as cli_module
from pressvisual_app import diagnostics


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


def test_frozen_macos_bundle_stores_config_in_application_support(
    monkeypatch, tmp_path
):
    """Un .app installé dans /Applications n'est pas inscriptible.

    La configuration doit donc aller dans le dossier utilisateur, et le dossier
    doit exister avant la première écriture.
    """
    bundle = tmp_path / "Applications" / "PressVisual.app"
    executable = bundle / "Contents" / "MacOS" / "PressVisual"
    executable.parent.mkdir(parents=True)
    executable.write_text("")
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setattr(cli_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli_module.sys, "platform", "darwin")
    monkeypatch.setattr(cli_module.sys, "executable", str(executable))
    # Path.home() lit HOME sous POSIX et USERPROFILE sous Windows : les deux
    # sont posés pour que le test se comporte pareil sur toute plateforme.
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    path = pressvisual._default_config_path()

    expected = home / "Library" / "Application Support" / "PressVisual"
    assert path == expected / "config.json"
    assert path.parent.is_dir()


class _FakeListener:
    """Écouteur factice : un test ne touche pas au clavier de la machine."""

    instances: list["_FakeListener"] = []

    def __init__(self, bridge, config, hotkeys):
        self.started = False
        self.stopped = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True


def test_main_starts_without_standard_streams(
    qapp, tmp_path, monkeypatch  # noqa: ARG001 - QApplication requise
):
    """Exécutable fenêtré : PyInstaller laisse ``sys.stderr`` à ``None``.

    Un message de configuration faisait alors mourir l'application
    (``AttributeError: 'NoneType' object has no attribute 'write'``) avant même
    qu'elle n'affiche l'overlay, et l'utilisateur ne voyait rien du tout.
    """
    log = tmp_path / "pressvisual.log"
    diagnostics.set_log_path(log)
    unreadable = tmp_path / "config.json"
    unreadable.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    _FakeListener.instances.clear()

    monkeypatch.setattr(
        cli_module, "_instance_lock_path", lambda: tmp_path / "pv.lock"
    )
    monkeypatch.setattr(cli_module, "InputListener", _FakeListener)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(cli_module.sys, "stderr", None)

    try:
        # --lang fr évite d'installer un traducteur global pour la session ; le
        # raccourci invalide ajoute un message de plus au journal.
        code = pressvisual.main(
            [
                "--lang",
                "fr",
                "--config",
                str(unreadable),
                "--toggle-hotkey",
                "ctrl+",
            ]
        )
    finally:
        # main() branche l'arrêt sur le signal de l'application de la session :
        # sans ce retrait, il se déclencherait plus tard sur des objets détruits.
        qapp.aboutToQuit.disconnect()

    assert code == 0
    written = log.read_text(encoding="utf-8")
    assert "Configuration illisible" in written
    assert "Raccourci global invalide ignoré" in written
    assert len(_FakeListener.instances) == 1
    assert _FakeListener.instances[0].started is True
    assert _FakeListener.instances[0].stopped is True


def test_version_is_printed_without_starting_the_overlay(
    qapp, capsys, monkeypatch  # noqa: ARG001 - QApplication requise
):
    _FakeListener.instances.clear()
    monkeypatch.setattr(cli_module, "InputListener", _FakeListener)

    # --lang fr évite d'installer un traducteur global pour la session : sur un
    # système anglophone, les tests suivants attendraient des libellés français.
    code = pressvisual.main(["--lang", "fr", "--version"])

    assert code == 0
    printed = capsys.readouterr().out.strip()
    assert printed == f"{pressvisual.APP_NAME} {pressvisual.APP_VERSION}"
    # Aucun écouteur : la version se lit sans lancer la capture.
    assert _FakeListener.instances == []


def test_version_answers_even_when_an_instance_is_running(
    qapp, tmp_path, monkeypatch, capsys  # noqa: ARG001 - QApplication requise
):
    monkeypatch.setattr(
        cli_module, "_instance_lock_path", lambda: tmp_path / "pv.lock"
    )
    first = pressvisual.acquire_instance_lock()
    assert first is not None
    try:
        # --lang fr : voir test_version_is_printed_without_starting_the_overlay.
        code = pressvisual.main(["--lang", "fr", "--version"])
    finally:
        first.unlock()

    assert code == 0
    assert pressvisual.APP_VERSION in capsys.readouterr().out


def test_version_without_a_console_opens_a_dialog(qapp, monkeypatch):  # noqa: ARG001
    """Exécutable fenêtré : la boîte de dialogue remplace la sortie standard."""
    shown: list[tuple] = []
    monkeypatch.setattr(cli_module.sys, "stdout", None)
    monkeypatch.setattr(
        cli_module.QMessageBox,
        "information",
        lambda parent, title, text: shown.append((title, text)),
    )

    # --lang fr : voir test_version_is_printed_without_starting_the_overlay.
    code = pressvisual.main(["--lang", "fr", "--version"])

    assert code == 0
    assert shown == [
        (pressvisual.APP_NAME, f"{pressvisual.APP_NAME} {pressvisual.APP_VERSION}")
    ]


def test_frozen_windows_executable_keeps_config_beside_it(monkeypatch, tmp_path):
    executable = tmp_path / "PressVisual.exe"
    executable.write_text("")

    monkeypatch.setattr(cli_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli_module.sys, "platform", "win32")
    monkeypatch.setattr(cli_module.sys, "executable", str(executable))

    # Comparaison avec le chemin résolu : sous Windows, resolve() développe les
    # noms courts (« RUNNER~1 ») que tempfile peut produire.
    expected = executable.resolve().parent / "config.json"
    assert pressvisual._default_config_path() == expected
