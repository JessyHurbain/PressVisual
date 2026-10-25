"""Pastilles et lignes de badges affichées dans l'overlay."""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from .theme import Palette, _with_alpha

class Badge(QWidget):
    """Petite pastille arrondie affichant une touche, un modificateur, etc.

    Types disponibles :
      * ``key``    : touche principale (fond clair, texte sombre) ;
      * ``mod``    : modificateur (fond translucide, texte clair) ;
      * ``plus``   : séparateur « + » ;
      * ``mouse``  : clic / molette (accent bleu) ;
      * ``text``   : texte saisi en continu (sans fond) ;
      * ``status`` : message d'état (accent clair).
    """

    HEIGHT_PADDING = 12
    HORIZONTAL_PADDING = 11

    def __init__(
        self,
        label: str,
        kind: str,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._kind = kind
        self._font = QFont(font)
        self._metrics = QFontMetrics(self._font)
        self._palette = palette
        self._alpha = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------
    def set_alpha(self, alpha: float) -> None:
        alpha = max(0.0, min(1.0, alpha))
        if abs(alpha - self._alpha) > 0.001:
            self._alpha = alpha
            self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        text_width = self._metrics.horizontalAdvance(self._label)
        height = max(self._metrics.height() + self.HEIGHT_PADDING, 30)
        if self._kind == "plus":
            return QSize(text_width + 8, height)
        if self._kind == "text":
            return QSize(text_width + 2, height)
        if self._kind == "status":
            return QSize(text_width + 16, height)
        if self._kind == "mouse":
            return QSize(12 + 6 + 7 + text_width + 12, height)
        return QSize(text_width + 2 * self.HORIZONTAL_PADDING, height)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)

        alpha = self._alpha
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(9.0, rect.height() / 2.0)

        if self._kind == "plus":
            painter.setPen(_with_alpha(self._palette.muted, alpha))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
            return

        if self._kind == "text":
            painter.setPen(_with_alpha(self._palette.text, alpha))
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._label,
            )
            return

        if self._kind == "status":
            painter.setPen(_with_alpha(self._palette.accent_soft, alpha))
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._label,
            )
            return

        if self._kind == "mouse":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_with_alpha(self._palette.accent, alpha))
            painter.drawRoundedRect(rect, radius, radius)

            dot_size = 6.0
            dot_x = 12.0
            dot_y = (rect.height() - dot_size) / 2.0
            painter.setBrush(_with_alpha(self._palette.on_accent, alpha))
            painter.drawEllipse(QRectF(dot_x, dot_y, dot_size, dot_size))
            painter.setPen(_with_alpha(self._palette.on_accent, alpha))
            painter.drawText(
                QRectF(dot_x + dot_size + 7, 0, rect.width() - dot_x - dot_size - 7, rect.height()),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._label,
            )
            return

        if self._kind == "mod":
            painter.setBrush(_with_alpha(self._palette.mod_bg, alpha))
            painter.setPen(QPen(_with_alpha(self._palette.mod_border, alpha), 1.0))
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(_with_alpha(self._palette.text, alpha))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
            return

        # Touche principale : pastille claire, texte sombre.
        painter.setBrush(_with_alpha(self._palette.key_bg, alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(_with_alpha(self._palette.key_text, alpha))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)


class KeyRow(QWidget):
    """Une ligne de badges (une frappe ou une combinaison)."""

    def __init__(
        self,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._font = QFont(font)
        self._palette = palette
        self._items: list[tuple[str, str]] = []
        self._badges: list[Badge] = []
        self._alpha = 1.0
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # ------------------------------------------------------------------
    def set_items(self, items: Iterable[tuple[str, str]]) -> None:
        """Remplace le contenu de la ligne par ``[(libellé, type), ...]``."""
        self._items = list(items)
        self._rebuild()

    # ------------------------------------------------------------------
    def set_font(self, font: QFont) -> None:
        """Change la police de la ligne et recrée ses badges."""
        self._font = QFont(font)
        self._rebuild()

    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        for badge in self._badges:
            self._layout.removeWidget(badge)
            badge.setParent(None)
            badge.deleteLater()
        self._badges.clear()

        for label, kind in self._items:
            badge = Badge(label, kind, self._font, self._palette, parent=self)
            badge.set_alpha(self._alpha)
            self._layout.addWidget(badge)
            self._badges.append(badge)

        self.updateGeometry()
        self.update()

    def set_alpha(self, alpha: float) -> None:
        self._alpha = alpha
        for badge in self._badges:
            badge.set_alpha(alpha)

