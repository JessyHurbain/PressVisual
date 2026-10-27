#!/usr/bin/env python3
"""Génère les illustrations du README (dossier ``docs/images``).

Les images sont composées hors écran : un fond de bureau factice, puis une
capture réelle de l'overlay ou de la fenêtre de réglages. Rien n'est simulé :
les pastilles, le clavier et les couleurs viennent du code de l'application.

Utilisation :
    QT_QPA_PLATFORM=offscreen python tools/make_docs_images.py
    QT_QPA_PLATFORM=offscreen python tools/make_docs_images.py --only standard

Le GIF de démonstration est assemblé avec ``ffmpeg`` ; les autres images
sortent en PNG. Les chemins d'écriture sont relatifs à la racine du dépôt.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import (  # noqa: E402
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
)

import pressvisual  # noqa: E402 - après le réglage de QT_QPA_PLATFORM
from pressvisual_app.events import KeyEvent, MouseEvent  # noqa: E402

IMAGES = PROJECT_ROOT / "docs" / "images"

#: Couleurs du bureau factice, reprises des premières illustrations.
BACKDROP_TOP = "#293c62"
BACKDROP_BOTTOM = "#0e131c"
WINDOW_BG = "#f7f8fa"
WINDOW_BAR = "#eceef3"
LINE_BG = "#ccd3df"
BLOCK_BG = "#e4e8ef"


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------
def backdrop(width: int, height: int, with_window: bool = True) -> QImage:
    """Fond dégradé, avec une fenêtre blanche stylisée."""
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0.0, QColor(BACKDROP_TOP))
    gradient.setColorAt(1.0, QColor(BACKDROP_BOTTOM))
    painter.fillRect(image.rect(), gradient)

    if with_window:
        _paint_window(painter, width, height)
    painter.end()
    return image


def _paint_window(painter: QPainter, width: int, height: int) -> None:
    frame = QRectF(width * 0.10, height * 0.07, width * 0.62, height * 0.62)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(WINDOW_BG))
    painter.drawRoundedRect(frame, 10, 10)

    bar = QRectF(frame.left(), frame.top(), frame.width(), 34)
    painter.setBrush(QColor(WINDOW_BAR))
    painter.drawRoundedRect(bar, 10, 10)
    painter.drawRect(QRectF(bar.left(), bar.bottom() - 10, bar.width(), 10))

    for index, color in enumerate(("#f26b5f", "#f5bf4f", "#5fc46b")):
        painter.setBrush(QColor(color))
        painter.drawEllipse(
            QPointF(frame.left() + 20 + index * 19, bar.center().y()), 5.5, 5.5
        )

    # Lignes de texte et bloc d'image : la page qu'on est en train de lire.
    painter.setBrush(QColor(LINE_BG))
    left = frame.left() + 40
    top = frame.top() + 66
    widths = (0.48, 0.78, 0.72, 0.51, 0.72, 0.72)
    for index, ratio in enumerate(widths):
        y = top + index * 26
        painter.drawRoundedRect(
            QRectF(left, y, frame.width() * ratio * 0.92, 11), 5.5, 5.5
        )

    block = QRectF(
        frame.left() + frame.width() * 0.62,
        frame.top() + frame.height() * 0.47,
        frame.width() * 0.29,
        frame.height() * 0.28,
    )
    painter.setBrush(QColor(BLOCK_BG))
    painter.drawRoundedRect(block, 8, 8)


def blurred(image: QImage, radius: int) -> QImage:
    """Flou gaussien d'une image (ombre portée)."""
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(image))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    item.setGraphicsEffect(effect)
    scene.addItem(item)

    margin = radius * 2
    result = QImage(
        image.width() + margin * 2,
        image.height() + margin * 2,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(
        painter,
        QRectF(0, 0, result.width(), result.height()),
        QRectF(-margin, -margin, image.width(), image.height()),
    )
    painter.end()
    return result


def shadow_of(pixmap: QPixmap, radius: int = 12, alpha: int = 150) -> QImage:
    """Silhouette noire et floue de la bulle, pour l'ombre portée."""
    image = pixmap.toImage().convertToFormat(
        QImage.Format.Format_ARGB32_Premultiplied
    )
    mask = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    mask.fill(QColor(0, 0, 0, alpha))
    painter = QPainter(mask)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawImage(0, 0, image)
    painter.end()
    return blurred(mask, radius)


def place(
    scene: QImage,
    pixmap: QPixmap,
    margin_right: float = 30,
    margin_bottom: float = 30,
) -> None:
    """Pose la bulle en bas à droite, avec son ombre."""
    painter = QPainter(scene)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    shadow = shadow_of(pixmap)
    x = scene.width() - pixmap.width() - margin_right
    y = scene.height() - pixmap.height() - margin_bottom
    painter.drawImage(
        QPointF(
            x - (shadow.width() - pixmap.width()) / 2,
            y - (shadow.height() - pixmap.height()) / 2 + 4,
        ),
        shadow,
    )
    painter.drawPixmap(QPointF(x, y), pixmap)
    painter.end()


# ---------------------------------------------------------------------------
# Bulles
# ---------------------------------------------------------------------------
def build_overlay(config: pressvisual.Config) -> pressvisual.Overlay:
    overlay = pressvisual.Overlay(config)
    overlay.show()
    QApplication.processEvents()
    return overlay


def type_keys(overlay: pressvisual.Overlay, *keys: str) -> None:
    """Envoie des touches simples (une lettre donne son caractère)."""
    for key in keys:
        char = key if len(key) == 1 else ""
        overlay._on_key(KeyEvent(token=key, char=char))


def combo(overlay: pressvisual.Overlay, mods: tuple[str, ...], key: str) -> None:
    overlay._on_modifiers(list(mods))
    overlay._on_key(KeyEvent(token=key, char=None, mods=mods))
    overlay._on_modifiers([])


def fit(overlay: pressvisual.Overlay) -> QPixmap:
    """Capture la bulle à sa taille naturelle."""
    overlay.adjustSize()
    QApplication.processEvents()
    return overlay.grab()


def shot_standard(app: QApplication) -> QImage:
    """Bulle en cours d'utilisation : combinaison, appuis comptés, clic."""
    config = pressvisual.Config()
    config.row_animation = "none"
    config.validate()
    overlay = build_overlay(config)
    try:
        combo(overlay, ("ctrl", "shift"), "p")
        type_keys(overlay, "e", "e", "e")
        overlay._on_mouse(MouseEvent(kind="click", button="right"))
        QApplication.processEvents()
        bubble = fit(overlay)
    finally:
        overlay.hide()
    scene = backdrop(1000, 620)
    place(scene, bubble)
    return scene


def shot_masked(app: QApplication) -> QImage:
    """Mode masqué : les caractères saisis deviennent des points."""
    config = pressvisual.Config()
    config.concat_text = True
    config.row_animation = "none"
    config.validate()
    overlay = build_overlay(config)
    overlay._masked = True
    try:
        type_keys(overlay, "s", "e", "c", "r", "e", "t")
        QApplication.processEvents()
        bubble = fit(overlay)
    finally:
        overlay.hide()
    scene = backdrop(1000, 620)
    place(scene, bubble)
    return scene


def shot_keyboard(app: QApplication) -> QImage:
    """Mode clavier complet : Ctrl gauche et A allumés, clic et molette."""
    config = pressvisual.Config()
    config.display_mode = "keyboard"
    config.validate()
    overlay = build_overlay(config)
    try:
        overlay._keyboard.set_modifiers(["ctrl"])
        overlay._keyboard.set_modifier_sides(["ctrl_l"])
        overlay._keyboard.set_active(["a"])
        overlay._mouse.set_buttons(["left"])
        overlay._mouse.set_scroll("vertical", 1)
        QApplication.processEvents()
        bubble = fit(overlay)
    finally:
        overlay.hide()
    scene = backdrop(1280, 760)
    place(scene, bubble)
    return scene


def shot_settings(app: QApplication) -> QImage:
    """Fenêtre de personnalisation, onglet Affichage."""
    return _dialog_shot(tab=0, width=720)


def shot_key_editor(app: QApplication) -> QImage:
    """Onglet Touches : formes par défaut et exceptions par touche."""
    return _dialog_shot(
        tab=3, width=720, overrides={"A": "flower", "Entrée": "star"}
    )


def _dialog_shot(
    tab: int, width: int = 640, overrides: Optional[dict[str, str]] = None
) -> QImage:
    config = pressvisual.Config()
    if overrides:
        config.key_shapes = dict(overrides)
    config.validate()
    dialog = pressvisual.AppearanceDialog(config, _font_family(config))
    dialog.show()
    QApplication.processEvents()
    dialog.tabs.setCurrentIndex(tab)
    QApplication.processEvents()

    # Hauteur juste suffisante pour l'onglet : pas de cadre vide sous les
    # réglages, ni de barre de défilement.
    page = dialog.tabs.widget(tab)
    bar = dialog.tabs.tabBar()
    bar_height = bar.sizeHint().height() if bar is not None else 32
    dialog.tabs.setFixedHeight(page.widget().sizeHint().height() + bar_height + 12)
    dialog.resize(width, dialog.sizeHint().height())
    QApplication.processEvents()

    image = dialog.grab().toImage()
    dialog.hide()
    dialog.deleteLater()
    return image


def _font_family(config: pressvisual.Config) -> str:
    from pressvisual_app.appearance import _choose_font_family

    return _choose_font_family(config)


# ---------------------------------------------------------------------------
# GIF de démonstration
# ---------------------------------------------------------------------------
def shot_demo(app: QApplication, fps: int = 15) -> Optional[Path]:
    """Séquence animée : clavier complet, puis overplay standard."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print("ffmpeg introuvable : GIF ignoré")
        return None

    keyboard_config = pressvisual.Config()
    keyboard_config.display_mode = "keyboard"
    keyboard_config.validate()
    keyboard = build_overlay(keyboard_config)

    config = pressvisual.Config()
    config.validate()
    overlay = build_overlay(config)

    scene_width, scene_height = 960, 520
    base = backdrop(scene_width, scene_height)
    switch_at = 2.7

    def release_keys() -> None:
        keyboard._keyboard.set_modifiers([])
        keyboard._keyboard.set_modifier_sides([])
        keyboard._keyboard.set_active([])
        keyboard._mouse.set_buttons([])
        keyboard._mouse.clear_scroll()

    steps = [
        # Clavier complet : Ctrl gauche + C allumés, clic, molette.
        (0.30, lambda: keyboard._keyboard.set_modifiers(["ctrl"])),
        (0.30, lambda: keyboard._keyboard.set_modifier_sides(["ctrl_l"])),
        (0.55, lambda: keyboard._keyboard.set_active(["c"])),
        (1.00, lambda: keyboard._mouse.set_buttons(["left"])),
        (1.45, lambda: keyboard._mouse.set_scroll("vertical", 1)),
        (2.20, release_keys),
        # Overlay standard : frappe animée, appuis comptés, combinaison.
        (switch_at + 0.10, lambda: type_keys(overlay, "b")),
        (switch_at + 0.40, lambda: type_keys(overlay, "o")),
        (switch_at + 0.70, lambda: type_keys(overlay, "n")),
        (switch_at + 1.30, lambda: type_keys(overlay, "j")),
        (switch_at + 1.55, lambda: type_keys(overlay, "j")),
        (switch_at + 1.80, lambda: type_keys(overlay, "j")),
        (switch_at + 2.40, lambda: combo(overlay, ("ctrl",), "c")),
        (switch_at + 2.95, lambda: overlay._on_mouse(MouseEvent(kind="click", button="left"))),
    ]
    duration = 6.6
    frames: list[QImage] = []

    with tempfile.TemporaryDirectory() as workdir:
        folder = Path(workdir)
        pending = list(steps)
        start = time.monotonic()
        index = 0
        while True:
            now = time.monotonic() - start
            if now > duration:
                break
            while pending and pending[0][0] <= now:
                pending.pop(0)[1]()
                QApplication.processEvents()
            frame = base.copy()
            source = keyboard if now < switch_at else overlay
            place(frame, fit(source), margin_right=24, margin_bottom=24)
            frame.save(str(folder / f"frame-{index:04d}.png"))
            frames.append(frame)
            index += 1
            target = index / fps
            delay = target - (time.monotonic() - start)
            if delay > 0:
                time.sleep(delay)
        for widget in (keyboard, overlay):
            widget.hide()
            widget.deleteLater()
        QApplication.processEvents()

        target_path = IMAGES / "demo.gif"
        subprocess.run(
            [
                ffmpeg, "-v", "error", "-y",
                "-framerate", str(fps),
                "-i", str(folder / "frame-%04d.png"),
                "-vf", "split[a][b];[a]palettegen[p];[b][p]paletteuse",
                "-loop", "0", str(target_path),
            ],
            check=True,
        )
    print(f"demo.gif : {len(frames)} images")
    return target_path


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
SHOTS: dict[str, tuple[str, Callable[..., object]]] = {
    "standard": ("overlay-standard.png", shot_standard),
    "masked": ("overlay-masked.png", shot_masked),
    "keyboard": ("overlay-keyboard.png", shot_keyboard),
    "settings": ("settings.png", shot_settings),
    "key-editor": ("key-editor.png", shot_key_editor),
    "demo": ("demo.gif", shot_demo),
}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(SHOTS),
        help="ne produire que ces images (répétable)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    wanted = args.only or list(SHOTS)

    app = QApplication.instance() or QApplication([])
    IMAGES.mkdir(parents=True, exist_ok=True)

    for name in wanted:
        filename, builder = SHOTS[name]
        result = builder(app)
        if result is None:
            continue
        path = IMAGES / filename
        if isinstance(result, QImage):
            result.save(str(path))
        print(f"{path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
