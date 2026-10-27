"""Tracés des formes de touches du clavier et des pastilles de l'overlay.

Chaque forme est un ``QPainterPath`` ajusté au rectangle de la touche, pour
que le dessin, l'aperçu et l'éditeur partagent la même géométrie. Les formes
sont volontairement simples : elles doivent rester lisibles à la taille d'une
touche et laisser la place à son étiquette.

Une touche large (une pastille de la bulle, la barre d'espace) ne peut pas
recevoir la même silhouette qu'une touche carrée : une fleur ou une étoile
inscrite dans un rectangle très allongé n'aurait plus de place au centre pour
le texte. Ces formes deviennent alors une bande festonnée, qui garde le même
dessin d'un bout à l'autre et laisse l'étiquette au milieu.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
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

#: Allongement au-delà duquel une forme radiale devient une bande : une
#: pastille de bulle est deux à quatre fois plus large que haute.
BANNER_ASPECT = 1.6
#: Profondeur des festons d'une bande, en fraction de sa hauteur : une
#: pastille de bulle est basse, ses festons doivent rester modestes pour
#: laisser la place à l'étiquette.
BANNER_DEPTH = 0.17
#: Longueur d'un feston, en hauteurs : plus la bande est large, plus elle en
#: porte, pour garder le même rythme qu'une touche carrée.
BANNER_TOOTH = 2.2
#: Nombre de festons d'une bande.
BANNER_MIN_LOBES = 6
BANNER_MAX_LOBES = 16
#: Points d'échantillonnage du contour d'une bande.
BANNER_SAMPLES = 320


def _aspect(rect: QRectF) -> float:
    """Allongement du rectangle (1 = carré, 2 = deux fois plus large)."""
    return rect.width() / max(1.0, rect.height())


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


def _add_hexagon(path: QPainterPath, rect: QRectF) -> None:
    """Bande à pointes : les coins sont coupés en biais."""
    cut = min(rect.height() / 2.0, rect.width() / 3.0)
    center_y = rect.center().y()
    path.moveTo(rect.left(), center_y)
    path.lineTo(rect.left() + cut, rect.top())
    path.lineTo(rect.right() - cut, rect.top())
    path.lineTo(rect.right(), center_y)
    path.lineTo(rect.right() - cut, rect.bottom())
    path.lineTo(rect.left() + cut, rect.bottom())
    path.closeSubpath()


def _add_diamond(path: QPainterPath, rect: QRectF) -> None:
    """Losange : les quatre coins du rectangle deviennent des pointes."""
    path.moveTo(rect.center().x(), rect.top())
    path.lineTo(rect.right(), rect.center().y())
    path.lineTo(rect.center().x(), rect.bottom())
    path.lineTo(rect.left(), rect.center().y())
    path.closeSubpath()


def _rounded_outline(
    width: float, height: float, radius: float, progress: float
) -> tuple[QPointF, QPointF]:
    """Point et normale sortante du contour d'un rectangle arrondi.

    ``progress`` vaut 0 au début du côté haut et parcourt le contour dans le
    sens des aiguilles d'une montre ; le point est centré sur l'origine.
    """
    straight_w = max(0.0, width - 2.0 * radius)
    straight_h = max(0.0, height - 2.0 * radius)
    arc = math.pi * radius / 2.0
    total = 2.0 * straight_w + 2.0 * straight_h + 4.0 * arc
    if total <= 0.0:
        return QPointF(0.0, 0.0), QPointF(0.0, -1.0)
    left, top = -width / 2.0, -height / 2.0
    right, bottom = width / 2.0, height / 2.0

    # Côtés et coins, dans l'ordre du contour (sens des aiguilles d'une
    # montre en coordonnées écran, où l'axe y descend).
    edges = (
        (straight_w, left + radius, top, 1.0, 0.0, QPointF(0.0, -1.0)),
        (straight_h, right, top + radius, 0.0, 1.0, QPointF(1.0, 0.0)),
        (straight_w, right - radius, bottom, -1.0, 0.0, QPointF(0.0, 1.0)),
        (straight_h, left, bottom - radius, 0.0, -1.0, QPointF(-1.0, 0.0)),
    )
    corners = (
        (right - radius, top + radius, -math.pi / 2.0),
        (right - radius, bottom - radius, 0.0),
        (left + radius, bottom - radius, math.pi / 2.0),
        (left + radius, top + radius, math.pi),
    )

    distance = (progress % 1.0) * total
    for index, (length, start_x, start_y, dx, dy, normal) in enumerate(edges):
        if distance <= length:
            return QPointF(start_x + dx * distance, start_y + dy * distance), normal
        distance -= length
        centre_x, centre_y, angle = corners[index]
        if distance <= arc:
            angle += (distance / arc) * (math.pi / 2.0)
            return (
                QPointF(
                    centre_x + radius * math.cos(angle),
                    centre_y + radius * math.sin(angle),
                ),
                QPointF(math.cos(angle), math.sin(angle)),
            )
        distance -= arc
    return QPointF(left + radius, top), QPointF(0.0, -1.0)


def _add_banner(path: QPainterPath, rect: QRectF, sharp: bool) -> None:
    """Bande festonnée : contour ondulé autour d'un rectangle arrondi.

    Les festons ne sortent jamais du rectangle de base, qui garde toute la
    place du texte : une étiquette n'est donc jamais coupée.
    """
    depth = rect.height() * BANNER_DEPTH
    inner = QRectF(rect).adjusted(depth, depth, -depth, -depth)
    if inner.width() <= 2.0 or inner.height() <= 2.0:
        inner = QRectF(rect)
        depth = 0.0
    radius = min(inner.width(), inner.height()) * 0.42
    lobes = int(round(rect.width() / (BANNER_TOOTH * max(1.0, rect.height()))))
    lobes = max(BANNER_MIN_LOBES, min(BANNER_MAX_LOBES, lobes))
    center = rect.center()

    for index in range(BANNER_SAMPLES):
        progress = index / BANNER_SAMPLES
        point, normal = _rounded_outline(
            inner.width(), inner.height(), radius, progress
        )
        wave = math.cos(2.0 * math.pi * lobes * progress)
        # Une fleur arrondit ses pétales, une étoile les pointe : la base du
        # feston reste la même dans les deux cas.
        if sharp:
            # Onde triangulaire : des pointes franches plutôt que des bosses.
            bump = 1.0 - 2.0 * abs((lobes * progress + 0.5) % 1.0 - 0.5)
        else:
            bump = 0.5 + 0.5 * wave
        x = center.x() + point.x() + normal.x() * depth * bump
        y = center.y() + point.y() + normal.y() * depth * bump
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
    wide = _aspect(inner) > BANNER_ASPECT

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
        _add_hexagon(path, inner)
    elif name == "diamond":
        # Un losange étiré n'aurait plus de place au centre : ses pointes
        # deviennent celles d'une bande.
        if wide:
            _add_hexagon(path, inner)
        else:
            _add_diamond(path, inner)
    elif name == "flower":
        if wide:
            _add_banner(path, inner, sharp=False)
        else:
            _add_flower(path, inner)
    elif name == "star":
        if wide:
            _add_banner(path, inner, sharp=True)
        else:
            _add_star(path, inner)
    else:
        radius = max(3.0, min(6.0, inner.height() * 0.2))
        path.addRoundedRect(inner, radius, radius)
    return path
