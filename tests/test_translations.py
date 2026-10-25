"""Catalogue anglais, compilation .qm et choix de la langue."""

from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

import pressvisual
from pressvisual_app import i18n as pv_i18n
from tools import compile_translations

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "pressvisual_app"
TS_PATH = PROJECT_ROOT / "translations" / "pressvisual_en.ts"

LABEL_FIELDS = (
    "ctrl_label",
    "alt_label",
    "shift_label",
    "win_label",
    "click_left_label",
    "click_right_label",
    "click_middle_label",
    "scroll_up_label",
    "scroll_down_label",
)


def ui_sources() -> set[str]:
    """Toutes les chaînes d'interface présentes dans le code."""
    found: set[str] = set()
    for module_path in sorted(APP_DIR.glob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_t"
            ):
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(
                        argument.value, str
                    ):
                        found.add(argument.value)
    found.update(pressvisual.SPECIAL_KEY_LABELS.values())
    found.update(pressvisual.POSITION_LABELS.values())
    found.update(str(value) for value in pressvisual.MULTI_CLICK_LABELS.values())
    found.update(label for _key, label in pressvisual.AppearanceDialog.COLOR_LABELS)
    config = pressvisual.Config()
    found.update(str(getattr(config, name)) for name in LABEL_FIELDS)
    return found


@pytest.fixture
def english(qapp):
    translator = pressvisual.install_translator(qapp, "en")
    assert translator is not None, "catalogue anglais introuvable"
    yield translator
    qapp.removeTranslator(translator)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def test_catalog_is_complete():
    _language, messages = compile_translations.parse_ts(TS_PATH)
    translated = {source for _context, source, _text in messages}

    missing = sorted(ui_sources() - translated)

    assert missing == [], f"chaînes sans traduction : {missing}"


def test_compiled_catalog_is_up_to_date():
    assert compile_translations.check() == []


def test_catalog_declares_english():
    language, messages = compile_translations.parse_ts(TS_PATH)

    assert language == "en"
    assert messages


def test_qm_is_loadable_by_qt(qapp):
    # qapp garantit qu'une QApplication existe : verify() réutilise
    # l'instance courante au lieu d'en créer une seconde.
    assert compile_translations.verify() == []


def test_french_is_the_source_language(qapp):
    assert pressvisual._t("Espace") == "Espace"
    assert pressvisual.install_translator(qapp, "fr") is None


