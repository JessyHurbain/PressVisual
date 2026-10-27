"""Tracés des formes de touches du clavier complet.

Chaque forme est un ``QPainterPath`` ajusté au rectangle de la touche, pour
que le dessin, l'aperçu et l'éditeur partagent la même géométrie. Les formes
sont volontairement simples : elles doivent rester lisibles à la taille d'une
touche et laisser la place à son étiquette.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath

from .keymap import KEY_SHAPES

#: Marge intérieure, pour que les formes ne touchent pas le vide entre les
#: touches et ne soient pas coupées par le bord du rectangle.
INSET = 1.0
#: Nombre de sommets d'une fleur : une forme lisible même petite.
FLOWER_PETALS = 6
#: Creux entre deux pétales (0 = cercle, 1 = pétales très marqués).
FLOWER_DEPTH = 0.30
#: Branches d'une étoile.
STAR_BRANCHES = 5
#: Rayon intérieur d'une étoile, en proportion du rayon extérieur.
STAR_INNER = 0.42
#: Points d'échantillonnage des formes courbes (fleur, étoile).
SAMPLES = 96


def _add_flower(path: QPainterPath, rect: QRectF) -> None:
    """Fleur à pétales, inscrite dans le rectangle."""
    center = rect.center()
    rx = rect.width() / 2.0
    ry = rect.height() / 2.0
    for index in range(SAMPLES):
        angle = 2.0 * math.pi * index / SAMPLES
        radius = 1.0 - FLOWER_DEPTH + FLOWER_DEPTH * math.cos(
            FLOWER_PETALS * angle
        )
        # Le creux est exagéré entre deux pétales : le contour se lit mieux
        # qu'une simple ondulation.
        radius = radius - FLOWER_DEPTH * 0.35 * max(
            0.0, -math.cos(FLOWER_PETALS * angle)
        )
        x = center.x() + rx * radius * math.cos(angle)
        y = center.y() + ry * radius * math.sin(angle)
        if index == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()


def _add_star(path: QPainterPath, rect: QRectF) -> None:
    """Étoile à branches, inscrite dans le rectangle."""
    center = rect.center()
    rx = rect.width() / 2.0
    ry = rect.height() / 2.0
    points = STAR_BRANCHES * 2
    for index in range(points):
        angle = -math.pi / 2.0 + math.pi * index / STAR_BRANCHES
        radius = 1.0 if index % 2 == 0 else STAR_INNER
        x = center.x() + rx * radius * math.cos(angle)
        y = center.y() + ry * radius * math.sin(angle)
        if index == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()


def key_shape_path(shape: str, rect: QRectF) -> QPainterPath:
    """Chemin de la touche ``shape`` dans ``rect``.

    Une forme inconnue retombe sur la forme arrondie, comme la configuration.
    """
    name = shape if shape in KEY_SHAPES else "rounded"
    inner = QRectF(rect).adjusted(INSET, INSET, -INSET, -INSET)
    if inner.width() <= 2.0 or inner.height() <= 2.0:
        inner = QRectF(rect)

    path = QPainterPath()
    if name == "square":
        radius = min(2.0, min(inner.width(), inner.height()) / 4.0)
        path.addRoundedRect(inner, radius, radius)
    elif name == "circle":
        path.addEllipse(inner)
    elif name == "pill":
        radius = min(inner.width(), inner.height()) / 2.0
        path.addRoundedRect(inner, radius, radius)
    elif name == "hexagon":
        cut = min(inner.height() / 2.0, inner.width() / 3.0)
        center_y = inner.center().y()
        path.moveTo(inner.left(), center_y)
        path.lineTo(inner.left() + cut, inner.top())
        path.lineTo(inner.right() - cut, inner.top())
        path.lineTo(inner.right(), center_y)
        path.lineTo(inner.right() - cut, inner.bottom())
        path.lineTo(inner.left() + cut, inner.bottom())
        path.closeSubpath()
    elif name == "diamond":
        path.moveTo(inner.center().x(), inner.top())
        path.lineTo(inner.right(), inner.center().y())
        path.lineTo(inner.center().x(), inner.bottom())
        path.lineTo(inner.left(), inner.center().y())
        path.closeSubpath()
    elif name == "flower":
        _add_flower(path, inner)
    elif name == "star":
        _add_star(path, inner)
    else:
        radius = max(3.0, min(6.0, inner.height() * 0.2))
        path.addRoundedRect(inner, radius, radius)
    return path
