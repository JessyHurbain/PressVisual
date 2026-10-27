"""Souris compacte affichée à côté du clavier complet.

La souris est dessinée comme un schéma vu de dessus : bouton gauche, bouton
droit, molette et deux boutons latéraux. Un bouton s'allume tant qu'il est
enfoncé ; la molette s'allume brièvement en indiquant le sens du défilement,
puisqu'un cran de molette n'a pas de relâchement.

Trois dessins sont proposés (``mouse_style``) : « classic » avec un fond plein
et des boutons séparés, « outline » en traits seuls, et « minimal » où la
souris reste une silhouette et où seuls les gestes apparaissent.

La vue ne dessine que la souris : c'est la fenêtre de l'overlay qui peint le
panneau, les coins arrondis et l'opacité.
"""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .keymap import MOUSE_STYLES
from .theme import Palette, _with_alpha

#: Boutons suivis, dans l'ordre de la souris.
MOUSE_BUTTONS: tuple[str, ...] = ("left", "right", "middle", "back", "forward")

#: Dessin utilisé quand la configuration n'en donne pas (ou un inconnu).
DEFAULT_MOUSE_STYLE = "classic"


def _normalize_style(style: str) -> str:
    """Nom de dessin valide, ou « classic »."""
    value = str(style or "").strip().lower()
    return value if value in MOUSE_STYLES else DEFAULT_MOUSE_STYLE

#: Durée d'allumage du défilement (un cran de molette n'est pas relâché).
MOUSE_SCROLL_FLASH_MS = 320

#: Largeur de la souris, en proportion de sa hauteur.
WIDTH_RATIO = 0.58


