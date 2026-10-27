"""Catalogue anglais, compilation .qm et choix de la langue."""

from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

import pressvisual
from pressvisual_app import i18n as pv_i18n
from pressvisual_app.keymap import key_shape_for
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
    "click_back_label",
    "click_forward_label",
    "scroll_up_label",
    "scroll_down_label",
    "scroll_left_label",
    "scroll_right_label",
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


def catalogue_paths() -> list[Path]:
    """Catalogues fournis, un par langue (le français est écrit dans le code)."""
    return sorted(TS_PATH.parent.glob("*.ts"))


def test_every_catalogue_covers_the_whole_interface():
    """Chaque langue doit couvrir toutes les chaînes du code.

    La comparaison part des chaînes présentes dans le code : une chaîne neuve
    fait donc échouer ce test tant qu'elle n'est pas traduite partout, ce qui
    vaut aussi pour les langues ajoutées plus tard.
    """
    expected = ui_sources()
    for path in catalogue_paths():
        _language, messages = compile_translations.parse_ts(path)
        translated = {source for _context, source, _text in messages}

        assert sorted(expected - translated) == [], (
            f"{path.name} : chaînes sans traduction : "
            f"{sorted(expected - translated)}"
        )


def test_catalogues_share_the_same_strings():
    """Toutes les langues couvrent exactement les mêmes chaînes.

    Le code ne dit pas tout : plusieurs libellés sont traduits par table
    (``_t(TRANSITION_LABELS[value])``), hors de portée de l'analyse du code
    source. Le catalogue anglais, écrit à la main et complet, sert donc de
    référence aux autres — une chaîne ajoutée à une seule langue se voit ici.
    """
    _language, reference = compile_translations.parse_ts(TS_PATH)
    expected = {source for _context, source, _text in reference}

    for path in catalogue_paths():
        _language, messages = compile_translations.parse_ts(path)
        translated = {source for _context, source, _text in messages}

        assert sorted(expected - translated) == [], (
            f"{path.name} : chaînes sans traduction : "
            f"{sorted(expected - translated)}"
        )
        assert sorted(translated - expected) == [], (
            f"{path.name} : chaînes absentes de la référence : "
            f"{sorted(translated - expected)}"
        )


def test_compiled_catalog_is_up_to_date():
    assert compile_translations.check() == []


def test_each_catalogue_declares_its_language():
    for path in catalogue_paths():
        language, messages = compile_translations.parse_ts(path)

        assert messages, f"{path.name} : catalogue vide"
        assert path.stem == f"pressvisual_{language}", (
            f"{path.name} : langue déclarée {language!r}"
        )


def test_catalogues_match_the_supported_languages():
    """Un catalogue par langue annoncée, et rien de plus.

    Le français est la langue source, écrite directement dans le code : son
    absence de catalogue est normale.
    """
    codes = {path.stem.removeprefix("pressvisual_") for path in catalogue_paths()}

    assert codes == set(pressvisual.SUPPORTED_LANGUAGES) - {"fr"}


def test_every_supported_language_is_named():
    """Chaque langue porte son nom, et un seul, dans les réglages."""
    labels = pressvisual.LANGUAGE_LABELS

    assert set(labels) == set(pressvisual.SUPPORTED_LANGUAGES)
    assert len(set(labels.values())) == len(labels)


def test_catalogues_really_translate():
    """Un catalogue recopié de la source ne serait pas une traduction.

    Quelques identités sont normales (« Ctrl », « Alt », « Zoom ») ; une part
    importante de chaînes identiques signalerait un catalogue sans contenu.
    """
    for path in catalogue_paths():
        _language, messages = compile_translations.parse_ts(path)
        identical = [
            source for _context, source, text in messages if source == text
        ]

        assert len(identical) / len(messages) < 0.2, (
            f"{path.name} : {len(identical)} chaînes recopiées sans traduction"
        )


@pytest.mark.parametrize(
    "code", [code for code in pressvisual.SUPPORTED_LANGUAGES if code != "fr"]
)
def test_installing_a_catalogue_changes_the_interface(qapp, code):
    """Le catalogue installé doit vraiment changer les textes affichés."""
    translator = pressvisual.install_translator(qapp, code)
    assert translator is not None, f"catalogue {code} introuvable"
    try:
        assert pressvisual._t("Enregistrer") != "Enregistrer"
        assert pressvisual._t("Langue") != "Langue"
    finally:
        qapp.removeTranslator(translator)


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


