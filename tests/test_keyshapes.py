"""Formes de touches : tracés, configuration, clavier, bulles et éditeur."""

from __future__ import annotations

import json

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFont

import pressvisual
from pressvisual_app.shapes import key_shape_path

# ---------------------------------------------------------------------------
# Tracés
# ---------------------------------------------------------------------------


def test_every_shape_draws_something():
    rect = QRectF(0, 0, 40, 30)

    for shape in pressvisual.KEY_SHAPES:
        path = key_shape_path(shape, rect)

        assert not path.isEmpty(), shape
        assert path.boundingRect().width() > 20.0, shape


def test_shapes_do_not_share_the_same_outline():
    rect = QRectF(0, 0, 40, 30)
    counts = {
        shape: key_shape_path(shape, rect).elementCount()
        for shape in pressvisual.KEY_SHAPES
    }

    assert counts["flower"] != counts["rounded"]
    assert counts["star"] != counts["rounded"]
    assert counts["hexagon"] != counts["rounded"]
    assert counts["diamond"] != counts["rounded"]


def test_unknown_shape_falls_back_to_rounded():
    rect = QRectF(0, 0, 40, 30)

    unknown = key_shape_path("blob", rect)
    rounded = key_shape_path("rounded", rect)

    assert unknown.elementCount() == rounded.elementCount()
    assert unknown.boundingRect() == rounded.boundingRect()


