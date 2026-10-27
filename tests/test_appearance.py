"""Palette de couleurs et fenêtre de personnalisation."""

from __future__ import annotations

import json

from PyQt6.QtCore import QAbstractAnimation, QPoint
from PyQt6.QtGui import QColor, QFontDatabase, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QScrollArea,
)

import pressvisual
from pressvisual_app import appearance as appearance_module
from pressvisual_app import overlay as overlay_module

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------


def test_palette_derives_colors_from_config(config):
    palette = pressvisual.Palette.from_config(config)

    assert palette.text.name() == "#f6f7f9"
    assert palette.panel_top.name() == "#26282f"
    assert palette.panel_bottom.name() == "#0e0f12"
    assert palette.key_bg.name() == "#f5f6f8"
    # Les traits sont dérivés du texte avec une alpha réduite.
    assert palette.border.alpha() == 40
    assert palette.mod_bg.alpha() == 28


def test_palette_uses_black_text_on_light_accent(config):
    config.accent_color = "#ffe066"

    palette = pressvisual.Palette.from_config(config)

    assert palette.on_accent.name() == "#000000"


def test_palette_uses_white_text_on_dark_accent(config):
    config.accent_color = "#1b2b6b"

    palette = pressvisual.Palette.from_config(config)

    assert palette.on_accent.name() == "#ffffff"


def test_palette_update_mutates_in_place(config):
    palette = pressvisual.Palette.from_config(config)
    shared = palette
    config.text_color = "#00ff00"

    palette.update_from_config(config)

    assert shared is palette
    assert palette.text.name() == "#00ff00"


def test_palette_falls_back_on_invalid_color(config):
    config.accent_color = "n'importe quoi"

    palette = pressvisual.Palette.from_config(config)

    assert palette.accent.name() == pressvisual.Config.accent_color


# ---------------------------------------------------------------------------
# Fenêtre d'apparence
# ---------------------------------------------------------------------------


def make_dialog(qapp, config, family="DejaVu Sans"):
    dialog = pressvisual.AppearanceDialog(config, family)
    qapp.processEvents()
    return dialog