class MouseView(QWidget):
    """Schéma de souris dont s'allument les boutons et le défilement."""

    def __init__(
        self,
        palette: Palette,
        parent: Optional[QWidget] = None,
        style: str = DEFAULT_MOUSE_STYLE,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._style = _normalize_style(style)
        self._buttons: frozenset[str] = frozenset()
        self._scroll: Optional[tuple[str, int]] = None
        self._height = 150.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_size()

    # ------------------------------------------------------------------
    # État
    # ------------------------------------------------------------------
    @property
    def style(self) -> str:
        """Dessin courant (``classic``, ``outline`` ou ``minimal``)."""
        return self._style

    def set_style(self, style: str) -> None:
        """Change le dessin ; l'état allumé est conservé."""
        value = _normalize_style(style)
        if value != self._style:
            self._style = value
            self.update()

    @property
    def scroll(self) -> Optional[tuple[str, int]]:
        """Dernier défilement affiché : ``(axe, sens)`` ou ``None``."""
        return self._scroll

    def active_buttons(self) -> list[str]:
        """Boutons actuellement allumés, dans l'ordre de la souris."""
        return [name for name in MOUSE_BUTTONS if name in self._buttons]

    def set_buttons(self, buttons: Iterable[str]) -> None:
        """Allume les boutons enfoncés (les autres sont éteints)."""
        pressed = frozenset(name for name in buttons if name in MOUSE_BUTTONS)
        if pressed != self._buttons:
            self._buttons = pressed
            self.update()

    def set_scroll(self, axis: str, direction: int) -> None:
        """Affiche le sens d'un cran de molette."""
        axis = "horizontal" if axis == "horizontal" else "vertical"
        state = (axis, 1 if direction >= 0 else -1)
        if state != self._scroll:
            self._scroll = state
            self.update()

    def clear_scroll(self) -> None:
        """Éteint l'indicateur de défilement."""
        if self._scroll is not None:
            self._scroll = None
            self.update()

    def clear(self) -> None:
        """Éteint les boutons et le défilement."""
        self._buttons = frozenset()
        self._scroll = None
        self.update()

    # ------------------------------------------------------------------
    # Dimensions
    # ------------------------------------------------------------------
    def set_height(self, height: float) -> None:
        """Aligne la souris sur la hauteur du clavier."""
        height = max(60.0, float(height))
        if height == self._height:
            return
        self._height = height
        self._apply_size()

    def _apply_size(self) -> None:
        self.setFixedSize(
            max(20, round(self._height * WIDTH_RATIO)), round(self._height)
        )
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        return QSize(
            max(20, round(self._height * WIDTH_RATIO)), round(self._height)
        )

    # ------------------------------------------------------------------
    # Peinture
    # ------------------------------------------------------------------
    def _paint_region(
        self,
        painter: QPainter,
        rect: QRectF,
        lit: bool,
        radius: Optional[float] = None,
    ) -> None:
        """Dessine une zone de la souris, allumée ou simplement contourée."""
        if rect.width() <= 1.0 or rect.height() <= 1.0:
            return
        corner = (
            radius
            if radius is not None
            else min(rect.width(), rect.height()) * 0.35
        )
        if lit:
            painter.setBrush(_with_alpha(self._palette.accent, 0.95))
            painter.setPen(QPen(_with_alpha(self._palette.accent_soft, 0.9), 1.0))
        elif self._style == "minimal":
            # Silhouette : rien tant que le bouton n'est pas enfoncé.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
        elif self._style == "outline":
            # Le corps n'étant pas rempli, les traits prennent la couleur du
            # texte du panneau : le texte des touches serait illisible sur le
            # fond sombre de la bulle.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_with_alpha(self._palette.text, 0.55), 1.0))
        else:
            painter.setBrush(
                _with_alpha(self._palette.key_text, 0.07)
                if self._palette.key_bg.lightness() > 128
                else Qt.BrushStyle.NoBrush
            )
            painter.setPen(QPen(_with_alpha(self._palette.key_text, 0.30), 1.0))
        painter.drawRoundedRect(rect, corner, corner)

    def _paint_scroll(
        self, painter: QPainter, wheel: QRectF, axis: str, direction: int
    ) -> None:
        """Triangle indiquant le sens du défilement, dans la molette allumée."""
        painter.setBrush(_with_alpha(self._palette.on_accent, 0.95))
        painter.setPen(Qt.PenStyle.NoPen)

        cx = wheel.center().x()
        cy = wheel.center().y()
        if axis == "vertical":
            size = wheel.width() * 0.34
            offset = wheel.height() * 0.30
            if direction > 0:
                points = (
                    QPointF(cx, cy - offset - size),
                    QPointF(cx - size * 0.85, cy - offset + size * 0.7),
                    QPointF(cx + size * 0.85, cy - offset + size * 0.7),
                )
            else:
                points = (
                    QPointF(cx, cy + offset + size),
                    QPointF(cx - size * 0.85, cy + offset - size * 0.7),
                    QPointF(cx + size * 0.85, cy + offset - size * 0.7),
                )
        else:
            size = wheel.width() * 0.32
            if direction >= 0:
                points = (
                    QPointF(cx + size, cy),
                    QPointF(cx - size * 0.7, cy - size * 0.85),
                    QPointF(cx - size * 0.7, cy + size * 0.85),
                )
            else:
                points = (
                    QPointF(cx - size, cy),
                    QPointF(cx + size * 0.7, cy - size * 0.85),
                    QPointF(cx + size * 0.7, cy + size * 0.85),
                )

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        path.closeSubpath()
        painter.drawPath(path)

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = float(self.width())
        height = float(self.height())
        if width < 16.0 or height < 32.0:
            return

        body = QRectF(1.0, 1.0, width - 2.0, height - 2.0)
        corner = min(body.width(), body.height()) * 0.46
        outline = QPainterPath()
        outline.addRoundedRect(body, corner, corner)
        if self._style != "outline":
            # « minimal » se fond dans le panneau : une silhouette translucide,
            # où seuls les gestes ressortent.
            fill = (
                _with_alpha(self._palette.text, 0.10)
                if self._style == "minimal"
                else _with_alpha(self._palette.key_bg, 0.9)
            )
            painter.fillPath(outline, fill)
        painter.setClipPath(outline)

        band = body.height() * 0.32
        wheel_width = max(9.0, body.width() * 0.22)
        center_x = body.center().x()
        gap = body.width() * 0.035
        wheel = QRectF(
            center_x - wheel_width / 2.0,
            body.top() + band * 0.10,
            wheel_width,
            band * 0.90,
        )
        left_button = QRectF(
            body.left(),
            body.top(),
            max(2.0, wheel.left() - gap - body.left()),
            band,
        )
        right_button = QRectF(
            wheel.right() + gap,
            body.top(),
            max(2.0, body.right() - (wheel.right() + gap)),
            band,
        )

        side_width = body.width() * 0.22
        side_height = max(5.0, body.height() * 0.08)
        side_x = body.left() + body.width() * 0.05
        side_y = body.top() + band + body.height() * 0.05
        back_button = QRectF(side_x, side_y, side_width, side_height)
        forward_button = QRectF(
            side_x, side_y + side_height * 1.7, side_width, side_height
        )

        self._paint_region(painter, left_button, "left" in self._buttons)
        self._paint_region(painter, right_button, "right" in self._buttons)
        self._paint_region(painter, back_button, "back" in self._buttons)
        self._paint_region(painter, forward_button, "forward" in self._buttons)

        wheel_lit = "middle" in self._buttons or self._scroll is not None
        self._paint_region(painter, wheel, wheel_lit, radius=wheel_width / 2.0)
        if self._style == "minimal" and not wheel_lit:
            # La molette reste dessinée au repos : c'est elle qui fait lire la
            # silhouette comme une souris.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(_with_alpha(self._palette.text, 0.40), 1.0))
            painter.drawRoundedRect(wheel, wheel_width / 2.0, wheel_width / 2.0)
        if self._scroll is not None:
            axis, direction = self._scroll
            self._paint_scroll(painter, wheel, axis, direction)

        painter.setClipping(False)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self._style == "outline":
            border = _with_alpha(self._palette.text, 0.60)
        elif self._style == "minimal":
            border = _with_alpha(self._palette.text, 0.40)
        else:
            border = _with_alpha(self._palette.key_text, 0.30)
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(outline)
