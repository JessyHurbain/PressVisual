"""Pastille affichée près du curseur pour un clic ou un défilement.

Elle sert au réglage « suivi de la souris » : au lieu d'empiler les clics dans
la bulle, l'événement s'affiche à côté du pointeur, là où le geste se produit.
La fenêtre ne prend ni le focus ni les clics : elle ne gêne jamais l'action.

Trois dessins sont proposés (``cursor_style``) : « classic » (pastille pleine
de la couleur d'accent), « outline » (fond du panneau et trait d'accent) et
« keycap » (une touche de clavier en miniature, avec son arête).
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QWidget

from .keymap import CURSOR_STYLES
from .theme import Palette, _blend, _with_alpha

#: Durée d'affichage (ms) : un cran de molette n'a pas de relâchement.
CURSOR_BADGE_MS = 700

#: Dessin utilisé quand la configuration n'en donne pas (ou un inconnu).
DEFAULT_CURSOR_STYLE = "classic"
#: Décalage par rapport au pointeur (px), pour ne pas masquer son extrémité.
CURSOR_OFFSET = 18
#: Marges du texte dans la pastille (px).
PADDING_H = 11
PADDING_V = 6


def _normalize_style(style: str) -> str:
    """Nom de dessin valide, ou « classic »."""
    value = str(style or "").strip().lower()
    return value if value in CURSOR_STYLES else DEFAULT_CURSOR_STYLE


class CursorBadge(QWidget):
    """Petite pastille près du pointeur, transparente aux clics et sans focus."""

    def __init__(
        self,
        palette: Palette,
        font: Optional[QFont] = None,
        style: str = DEFAULT_CURSOR_STYLE,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._palette = palette
        self._style = _normalize_style(style)
        self._font = QFont(font) if font is not None else QFont()
        self._font.setWeight(QFont.Weight.DemiBold)
        self._label = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_badge)
        self.hide()

    # ------------------------------------------------------------------
    @property
    def label(self) -> str:
        """Texte actuellement affiché (tests, débogage)."""
        return self._label

    @property
    def style(self) -> str:
        """Dessin courant (``classic``, ``outline`` ou ``keycap``)."""
        return self._style

    def set_style(self, style: str) -> None:
        """Change le dessin ; le texte affiché est conservé."""
        value = _normalize_style(style)
        if value != self._style:
            self._style = value
            if self._label:
                self._resize_to_label()
            self.update()

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_font(self, font: QFont) -> None:
        self._font = QFont(font)
        self._font.setWeight(QFont.Weight.DemiBold)
        if self._label:
            self._resize_to_label()
        self.update()

    def show_label(self, text: str) -> None:
        """Affiche ``text`` à côté du pointeur, puis l'efface après un délai."""
        self._label = text
        self._resize_to_label()
        self._move_next_to_cursor()
        self.show()
        self._timer.start(CURSOR_BADGE_MS)
        self.update()

    def hide_badge(self) -> None:
        """Efface la pastille et arrête le minuteur."""
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    def _resize_to_label(self) -> None:
        metrics = QFontMetrics(self._font)
        width = metrics.horizontalAdvance(self._label) + 2 * PADDING_H
        height = max(metrics.height() + 2 * PADDING_V, 24)
        self.resize(int(width), int(height))

    def _move_next_to_cursor(self) -> None:
        """Place la pastille sous le pointeur, en restant sur l'écran.

        La position vient de Qt (``QCursor``) et non du clic capturé : les
        coordonnées de ``pynput`` sont en pixels physiques, celles de Qt en
        pixels logiques, et les deux diffèrent sur un écran mis à l'échelle.
        """
        cursor = QCursor.pos()
        position = cursor + QPoint(CURSOR_OFFSET, CURSOR_OFFSET)
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = min(position.x(), available.right() - self.width() + 1)
            y = min(position.y(), available.bottom() - self.height() + 1)
            position = QPoint(max(available.left(), x), max(available.top(), y))
        self.move(position)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._style == "keycap":
            text_rect = self._paint_keycap(painter, rect)
            color = self._palette.key_text
        elif self._style == "outline":
            text_rect = self._paint_outline(painter, rect)
            color = self._palette.text
        else:
            text_rect = self._paint_pill(painter, rect)
            color = self._palette.on_accent

        painter.setFont(self._font)
        painter.setPen(_with_alpha(color, 0.98))
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignCenter, self._label
        )

    # ------------------------------------------------------------------
    def _paint_pill(self, painter: QPainter, rect: QRectF) -> QRectF:
        """Pastille pleine de la couleur d'accent."""
        radius = min(8.0, rect.height() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, _with_alpha(self._palette.accent, 0.94))
        painter.setPen(QPen(_with_alpha(self._palette.accent_soft, 0.9), 1.0))
        painter.drawPath(path)
        return rect

    def _paint_outline(self, painter: QPainter, rect: QRectF) -> QRectF:
        """Fond du panneau et trait d'accent : la version « contour »."""
        radius = min(8.0, rect.height() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, _with_alpha(self._palette.panel_bottom, 0.94))
        painter.setPen(QPen(_with_alpha(self._palette.accent, 0.95), 1.4))
        painter.drawPath(path)
        return rect

    def _paint_keycap(self, painter: QPainter, rect: QRectF) -> QRectF:
        """Touche de clavier en miniature, avec son arête plus sombre.

        Renvoie le rectangle du capuchon : le texte se centre dessus, pas sur
        l'arête.
        """
        edge = min(3.0, rect.height() * 0.16)
        radius = min(6.0, rect.height() / 2.0)
        base = QPainterPath()
        base.addRoundedRect(rect, radius, radius)
        shade = _blend(self._palette.key_bg, QColor(0, 0, 0), 0.45)
        painter.fillPath(base, _with_alpha(shade, 0.98))

        cap = QRectF(rect.left(), rect.top(), rect.width(), rect.height() - edge)
        cap_radius = min(6.0, cap.height() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(cap, cap_radius, cap_radius)
        painter.fillPath(path, _with_alpha(self._palette.key_bg, 0.98))
        painter.setPen(QPen(_with_alpha(self._palette.key_text, 0.16), 1.0))
        painter.drawPath(path)
        return cap