def test_tiny_rect_still_produces_a_path():
    path = key_shape_path("flower", QRectF(0, 0, 2, 2))

    assert not path.isEmpty()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_key_shapes_are_saved_with_the_appearance(tmp_path):
    path = tmp_path / "config.json"
    config = pressvisual.Config()
    config.path = path

    assert config.save_appearance(
        {"key_shape": "flower", "key_shapes": {"A": "star"}}
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["key_shape"] == "flower"
    assert data["key_shapes"] == {"A": "star"}

    reloaded = pressvisual.Config.load(path, lambda _message: None)
    reloaded.validate()
    assert reloaded.key_shape == "flower"
    assert reloaded.shape_for("A") == "star"
    assert reloaded.shape_for("B") == "flower"


def test_unknown_key_shape_falls_back_to_rounded():
    config = pressvisual.Config(
        key_shape="blob", key_shapes={"A": "blob", "B": "star"}
    )

    notes = config.validate()

    assert config.key_shape == "rounded"
    assert config.key_shapes == {"B": "star"}
    assert any("key_shape" in note for note in notes)


def test_key_shapes_must_be_an_object():
    config = pressvisual.Config()
    config.key_shapes = ["A"]  # type: ignore[assignment]

    notes = config.validate()

    assert config.key_shapes == {}
    assert any("key_shapes" in note for note in notes)


def test_default_shape_is_rounded():
    assert pressvisual.Config().key_shape == "rounded"
    assert pressvisual.Config().shape_for("A") == "rounded"


def test_shape_lookup_ignores_case():
    config = pressvisual.Config(key_shapes={"é": "flower", "A": "star"})

    # La bulle affiche « É » quand la disposition nomme la touche « é ».
    assert config.shape_for("É") == "flower"
    assert config.shape_for("a") == "star"
    assert config.shape_for("Z") == "rounded"


# ---------------------------------------------------------------------------
# Clavier
# ---------------------------------------------------------------------------


def make_keyboard(qapp, shape: str, overrides: dict[str, str] | None = None):
    config = pressvisual.Config(
        display_mode="keyboard", key_shape=shape, key_shapes=overrides or {}
    )
    view = pressvisual.KeyboardView(
        config, QFont("DejaVu Sans"), pressvisual.Palette.from_config(config)
    )
    view.resize(view.sizeHint())
    return view


def test_keyboard_draws_the_configured_shape(qapp):
    rounded = make_keyboard(qapp, "rounded")
    flower = make_keyboard(qapp, "flower")
    try:
        assert rounded.grab().toImage() != flower.grab().toImage()
    finally:
        rounded.deleteLater()
        flower.deleteLater()


def test_keyboard_shape_can_be_set_per_key(qapp):
    plain = make_keyboard(qapp, "rounded")
    mixed = make_keyboard(qapp, "rounded", {"A": "star"})
    try:
        assert plain.grab().toImage() != mixed.grab().toImage()
    finally:
        plain.deleteLater()
        mixed.deleteLater()


# ---------------------------------------------------------------------------
# Formes larges
# ---------------------------------------------------------------------------


def test_wide_shape_still_fills_its_rect():
    rect = QRectF(0, 0, 88, 30)

    for shape in ("flower", "star", "diamond"):
        path = key_shape_path(shape, rect)
        bounds = path.boundingRect()

        assert bounds.width() > rect.width() * 0.85, shape
        assert bounds.height() > rect.height() * 0.9, shape


def test_wide_shape_leaves_room_for_the_label():
    # Une pastille garde une bande centrale pleine : l'étiquette n'est jamais
    # coupée par un creux, même sur une fleur ou une étoile.
    rect = QRectF(0, 0, 88, 30)
    centre = rect.center()
    # Une bande de la largeur d'une étiquette (« Entrée » fait 56 px).
    band = QRectF(centre.x() - 26.0, centre.y() - 6.0, 52.0, 12.0)

    for shape in pressvisual.KEY_SHAPES:
        assert key_shape_path(shape, rect).contains(band), shape


def test_wide_diamond_keeps_its_points():
    rect = QRectF(0, 0, 88, 30)
    path = key_shape_path("diamond", rect)

    # Un losange étiré n'aurait plus de place au centre : ses coins gauches
    # et droits restent des pointes, le haut et le bas s'aplatissent.
    assert path.contains(rect.center() - QPointF(rect.width() / 2 - 6, 0))
    assert not path.contains(QPointF(rect.left() + 4, rect.top() + 4))


# ---------------------------------------------------------------------------
# Bulles
# ---------------------------------------------------------------------------


def test_bubble_keys_take_the_configured_shape(qapp, overlay):
    overlay._cfg.key_shape = "flower"

    row = overlay._new_row([("A", "key")])

    assert [badge.shape for badge in row._badges] == ["flower"]


def test_bubble_shapes_can_be_set_per_key(qapp, overlay):
    overlay._cfg.key_shape = "rounded"
    overlay._cfg.key_shapes = {"A": "star", "Ctrl": "pill"}

    row = overlay._new_row([("Ctrl", "mod"), ("+", "plus"), ("A", "key")])

    assert [badge.shape for badge in row._badges] == ["pill", "rounded", "star"]


def test_bubble_leaves_clicks_and_typed_text_rounded(qapp, overlay):
    overlay._cfg.key_shape = "star"

    row = overlay._new_row([("Clic gauche", "mouse"), ("bonjour", "text")])

    assert [badge.shape for badge in row._badges] == ["rounded", "rounded"]


def test_bubble_shapes_follow_a_saved_setting(qapp, overlay):
    row = overlay._new_row([("A", "key")])

    overlay.apply_appearance({"key_shape": "star"})

    assert row._badges[0].shape == "star"


def test_preview_bubbles_follow_the_shape(qapp, config):
    config.key_shape = "pill"
    config.key_shapes = {"C": "flower"}
    preview = pressvisual.PreviewPanel(config, "DejaVu Sans")
    try:
        shapes = [
            badge.shape for row in preview._rows for badge in row._badges
        ]

        assert "pill" in shapes
        assert "flower" in shapes
    finally:
        preview.deleteLater()


# ---------------------------------------------------------------------------
# Éditeur
# ---------------------------------------------------------------------------


def make_editor(config: pressvisual.Config | None = None):
    return pressvisual.KeyShapeEditor(config or pressvisual.Config(), "DejaVu Sans")


def test_editor_lists_every_shape(qapp):
    editor = make_editor()
    try:
        shapes = [
            editor.default_combo.itemData(index)
            for index in range(editor.default_combo.count())
        ]
        brush = [
            editor.brush_combo.itemData(index)
            for index in range(editor.brush_combo.count())
        ]

        assert shapes == list(pressvisual.KEY_SHAPES)
        assert brush == list(pressvisual.KEY_SHAPES)
        assert editor.values() == {"key_shape": "rounded", "key_shapes": {}}
    finally:
        editor.deleteLater()


def test_editor_gives_a_shape_to_one_key(qapp):
    editor = make_editor()
    emitted: list[bool] = []
    editor.changed.connect(lambda: emitted.append(True))
    try:
        editor.brush_combo.setCurrentIndex(
            editor.brush_combo.findData("flower")
        )
        editor._paint_key("A")

        assert editor.values()["key_shapes"] == {"A": "flower"}
        assert editor._patches["A"][0].shape == "flower"
        assert editor._patches["A"][0].overridden
        assert editor._patches["Z"][0].shape == "rounded"
        assert emitted
    finally:
        editor.deleteLater()


def test_editor_applies_a_shape_to_every_key(qapp):
    editor = make_editor()
    try:
        editor._paint_key("A")
        editor.brush_combo.setCurrentIndex(editor.brush_combo.findData("star"))
        editor._apply_to_all()

        assert editor.values() == {"key_shape": "star", "key_shapes": {}}
        assert editor._patches["A"][0].shape == "star"
        assert not editor._patches["A"][0].overridden
    finally:
        editor.deleteLater()


def test_editor_clears_exceptions(qapp):
    editor = make_editor()
    try:
        editor._paint_key("A")
        editor._paint_key("B")
        editor._clear_overrides()

        assert editor.values()["key_shapes"] == {}
        assert editor._patches["A"][0].shape == "rounded"
    finally:
        editor.deleteLater()


def test_editor_follows_the_layout(qapp):
    editor = make_editor()
    try:
        assert "é" in editor._patches

        editor.set_layout("qwerty")

        assert "é" not in editor._patches
        assert "Q" in editor._patches
    finally:
        editor.deleteLater()


def test_editor_reset_restores_defaults(qapp):
    config = pressvisual.Config(key_shape="pill", key_shapes={"A": "flower"})
    editor = make_editor(config)
    try:
        assert editor.values() == {"key_shape": "pill", "key_shapes": {"A": "flower"}}

        editor.reset()

        assert editor.values() == {"key_shape": "rounded", "key_shapes": {}}
    finally:
        editor.deleteLater()
