"""Pastille affichée près du curseur pour un clic ou un défilement.

Elle sert au réglage « suivi de la souris » : au lieu d'empiler les clics dans
la bulle, l'événement s'affiche à côté du pointeur, là où le geste se produit.
La fenêtre ne prend ni le focus ni les clics : elle ne gêne jamais l'action.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QWidget

from .theme import Palette, _with_alpha

#: Durée d'affichage (ms) : un cran de molette n'a pas de relâchement.
CURSOR_BADGE_MS = 700
#: Décalage par rapport au pointeur (px), pour ne pas masquer son extrémité.
CURSOR_OFFSET = 18
#: Marges du texte dans la pastille (px).
PADDING_H = 11
PADDING_V = 6


class CursorBadge(QWidget):
    """Petite pastille près du pointeur, transparente aux clics et sans focus."""

    def __init__(self, palette: Palette, font: Optional[QFont] = None) -> None:
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
        radius = min(8.0, rect.height() / 2.0)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, _with_alpha(self._palette.accent, 0.94))
        painter.setPen(QPen(_with_alpha(self._palette.accent_soft, 0.9), 1.0))
        painter.drawPath(path)

        painter.setFont(self._font)
        painter.setPen(_with_alpha(self._palette.on_accent, 0.98))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