def test_missing_catalog_is_reported(qapp, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(pv_i18n, "translations_directory", lambda: tmp_path)

    assert pressvisual.install_translator(qapp, "en") is None
    assert "Traduction introuvable" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Rendu traduit
# ---------------------------------------------------------------------------


def test_key_and_modifier_labels(english, config):
    assert pressvisual._t("Espace") == "Space"
    assert pressvisual.key_label(config, "space") == "Space"
    assert pressvisual.key_label(config, "print_screen") == "Print Screen"
    assert pressvisual.key_label(config, "page_up") == "Page ↑"
    assert pressvisual.modifier_label(config, "shift") == "Shift"
    assert pressvisual.modifier_label(config, "ctrl") == "Ctrl"


def test_position_labels(english):
    assert pressvisual._t("Haut gauche") == "Top left"
    assert pressvisual._t("Bas centre") == "Bottom center"


def test_badges_use_english_labels(english, overlay):
    overlay._on_key(pressvisual.KeyEvent(token="space", char=None))
    overlay._on_click(pressvisual.MouseEvent(kind="click", button="left"))
    overlay._on_scroll(pressvisual.MouseEvent(kind="scroll", direction=1))
    overlay._on_click(
        pressvisual.MouseEvent(kind="click", button="middle", mods=("ctrl",))
    )

    lines = [list(row._items) for row in overlay._rows]

    assert [("Space", "key")] in lines
    assert [("Left click", "mouse")] in lines
    assert [("Scroll ↑", "mouse")] in lines
    assert [
        ("Ctrl", "mod"),
        ("+", "plus"),
        ("Middle click", "mouse"),
    ] in lines


def test_status_and_position_are_translated(english, overlay):
    overlay.set_position("top-left")
    assert list(overlay._rows[0]._items) == [("Position: Top left", "status")]

    overlay.set_capture_enabled(False)
    overlay.set_capture_enabled(True, announce=True)
    assert list(overlay._rows[-1]._items) == [("Capture on", "status")]


def test_appearance_dialog_is_translated(english, qapp, config):
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    try:
        assert "Appearance" in dialog.windowTitle()
    finally:
        dialog.deleteLater()


def test_tray_menu_is_translated(english, qapp, overlay, config):
    tray = pressvisual.TrayController(qapp, overlay, config)
    try:
        assert tray.act_quit.text().startswith("Quit")
        assert tray.act_appearance.text() == "Customize overlay…"
        assert tray.position_actions["top-left"].text() == "Top left"
        assert "Show/hide" in tray.tray.toolTip()
    finally:
        tray.tray.hide()
        tray.deleteLater()


def test_language_change_updates_the_menu(qapp, overlay, config):
    tray = pressvisual.TrayController(qapp, overlay, config)
    translator = None
    try:
        assert tray.act_quit.text().startswith("Quitter")

        translator = pressvisual.apply_language_change(qapp, tray, None, "en")
        assert translator is not None
        assert tray.act_quit.text().startswith("Quit")
        assert tray.act_appearance.text() == "Customize overlay…"
        assert tray.position_actions["bottom-right"].text() == "Bottom right"
        assert "Show/hide" in tray.tray.toolTip()

        translator = pressvisual.apply_language_change(qapp, tray, translator, "fr")
        assert translator is None
        assert tray.act_quit.text().startswith("Quitter")
        assert tray.position_actions["bottom-right"].text() == "Bas droite"
    finally:
        if translator is not None:
            qapp.removeTranslator(translator)
        tray.tray.hide()
        tray.deleteLater()


def test_command_line_help_is_translated(english):
    help_text = pressvisual.build_arg_parser().format_help()

    assert "interface language: auto (system), fr or en" in help_text
    assert "JSON configuration file" in help_text


# ---------------------------------------------------------------------------
# Choix de la langue
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("fr", "fr"),
        ("en", "en"),
        ("FR", "fr"),
        ("En", "en"),
        ("fr_FR", "fr"),
        ("en_US", "en"),
        ("fr-CA", "fr"),
    ],
)
def test_explicit_language_is_honoured(value, expected):
    assert pressvisual.resolve_language(value) == expected


@pytest.mark.parametrize(
    ("system_locale", "expected"),
    [("fr_FR", "fr"), ("fr", "fr"), ("de_DE", "en"), ("en_GB", "en")],
)
def test_auto_language_follows_system(monkeypatch, system_locale, expected):
    fake = types.SimpleNamespace(name=lambda: system_locale)
    monkeypatch.setattr(pv_i18n.QLocale, "system", lambda: fake)

    assert pressvisual.resolve_language("auto") == expected
    assert pressvisual.resolve_language("") == expected


def test_unknown_language_falls_back_to_system(monkeypatch):
    fake = types.SimpleNamespace(name=lambda: "fr_FR")
    monkeypatch.setattr(pv_i18n.QLocale, "system", lambda: fake)

    assert pressvisual.resolve_language("allemand") == "fr"


def test_config_accepts_supported_languages():
    for value in ("auto", "fr", "en", "EN"):
        config = pressvisual.Config(language=value)
        assert config.validate() == []


def test_config_rejects_unknown_language():
    config = pressvisual.Config(language="de")

    notes = config.validate()

    assert config.language == "auto"
    assert any("langue" in note for note in notes)


def test_language_cli_option():
    parser = pressvisual.build_arg_parser()

    assert parser.parse_args(["--lang", "en"]).lang == "en"
    assert parser.parse_args(["--lang=fr"]).lang == "fr"
    assert parser.parse_args([]).lang is None
    with pytest.raises(SystemExit):
        parser.parse_args(["--lang", "de"])


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["--lang", "en"], "en"),
        (["--lang=en"], "en"),
        (["--lang", "fr", "--lang", "en"], "fr"),
        (["--duration", "3"], "auto"),
        ([], "auto"),
        (["--lang"], "auto"),
    ],
)
def test_language_is_read_before_parsing(arguments, expected):
    assert pressvisual._language_argument(arguments) == expected
