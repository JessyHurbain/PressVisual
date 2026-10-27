"""Éditeur des formes de touches du clavier complet.

L'éditeur montre les touches de la disposition courante ; la forme choisie
s'applique à toutes celles qui n'ont pas d'exception, et un clic sur une
touche lui donne sa propre forme (une fleur pour le A, une étoile pour
Entrée…). Les exceptions sont enregistrées dans ``key_shapes``.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import Config
from .i18n import _t
from .keyboard import layout_for
from .keymap import KEY_SHAPE_LABELS, KEY_SHAPES
from .shapes import key_shape_path
from .theme import Palette, _with_alpha

#: Taille d'une touche dans la grille de l'éditeur (px).
PATCH_SIZE = QSize(36, 28)
#: Taille des vignettes de formes dans la liste (px).
SWATCH_SIZE = QSize(44, 30)


def shape_icon(shape: str, palette: Palette, size: QSize = SWATCH_SIZE) -> QIcon:
    """Vignette d'une forme, dessinée avec les couleurs de l'overlay."""
    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rect = QRectF(2.0, 2.0, size.width() - 4.0, size.height() - 4.0)
    # La vignette reprend le panneau de l'overlay : une touche claire sur le
    # fond blanc d'une liste déroulante serait invisible.
    backdrop = QPainterPath()
    backdrop.addRoundedRect(rect, 5.0, 5.0)
    painter.fillPath(backdrop, _with_alpha(palette.panel_top, 0.95))
    path = key_shape_path(shape, rect.adjusted(4.0, 4.0, -4.0, -4.0))
    painter.fillPath(path, _with_alpha(palette.key_bg, 0.95))
    painter.setPen(QPen(_with_alpha(palette.key_text, 0.45), 1.2))
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class KeyPatch(QWidget):
    """Une touche de la grille : cliquez-la pour lui donner une forme."""

    clicked = pyqtSignal()

    def __init__(
        self,
        label: str,
        palette: Palette,
        font: QFont,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._palette = palette
        self._font = QFont(font)
        self._font.setPointSizeF(max(6.0, self._font.pointSizeF() - 4.0))
        self._shape = "rounded"
        self._overridden = False
        self.setFixedSize(PATCH_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{label} — {_t('cliquer pour changer la forme')}")

    # ------------------------------------------------------------------
    @property
    def label(self) -> str:
        return self._label

    @property
    def shape(self) -> str:
        """Forme effective de la touche, exception comprise."""
        return self._shape

    @property
    def overridden(self) -> bool:
        """Vrai si la touche a sa propre forme."""
        return self._overridden

    def set_shape(self, shape: str, overridden: bool) -> None:
        self._shape = shape
        self._overridden = bool(overridden)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        path = key_shape_path(self._shape, rect)
        painter.fillPath(path, _with_alpha(self._palette.key_bg, 0.92))
        border = (
            _with_alpha(self._palette.accent, 0.95)
            if self._overridden
            else _with_alpha(self._palette.key_text, 0.45)
        )
        painter.setPen(QPen(border, 1.0 + (0.8 if self._overridden else 0.0)))
        painter.drawPath(path)

        painter.setFont(self._font)
        painter.setPen(_with_alpha(self._palette.key_text, 0.92))
        metrics = QFontMetrics(self._font)
        text = metrics.elidedText(
            self._label,
            Qt.TextElideMode.ElideRight,
            max(8, self.width() - 6),
        )
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)


class KeyShapeEditor(QWidget):
    """Palette de formes, grille de touches et exceptions par touche."""

    changed = pyqtSignal()

    def __init__(
        self,
        config: Config,
        font_family: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._palette = Palette.from_config(config)
        self._layout_name = ""
        self._overrides: dict[str, str] = dict(config.key_shapes)
        self._patches: dict[str, list[KeyPatch]] = {}
        self._font = QFont(font_family)
        self._font.setPointSizeF(11.0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        default_row = QHBoxLayout()
        default_row.addWidget(QLabel(_t("Forme par défaut"), self))
        self.default_combo = QComboBox(self)
        self.default_combo.setIconSize(QSize(30, 20))
        for shape in KEY_SHAPES:
            self.default_combo.addItem(
                shape_icon(shape, self._palette), _t(KEY_SHAPE_LABELS[shape]), shape
            )
        index = self.default_combo.findData(config.key_shape)
        self.default_combo.setCurrentIndex(index if index >= 0 else 0)
        default_row.addWidget(self.default_combo, 1)
        outer.addLayout(default_row)

        brush_row = QHBoxLayout()
        brush_row.addWidget(QLabel(_t("Forme à appliquer"), self))
        self.brush_combo = QComboBox(self)
        self.brush_combo.setIconSize(QSize(30, 20))
        for shape in KEY_SHAPES:
            self.brush_combo.addItem(
                shape_icon(shape, self._palette), _t(KEY_SHAPE_LABELS[shape]), shape
            )
        brush_row.addWidget(self.brush_combo, 1)
        outer.addLayout(brush_row)

        hint = QLabel(
            _t("Cliquez une touche du clavier pour lui donner cette forme."),
            self,
        )
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self._grid_host = QWidget(self)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(3)
        self._grid.setVerticalSpacing(3)
        outer.addWidget(self._grid_host)

        buttons = QHBoxLayout()
        self.apply_all = QPushButton(_t("Appliquer à toutes"), self)
        self.clear_overrides = QPushButton(_t("Effacer les exceptions"), self)
        buttons.addWidget(self.apply_all)
        buttons.addWidget(self.clear_overrides)
        buttons.addStretch(1)
        outer.addLayout(buttons)

        self.default_combo.currentIndexChanged.connect(self._default_changed)
        self.apply_all.clicked.connect(self._apply_to_all)
        self.clear_overrides.clicked.connect(self._clear_overrides)
        self._build_grid(config.keyboard_layout)

    # ------------------------------------------------------------------
    def values(self) -> dict[str, object]:
        """Formes choisies, prêtes à être appliquées et enregistrées."""
        return {
            "key_shape": self.default_combo.currentData() or "rounded",
            "key_shapes": dict(self._overrides),
        }

    def set_layout(self, name: str) -> None:
        """Reconstruit la grille quand la disposition change."""
        if str(name).strip().lower() == self._layout_name:
            return
        self._build_grid(name)

    def reset(self) -> None:
        """Revient aux formes d'origine (aucune exception)."""
        self._overrides.clear()
        index = self.default_combo.findData("rounded")
        self.default_combo.setCurrentIndex(index if index >= 0 else 0)
        self._refresh_patches()

    # ------------------------------------------------------------------
    def _build_grid(self, layout_name: str) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._patches.clear()

        layout = layout_for(layout_name)
        self._layout_name = layout.name
        for row_index, row in enumerate(layout.rows):
            for column, key in enumerate(row):
                patch = KeyPatch(key.label, self._palette, self._font, self._grid_host)
                patch.clicked.connect(
                    lambda label=key.label: self._paint_key(label)
                )
                self._grid.addWidget(patch, row_index, column)
                self._patches.setdefault(key.label, []).append(patch)
        self._refresh_patches()

    def _refresh_patches(self) -> None:
        default = self.default_combo.currentData() or "rounded"
        for label, patches in self._patches.items():
            shape = self._overrides.get(label, default)
            for patch in patches:
                patch.set_shape(shape, label in self._overrides)

    def _default_changed(self) -> None:
        self._refresh_patches()
        self.changed.emit()

    def _paint_key(self, label: str) -> None:
        shape = self.brush_combo.currentData() or "rounded"
        self._overrides[label] = str(shape)
        self._refresh_patches()
        self.changed.emit()

    def _apply_to_all(self) -> None:
        shape = self.brush_combo.currentData() or "rounded"
        index = self.default_combo.findData(shape)
        self.default_combo.setCurrentIndex(index if index >= 0 else 0)
        self._overrides.clear()
        self._refresh_patches()
        self.changed.emit()

    def _clear_overrides(self) -> None:
        self._overrides.clear()
        self._refresh_patches()
        self.changed.emit()