def test_dialog_values_reflect_controls(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.opacity_slider.setValue(50)
        dialog.font_size.setValue(24)
        dialog.corner_radius.setValue(4)
        dialog.margin.setValue(40)
        dialog.max_width.setValue(700)
        dialog.color_buttons["accent_color"].set_color(QColor("#ff8800"))

        values = dialog.values()

        assert values["opacity"] == 0.5
        assert values["font_size"] == 24
        assert values["corner_radius"] == 4
        assert values["margin"] == 40
        assert values["max_width"] == 700
        assert values["accent_color"] == "#ff8800"
        assert values["font_family"]
        assert dialog.opacity_label.text() == "50 %"
    finally:
        dialog.deleteLater()


def test_dialog_preview_does_not_touch_base_config(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.font_size.setValue(30)
        dialog.margin.setValue(60)

        preview = dialog._preview_config()

        assert preview.font_size == 30
        assert preview.margin == 60
        assert config.font_size == 16
        assert config.margin == 28
    finally:
        dialog.deleteLater()


def test_dialog_reset_restores_defaults(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.opacity_slider.setValue(40)
        dialog.font_size.setValue(34)
        dialog.corner_radius.setValue(2)
        dialog.margin.setValue(70)
        dialog.max_width.setValue(1200)
        dialog.color_buttons["text_color"].set_color(QColor("#ff0000"))

        dialog._reset()
        values = dialog.values()

        defaults = pressvisual.Config()
        assert values["opacity"] == defaults.opacity
        assert values["font_size"] == defaults.font_size
        assert values["corner_radius"] == defaults.corner_radius
        assert values["margin"] == defaults.margin
        assert values["max_width"] == defaults.max_width
        assert values["text_color"] == defaults.text_color
    finally:
        dialog.deleteLater()


def test_dialog_preview_paints_without_error(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.preview.resize(420, 160)
        dialog.preview.update_appearance(dialog._preview_config(), "DejaVu Sans")

        pixmap = dialog.preview.grab()

        assert not pixmap.isNull()
    finally:
        dialog.deleteLater()


def test_preview_stage_replays_the_shared_geometry(qapp, monkeypatch):
    """L'aperçu et l'overlay lisent la même géométrie de transition."""
    seen = []

    def recorder(style, width, height, progress):
        seen.append((style, width, height, progress))
        return 0.0, 0.0, 1.0, 1.0

    monkeypatch.setattr(appearance_module, "transition_geometry", recorder)
    stage = appearance_module.TransitionStage()
    try:
        stage.resize(240, 120)
        shot = QPixmap(120, 60)
        shot.fill(QColor("black"))
        stage.set_frame(shot, QPoint(20, 10), "slide-left", 0.5)

        stage.grab()

        assert seen, "l'aperçu doit passer par la géométrie commune"
        style, width, height, progress = seen[-1]
        assert style == "slide-left"
        assert (width, height) == (120.0, 60.0)
        assert progress == 0.5
    finally:
        stage.deleteLater()


def test_dialog_exposes_display_mode_choices(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        assert dialog.mode_combo.count() == 2
        assert dialog.mode_combo.currentData() == "overlay"
        assert dialog.mode_combo.findData("keyboard") >= 0
        assert dialog.layout_combo.count() == 2
        assert dialog.layout_combo.currentData() == "azerty"
        assert dialog.layout_combo.findData("qwerty") >= 0
    finally:
        dialog.deleteLater()


def test_dialog_reflects_configured_display_settings(qapp, config):
    config.display_mode = "keyboard"
    config.keyboard_layout = "qwerty"

    dialog = make_dialog(qapp, config)

    try:
        assert dialog.mode_combo.currentData() == "keyboard"
        assert dialog.layout_combo.currentData() == "qwerty"
    finally:
        dialog.deleteLater()


def test_dialog_values_include_display_settings(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))
        dialog.layout_combo.setCurrentIndex(dialog.layout_combo.findData("qwerty"))

        values = dialog.values()

        assert values["display_mode"] == "keyboard"
        assert values["keyboard_layout"] == "qwerty"
    finally:
        dialog.deleteLater()


def test_dialog_reset_restores_the_standard_overlay(qapp, config):
    config.display_mode = "keyboard"
    config.keyboard_layout = "qwerty"
    dialog = make_dialog(qapp, config)
    try:
        dialog._reset()

        assert dialog.mode_combo.currentData() == "overlay"
        assert dialog.layout_combo.currentData() == "azerty"
    finally:
        dialog.deleteLater()


def test_preview_switches_to_the_keyboard(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        assert dialog.preview._keyboard.isHidden() is True
        assert not any(row.isHidden() for row in dialog.preview._rows)

        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))

        assert dialog.preview._keyboard.isHidden() is False
        assert all(row.isHidden() for row in dialog.preview._rows)

        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("overlay"))

        assert dialog.preview._keyboard.isHidden() is True
    finally:
        dialog.deleteLater()


def test_preview_keyboard_follows_the_chosen_layout(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))
        dialog.layout_combo.setCurrentIndex(dialog.layout_combo.findData("qwerty"))

        assert dialog.preview._keyboard.layout.name == "qwerty"
    finally:
        dialog.deleteLater()


def test_preview_animates_a_keystroke_and_a_click(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        assert preview._demo_timer.isActive()
        assert preview._demo_timer.interval() == appearance_module.DEMO_STEP_MS

        preview._demo_step = 0
        preview._apply_demo_step()

        assert preview._keyboard.active_labels() == ["A"]
        assert preview._mouse.active_buttons() == ["left"]
        assert preview._demo_row._items == [("a", "key")]

        preview._advance_demo()

        assert preview._keyboard.active_labels() == []
        assert preview._mouse.active_buttons() == []
        assert preview._demo_row._items == [("a", "key")]

        preview._advance_demo()

        labels = preview._keyboard.active_labels()
        assert "E" in labels
        # La démonstration enfonce la touche de gauche : un seul Maj s'allume.
        assert labels.count("Maj") == 1
        assert preview._mouse.active_buttons() == ["right"]
        assert preview._mouse.scroll == ("vertical", 1)
        assert preview._demo_row._items == [("Clic droit", "mouse")]
    finally:
        dialog.deleteLater()


def test_preview_demo_plays_once_then_shows_the_transition(qapp, config):
    config.transition = "fade"
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        preview._demo_timer.stop()
        preview._demo_step = 0
        preview._apply_demo_step()

        # Une étape par minuteur, sans revenir au début : la démonstration
        # s'arrête au lieu de boucler.
        for _ in range(len(preview._demo_steps()) - 1):
            preview._advance_demo()

        assert preview._demo_step == len(preview._demo_steps()) - 1
        assert preview._demo_timer.isActive()

        preview._advance_demo()

        assert not preview._demo_timer.isActive()
        # Elle se termine par la sortie de la bulle, une seule fois.
        assert preview._phase == "exit"
    finally:
        dialog.deleteLater()


def test_preview_stays_still_until_a_setting_changes(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        preview._demo_timer.stop()
        preview._cycle_timer.stop()
        preview._replay_timer.stop()
        assert not preview._demo_timer.isActive()

        dialog.font_size.setValue(config.font_size + 2)

        # Le rejeu attend la fin du geste, puis la démonstration repart.
        assert preview._replay_timer.isActive()
        assert not preview._demo_timer.isActive()

        preview._replay()

        assert preview._demo_timer.isActive()
    finally:
        dialog.deleteLater()


def test_preview_replays_the_transition_alone_for_a_transition_setting(
    qapp, config
):
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview

        dialog.transition_combo.setCurrentIndex(
            dialog.transition_combo.findData("zoom")
        )
        preview._replay()

        # Pas de frappe simulée : la transition se voit tout de suite.
        assert not preview._demo_timer.isActive()
        assert preview._cycle_timer.isActive()
        assert preview._phase == "idle"
    finally:
        dialog.deleteLater()


def test_a_slider_drag_replays_the_preview_once(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        replays: list[int] = []
        original = preview.play_demo
        preview.play_demo = lambda: replays.append(1) or original()
        preview._replay_timer.stop()

        # Un cran de curseur envoyé toutes les quelques millisecondes :
        # l'aperçu ne doit pas repartir à chaque valeur.
        for value in range(40, 70, 3):
            dialog.opacity_slider.setValue(value)

        assert replays == []
        assert preview._replay_timer.isActive()

        preview._replay()

        assert replays == [1]
    finally:
        dialog.deleteLater()


def test_preview_demo_row_follows_the_mode(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        assert dialog.preview._demo_row.isHidden() is False

        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))

        assert dialog.preview._demo_row.isHidden() is True

        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("overlay"))

        assert dialog.preview._demo_row.isHidden() is False
    finally:
        dialog.deleteLater()


def test_preview_keyboard_paints(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("keyboard"))
        dialog.preview.resize(560, 240)
        dialog.preview.update_appearance(dialog._preview_config(), "DejaVu Sans")

        pixmap = dialog.preview.grab()

        assert not pixmap.isNull()
    finally:
        dialog.deleteLater()


def test_dialog_exposes_mouse_tracking(qapp, config):
    config.mouse_tracking = True
    dialog = make_dialog(qapp, config)
    try:
        assert dialog.mouse_tracking.isChecked()
        assert dialog.values()["mouse_tracking"] is True

        dialog.mouse_tracking.setChecked(False)

        assert dialog.values()["mouse_tracking"] is False

        dialog._reset()
        assert not dialog.mouse_tracking.isChecked()
    finally:
        dialog.deleteLater()


def test_dialog_exposes_repeat_counting(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        assert dialog.count_repeats.isChecked() is True
        assert dialog.values()["count_repeats"] is True

        dialog.count_repeats.setChecked(False)

        assert dialog.values()["count_repeats"] is False

        dialog._reset()
        assert dialog.count_repeats.isChecked() is True
    finally:
        dialog.deleteLater()


def test_dialog_exposes_mouse_styles(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        choices = [
            dialog.mouse_style_combo.itemData(index)
            for index in range(dialog.mouse_style_combo.count())
        ]

        assert choices == ["classic", "outline", "minimal"]
        assert dialog.mouse_style_combo.currentData() == "classic"

        dialog.mouse_style_combo.setCurrentIndex(
            dialog.mouse_style_combo.findData("outline")
        )
        assert dialog.values()["mouse_style"] == "outline"

        dialog._reset()
        assert dialog.mouse_style_combo.currentData() == "classic"
    finally:
        dialog.deleteLater()


def test_dialog_splits_its_settings_into_tabs(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        titles = [
            dialog.tabs.tabText(index) for index in range(dialog.tabs.count())
        ]

        assert titles == [
            "Affichage",
            "Couleurs",
            "Mise en forme",
            "Touches",
            "Interface",
        ]
        for index in range(dialog.tabs.count()):
            page = dialog.tabs.widget(index)
            assert isinstance(page, QScrollArea)
            assert page.widgetResizable()
    finally:
        dialog.deleteLater()


def test_dialog_keeps_its_buttons_visible(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.show()
        qapp.processEvents()
        save = dialog.buttons.button(QDialogButtonBox.StandardButton.Save)

        assert save.isVisible()
        centre = save.mapTo(dialog, save.rect().center())
        assert dialog.rect().contains(centre)
        assert dialog.buttons.parent() is dialog
    finally:
        dialog.close()
        dialog.deleteLater()


def test_dialog_exposes_the_key_editor(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        assert dialog.key_editor.values()["key_shape"] == "rounded"

        dialog.key_editor.brush_combo.setCurrentIndex(
            dialog.key_editor.brush_combo.findData("star")
        )
        dialog.key_editor._paint_key("A")

        assert dialog.values()["key_shapes"] == {"A": "star"}
        assert dialog._preview_config().shape_for("A") == "star"

        dialog._reset()
        assert dialog.values()["key_shapes"] == {}
        assert dialog.values()["key_shape"] == "rounded"
    finally:
        dialog.deleteLater()


def test_dialog_key_editor_follows_the_layout(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        assert "é" in dialog.key_editor._patches

        dialog.layout_combo.setCurrentIndex(
            dialog.layout_combo.findData("qwerty")
        )

        assert "é" not in dialog.key_editor._patches
    finally:
        dialog.deleteLater()


def test_dialog_exposes_cursor_styles(qapp, config):
    config.cursor_style = "outline"
    dialog = make_dialog(qapp, config)
    try:
        choices = [
            dialog.cursor_style_combo.itemData(index)
            for index in range(dialog.cursor_style_combo.count())
        ]

        assert choices == ["classic", "outline", "keycap"]
        assert dialog.cursor_style_combo.currentData() == "outline"
        assert dialog.values()["cursor_style"] == "outline"

        dialog.cursor_style_combo.setCurrentIndex(
            dialog.cursor_style_combo.findData("keycap")
        )
        assert dialog.values()["cursor_style"] == "keycap"

        dialog._reset()
        assert dialog.cursor_style_combo.currentData() == "classic"
    finally:
        dialog.deleteLater()


def test_dialog_exposes_language_choice(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        combo = dialog.language_combo
        assert combo.count() == 3
        assert combo.currentData() == "auto"
        assert combo.findData("fr") >= 0
        assert combo.findData("en") >= 0
    finally:
        dialog.deleteLater()


def test_dialog_reflects_configured_language(qapp, config):
    config.language = "en"

    dialog = make_dialog(qapp, config)
    try:
        assert dialog.values()["language"] == "en"
    finally:
        dialog.deleteLater()


def test_dialog_reset_restores_automatic_language(qapp, config):
    config.language = "en"
    dialog = make_dialog(qapp, config)
    try:
        dialog._reset()

        assert dialog.values()["language"] == "auto"
    finally:
        dialog.deleteLater()


def test_edit_appearance_applies_language_and_saves_it(
    monkeypatch, qapp, overlay, config, tmp_path
):
    path = tmp_path / "config.json"
    config.path = path
    emitted: list[str] = []
    overlay.language_changed.connect(emitted.append)

    class FakeDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"language": "en", "opacity": 0.5}

    monkeypatch.setattr(overlay_module, "AppearanceDialog", FakeDialog)

    overlay.edit_appearance()

    assert emitted == ["en"]
    assert config.language == "en"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["language"] == "en"
    assert data["opacity"] == 0.5


def test_edit_appearance_keeps_language_silent_when_unchanged(
    monkeypatch, qapp, overlay, config
):
    emitted: list[str] = []
    overlay.language_changed.connect(emitted.append)

    class FakeDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return {"language": "auto"}

    monkeypatch.setattr(overlay_module, "AppearanceDialog", FakeDialog)

    overlay.edit_appearance()

    assert emitted == []


def test_color_button_ignores_invalid_colors(qapp):
    button = pressvisual.ColorButton(QColor("#123456"))
    try:
        button.set_color(QColor())
        assert button.color().name() == "#123456"

        button.set_color(QColor("#abcdef"))
        assert button.color().name() == "#abcdef"
    finally:
        button.deleteLater()


# ---------------------------------------------------------------------------
# Police
# ---------------------------------------------------------------------------


def test_choose_font_family_keeps_configured_family(config):
    config.font_family = "Ma Police Maison"

    assert pressvisual._choose_font_family(config) == "Ma Police Maison"


def test_choose_font_family_returns_available_default(config):
    family = pressvisual._choose_font_family(config)

    assert family
    assert family in QFontDatabase.families() or family == QApplication.font().family()


# ---------------------------------------------------------------------------
# Aperçu de la transition
# ---------------------------------------------------------------------------


def test_preview_freezes_the_bubble_without_the_checkerboard(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        dialog.preview.resize(420, 160)
        dialog.preview.update_appearance(dialog._preview_config(), "DejaVu Sans")
        preview = dialog.preview

        preview._freeze()

        assert preview._shot is not None
        image = preview._shot.toImage()
        # Le coin arrondi reste transparent : le damier n'est pas figé avec.
        assert image.pixelColor(0, 0).alpha() == 0
        centre = image.pixelColor(image.width() // 2, image.height() // 2)
        assert centre.alpha() > 0
    finally:
        dialog.deleteLater()


def test_preview_plays_the_transition_and_returns(qapp, config):
    config.transition = "slide"
    config.transition_out_ms = 200
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        preview._start_exit()

        assert preview._stack.currentWidget() is preview._stage
        assert preview._phase == "exit"
        assert preview._stage._style == "slide"

        preview._transition.setCurrentTime(100)
        qapp.processEvents()
        assert 0.0 < preview._progress < 1.0

        preview._transition.setCurrentTime(200)
        qapp.processEvents()
        assert preview._phase == "hidden"
        assert preview._cycle_timer.isActive()

        preview._start_entry()
        preview._transition.setCurrentTime(preview._transition.duration())
        qapp.processEvents()

        assert preview._phase == "idle"
        assert preview._stack.currentWidget() is preview._surface
    finally:
        dialog.deleteLater()


def test_preview_none_transition_hides_at_once(qapp, config):
    config.transition = "none"
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        preview._start_exit()

        assert preview._phase == "hidden"
        assert preview._transition.state() != QAbstractAnimation.State.Running
        # Rien à dessiner : la bulle est déjà sortie.
        assert preview._shot is None
        assert preview._stack.currentWidget() is preview._stage
    finally:
        dialog.deleteLater()


def test_preview_follows_the_chosen_duration(qapp, config):
    config.transition = "zoom"
    config.transition_out_ms = 900
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        preview._start_exit()

        assert preview._transition.duration() == 900
        assert preview._stage._style == "zoom"
    finally:
        dialog.deleteLater()


def test_changing_the_transition_restarts_the_preview(qapp, config):
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        preview._start_exit()
        preview._transition.setCurrentTime(100)

        dialog.transition_combo.setCurrentIndex(
            dialog.transition_combo.findData("slide-left")
        )
        preview._replay()

        # Le rejeu interrompt la sortie en cours et repart de la bulle.
        assert preview._phase == "idle"
        assert preview._transition.state() != QAbstractAnimation.State.Running
        assert preview._stack.currentWidget() is preview._surface
    finally:
        dialog.deleteLater()


def test_preview_cycle_hides_then_brings_the_bubble_back(qapp, config):
    config.transition = "fade"
    config.transition_out_ms = 120
    dialog = make_dialog(qapp, config)
    try:
        preview = dialog.preview
        preview.play_transition()
        assert preview._phase == "idle"

        preview._on_cycle_timeout()
        assert preview._phase == "exit"

        preview._transition.setCurrentTime(preview._transition.duration())
        qapp.processEvents()
        assert preview._phase == "hidden"

        preview._on_cycle_timeout()
        assert preview._phase == "entry"

        preview._transition.setCurrentTime(preview._transition.duration())
        qapp.processEvents()
        assert preview._phase == "idle"
        assert preview._stack.currentWidget() is preview._surface
        # La bulle revenue, plus rien ne se rejoue tout seul.
        assert not preview._cycle_timer.isActive()
        assert not preview._demo_timer.isActive()
    finally:
        dialog.deleteLater()