def test_display_settings_are_translated(english, qapp, config):
    dialog = pressvisual.AppearanceDialog(config, "DejaVu Sans")
    try:
        labels = [
            dialog.mode_combo.itemText(index)
            for index in range(dialog.mode_combo.count())
        ]
        layouts = [
            dialog.layout_combo.itemText(index)
            for index in range(dialog.layout_combo.count())
        ]

        transitions = [
            dialog.transition_combo.itemText(index)
            for index in range(dialog.transition_combo.count())
        ]

        assert labels == ["Standard overlay", "Full keyboard"]
        assert layouts == ["AZERTY (French)", "QWERTY (English)"]
        assert transitions == [
            "Fade",
            "Slide down",
            "Slide up",
            "Slide left",
            "Slide right",
            "Zoom",
            "None",
        ]
        styles = [
            dialog.mouse_style_combo.itemText(index)
            for index in range(dialog.mouse_style_combo.count())
        ]

        tabs = [
            dialog.tabs.tabText(index) for index in range(dialog.tabs.count())
        ]
        assert tabs == ["Display", "Colors", "Layout", "Keys", "Interface"]
        assert styles == ["Classic", "Outline", "Minimal"]
        cursor_styles = [
            dialog.cursor_style_combo.itemText(index)
            for index in range(dialog.cursor_style_combo.count())
        ]
        assert cursor_styles == ["Classic", "Outline", "Key"]
        assert dialog.show_mouse.text() == "Show the mouse next to the keyboard"
        assert dialog.mouse_tracking.text() == (
            "Show clicks and scroll wheel movements next to the cursor"
        )
        assert dialog.count_repeats.text() == (
            "Group repeated presses of the same key (×2)"
        )
        animations = [
            dialog.animation_combo.itemText(index)
            for index in range(dialog.animation_combo.count())
        ]
        assert animations == [
            "Fade",
            "Zoom",
            "Bounce",
            "Slide",
            "Drop",
            "Unfold",
            "None",
        ]
    finally:
        dialog.deleteLater()


def test_key_shape_follows_the_translated_modifier(english, qapp, config):
    # L'éditeur nomme la touche « Maj » comme le clavier ; la bulle affiche
    # « Shift ». La forme choisie doit valoir pour les deux.
    config.key_shapes = {"Maj": "flower"}

    assert key_shape_for(config, "Shift") == "flower"
    assert key_shape_for(config, "Maj") == "flower"
    assert key_shape_for(config, "Ctrl") == "rounded"


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


def test_tray_shows_the_version_whatever_the_language(qapp, overlay, config):
    """La version ne se traduit pas : elle doit être identique dans les deux."""
    tray = pressvisual.TrayController(qapp, overlay, config)
    translator = None
    expected = f"{pressvisual.APP_NAME} {pressvisual.APP_VERSION}"
    try:
        assert tray.menu.actions()[0] is tray.act_version
        assert tray.act_version.text() == expected
        assert tray.act_version.isEnabled() is False
        assert tray.tray.toolTip().startswith(expected + "\n")

        translator = pressvisual.apply_language_change(qapp, tray, translator, "en")

        assert tray.act_version.text() == expected
        assert tray.tray.toolTip().startswith(expected + "\n")
    finally:
        if translator is not None:
            qapp.removeTranslator(translator)
        tray.tray.hide()
        tray.deleteLater()


def test_command_line_help_is_translated(english):
    help_text = pressvisual.build_arg_parser().format_help()

    assert "interface language (auto = system language)" in help_text
    assert "JSON configuration file" in help_text
    assert "print the version and quit" in help_text


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
    [
        ("fr_FR", "fr"),
        ("fr", "fr"),
        ("en_GB", "en"),
        # La région ne change pas la langue : « pt-BR » reste du portugais.
        ("de_DE", "de"),
        ("pt_BR", "pt"),
        ("zh_CN", "zh"),
        ("ja_JP", "ja"),
        ("es_MX", "es"),
        # Une langue que l'application ne parle pas retombe sur l'anglais.
        ("pl_PL", "en"),
        ("sv_SE", "en"),
    ],
)
def test_auto_language_follows_system(monkeypatch, system_locale, expected):
    fake = types.SimpleNamespace(name=lambda: system_locale)
    monkeypatch.setattr(pv_i18n.QLocale, "system", lambda: fake)

    assert pressvisual.resolve_language("auto") == expected
    assert pressvisual.resolve_language("") == expected


def test_suite_language_does_not_follow_the_host():
    """La langue « auto » des tests est figée, quel que soit le poste.

    `tests/conftest.py` fixe la langue du système à l'anglais pour toute la
    session : c'est ce qui empêche un test d'oublier `--lang fr` de passer
    inaperçu en local. Retirer ce réglage fait échouer ce test-ci.
    """
    assert pressvisual.resolve_language("auto") == "en"


def test_unknown_language_falls_back_to_system(monkeypatch):
    fake = types.SimpleNamespace(name=lambda: "fr_FR")
    monkeypatch.setattr(pv_i18n.QLocale, "system", lambda: fake)

    assert pressvisual.resolve_language("allemand") == "fr"


def test_config_accepts_supported_languages():
    for value in ("auto", "EN", *pressvisual.SUPPORTED_LANGUAGES):
        config = pressvisual.Config(language=value)
        assert config.validate() == []


def test_config_rejects_unknown_language():
    # « sv » (suédois) n'est pas fourni : la valeur doit être écartée.
    config = pressvisual.Config(language="sv")

    notes = config.validate()

    assert config.language == "auto"
    assert any("langue" in note for note in notes)


def test_language_cli_option():
    parser = pressvisual.build_arg_parser()

    assert parser.parse_args(["--lang", "en"]).lang == "en"
    assert parser.parse_args(["--lang=fr"]).lang == "fr"
    assert parser.parse_args([]).lang is None
    for code in pressvisual.SUPPORTED_LANGUAGES:
        assert parser.parse_args(["--lang", code]).lang == code
    with pytest.raises(SystemExit):
        parser.parse_args(["--lang", "sv"])


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
