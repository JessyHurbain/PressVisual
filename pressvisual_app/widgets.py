"""Pastilles et lignes de badges affichées dans l'overlay."""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from .shapes import key_shape_path
from .theme import Palette, _with_alpha


class Badge(QWidget):
    """Petite pastille affichant une touche, un modificateur, etc.

    Les touches prennent la forme choisie dans l'éditeur ; les autres genres
    gardent la pastille arrondie.

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
    #: Place horizontale supplémentaire que réclame chaque forme, en fraction
    #: de la hauteur de la pastille : une étoile ou un losange laissent moins
    #: de place à l'étiquette qu'un rectangle, il faut donc élargir le badge.
    SHAPE_ROOM: dict[str, float] = {
        "square": 0.12,
        "pill": 0.06,
        "hexagon": 0.28,
        "circle": 0.34,
        "flower": 0.34,
        "star": 0.46,
        "diamond": 0.68,
    }

    def __init__(
        self,
        label: str,
        kind: str,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
        shape: str = "rounded",
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._kind = kind
        self._font = QFont(font)
        self._metrics = QFontMetrics(self._font)
        self._palette = palette
        self._alpha = 1.0
        #: Avancement de l'apparition (0 = invisible) et échelle de « zoom ».
        self._appear = 1.0
        self._zoom = 1.0
        # Seules les touches prennent une forme : un clic ou un texte saisi
        # restent des pastilles, comme avant.
        self._shape = shape if kind in ("key", "mod") else "rounded"
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------
    @property
    def shape(self) -> str:
        """Forme de la pastille (``rounded`` pour tout ce qui n'est pas touche)."""
        return self._shape

    def set_alpha(self, alpha: float) -> None:
        alpha = max(0.0, min(1.0, alpha))
        if abs(alpha - self._alpha) > 0.001:
            self._alpha = alpha
            self.update()

    def set_appear(self, appear: float) -> None:
        """Opacité d'apparition de la pastille (0 = transparente)."""
        appear = max(0.0, min(1.0, float(appear)))
        if abs(appear - self._appear) > 0.001:
            self._appear = appear
            self.update()

    def set_zoom(self, zoom: float) -> None:
        """Échelle du contenu, pour l'animation « zoom » (1 = taille normale)."""
        zoom = max(0.1, min(1.5, float(zoom)))
        if abs(zoom - self._zoom) > 0.001:
            self._zoom = zoom
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
        if self._kind == "count":
            return QSize(text_width + 6, height)
        if self._kind == "mouse":
            return QSize(12 + 6 + 7 + text_width + 12, height)
        width = text_width + 2 * self.HORIZONTAL_PADDING
        width += int(round(self.SHAPE_ROOM.get(self._shape, 0.0) * height))
        return QSize(width, height)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)

        # L'animation d'apparition module l'opacité et, pour « zoom », la
        # taille du contenu : la place réservée dans la ligne ne bouge pas.
        alpha = self._alpha * self._appear
        if self._zoom != 1.0:
            center = QRectF(self.rect()).center()
            painter.translate(center)
            painter.scale(self._zoom, self._zoom)
            painter.translate(-center)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(9.0, rect.height() / 2.0)

        if self._kind == "plus":
            painter.setPen(_with_alpha(self._palette.muted, alpha))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
            return

        if self._kind == "count":
            # « ×2 » : un appui de plus sur la même touche, pas un nouveau
            # badge — le compteur reste discret à côté de la pastille.
            painter.setPen(_with_alpha(self._palette.accent_soft, alpha))
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
            painter.drawPath(key_shape_path(self._shape, rect))
            painter.setPen(_with_alpha(self._palette.text, alpha))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
            return

        # Touche principale : pastille claire, texte sombre.
        painter.setBrush(_with_alpha(self._palette.key_bg, alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(key_shape_path(self._shape, rect))
        painter.setPen(_with_alpha(self._palette.key_text, alpha))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)


class KeyRow(QWidget):
    """Une ligne de badges (une frappe ou une combinaison)."""

    def __init__(
        self,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
        shape_for: Optional[Callable[[str], str]] = None,
    ) -> None:
        super().__init__(parent)
        self._font = QFont(font)
        self._palette = palette
        self._shape_for = shape_for
        self._items: list[tuple[str, str]] = []
        self._count = 0
        self._badges: list[Badge] = []
        self._alpha = 1.0
        self._appear = 1.0
        self._zoom = 1.0
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # ------------------------------------------------------------------
    @property
    def items(self) -> list[tuple[str, str]]:
        """Badges de la ligne, sans le compteur de répétitions."""
        return list(self._items)

    @property
    def count(self) -> int:
        """Appuis regroupés (0 ou 1 : aucun compteur affiché)."""
        return self._count

    def set_items(self, items: Iterable[tuple[str, str]]) -> None:
        """Remplace le contenu de la ligne par ``[(libellé, type), ...]``."""
        self._items = list(items)
        self._count = 0
        self._rebuild()

    def set_count(self, count: int) -> None:
        """Regroupe ``count`` appuis identiques : « ×2 », « ×3 »…"""
        count = max(0, int(count))
        if count == self._count:
            return
        self._count = count
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

        items = list(self._items)
        if self._count > 1:
            items.append((f"×{self._count}", "count"))

        for label, kind in items:
            shape = "rounded"
            if self._shape_for is not None and kind in ("key", "mod"):
                shape = self._shape_for(label)
            badge = Badge(
                label, kind, self._font, self._palette, parent=self, shape=shape
            )
            badge.set_alpha(self._alpha)
            badge.set_appear(self._appear)
            badge.set_zoom(self._zoom)
            self._layout.addWidget(badge)
            self._badges.append(badge)

        self.updateGeometry()
        self.update()

    def set_alpha(self, alpha: float) -> None:
        self._alpha = alpha
        for badge in self._badges:
            badge.set_alpha(alpha)

    def set_appear(self, appear: float) -> None:
        """Fait apparaître la ligne entière (opacité de tous ses badges)."""
        self._appear = max(0.0, min(1.0, float(appear)))
        for badge in self._badges:
            badge.set_appear(self._appear)

    def set_zoom(self, zoom: float) -> None:
        """Grossit ou rétrécit le contenu de la ligne, sans changer sa place."""
        self._zoom = max(0.1, min(1.5, float(zoom)))
        for badge in self._badges:
            badge.set_zoom(self._zoom)
