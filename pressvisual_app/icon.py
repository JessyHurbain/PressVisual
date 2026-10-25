"""Icône de l'application, dessinée avec QPainter."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap

# ---------------------------------------------------------------------------
# Icône et menu de notification
# ---------------------------------------------------------------------------


def _icon_pixmap(size: int) -> QPixmap:
    """Dessine l'icône de l'application (touche clavier stylisée)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    rect = QRectF(size * 0.02, size * 0.02, size * 0.96, size * 0.96)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor(91, 155, 255))
    gradient.setColorAt(1.0, QColor(46, 99, 232))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(rect, size * 0.26, size * 0.26)

    painter.setBrush(QColor(255, 255, 255, 240))
    key_width = size * 0.16
    key_height = size * 0.12
    gap = size * 0.07
    total = 3 * key_width + 2 * gap
    start_x = (size - total) / 2.0
    top_y = size * 0.34
    radius = size * 0.03
    for index in range(3):
        painter.drawRoundedRect(
            QRectF(start_x + index * (key_width + gap), top_y, key_width, key_height),
            radius,
            radius,
        )
    painter.drawRoundedRect(
        QRectF(size * 0.28, size * 0.57, size * 0.44, size * 0.11),
        radius,
        radius,
    )
    painter.end()
    return pixmap


def build_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_icon_pixmap(size))
    return icon

