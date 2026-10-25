"""Fenêtre de personnalisation de l'apparence de l'overlay."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import APPEARANCE_COLOR_FIELDS, Config, _color_to_text
from .constants import APP_NAME
from .i18n import LANGUAGE_AUTO, _t
from .icon import build_app_icon
from .keyboard import KeyboardView
from .theme import Palette, _config_color
from .widgets import KeyRow

class ColorButton(QPushButton):
    """Bouton affichant une couleur et ouvrant un sélecteur."""

    color_changed = pyqtSignal()

    def __init__(self, color: QColor, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setMinimumWidth(148)
        self.setToolTip(_t("Cliquer pour choisir une couleur"))
        self.clicked.connect(self._pick)
        self._refresh()

    # ------------------------------------------------------------------
    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor, emit: bool = True) -> None:
        if not isinstance(color, QColor) or not color.isValid():
            return
        self._color = QColor(color)
        self._refresh()
        if emit:
            self.color_changed.emit()

    def _refresh(self) -> None:
        swatch = QPixmap(18, 18)
        swatch.fill(Qt.GlobalColor.transparent)
        painter = QPainter(swatch)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for y in range(0, 18, 4):
            for x in range(0, 18, 4):
                light = (x // 4 + y // 4) % 2 == 0
                painter.fillRect(
                    x, y, 4, 4, QColor("#f2f4f7") if light else QColor("#cfd4dc")
                )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawRoundedRect(QRectF(1, 1, 16, 16), 4, 4)
        painter.end()
        self.setIcon(QIcon(swatch))

        text = self._color.name(QColor.NameFormat.HexRgb).upper()
        if self._color.alpha() < 255:
            text += f"  {round(self._color.alpha() / 255 * 100)} %"
        self.setText(text)

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(
            self._color, self, _t("Choisir une couleur")
        )
        if chosen.isValid():
            self.set_color(chosen)


class PreviewPanel(QWidget):
    """Aperçu compact de l'overlay avec les réglages en cours."""

    def __init__(
        self,
        config: Config,
        font_family: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._palette = Palette.from_config(config)
        self.setMinimumHeight(180)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(7)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._min_timer = QTimer(self)
        self._min_timer.setSingleShot(True)
        self._min_timer.timeout.connect(self._sync_minimum_size)

        font = QFont(font_family)
        font.setPointSize(max(9, config.font_size - 1))
        font.setWeight(QFont.Weight.DemiBold)

        self._rows: list[KeyRow] = []
        samples: tuple[tuple[tuple[str, str], ...], ...] = (
            ((_t("Ctrl"), "mod"), ("+", "plus"), ("C", "key")),
            ((_t("Maj"), "mod"), ("+", "plus"), ("→", "key")),
            ((_t("Clic gauche"), "mouse"),),
            ((_t("bonjour"), "text"),),
        )
        for items in samples:
            row = KeyRow(font, self._palette, self)
            row.set_items(items)
            self._layout.addWidget(row)
            self._rows.append(row)

        keyboard_font = QFont(font)
        keyboard_font.setPointSize(max(9, config.font_size - 4))
        self._keyboard = KeyboardView(config, keyboard_font, self._palette, self)
        self._layout.addWidget(self._keyboard)
        self._apply_mode(config)
        self._sync_minimum_size()

    # ------------------------------------------------------------------
    def _apply_mode(self, config: Config) -> None:
        """N'affiche que la vue correspondant au mode choisi."""
        keyboard_mode = config.display_mode == "keyboard"
        self._keyboard.setVisible(keyboard_mode)
        for row in self._rows:
            row.setVisible(not keyboard_mode)

    # ------------------------------------------------------------------
    def _sync_minimum_size(self) -> None:
        """Laisse l'aperçu grandir et défiler aux grandes tailles de police."""
        self._layout.invalidate()
        self._layout.activate()
        minimum = self._layout.minimumSize()
        self.setMinimumSize(minimum.width(), max(180, minimum.height()))

    # ------------------------------------------------------------------
    def update_appearance(self, config: Config, font_family: str) -> None:
        self._config = config
        self._palette.update_from_config(config)

        font = QFont(font_family)
        font.setPointSize(max(9, config.font_size - 1))
        font.setWeight(QFont.Weight.DemiBold)
        for row in self._rows:
            row.set_font(font)

        keyboard_font = QFont(font_family)
        keyboard_font.setPointSize(max(9, config.font_size - 4))
        self._keyboard.set_config(config)
        self._keyboard.set_font(keyboard_font)
        self._apply_mode(config)
        self._sync_minimum_size()
        # Le QScrollArea réévalue la taille du widget après le layout : on
        # réapplique la taille minimale une fois celui-ci stabilisé.
        self._min_timer.start(0)
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.fillRect(self.rect(), QColor("#eceef2"))
        checker = 12
        for y in range(0, self.height(), checker):
            for x in range(0, self.width(), checker):
                if (x // checker + y // checker) % 2:
                    painter.fillRect(x, y, checker, checker, QColor("#e2e5ea"))

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = float(self._config.corner_radius)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        alpha = int(round(255 * self._config.opacity))
        top = QColor(self._palette.panel_top)
        top.setAlpha(alpha)
        bottom = QColor(self._palette.panel_bottom)
        bottom.setAlpha(alpha)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)
        painter.fillPath(path, gradient)
        painter.setPen(QPen(self._palette.border, 1.0))
        painter.drawPath(path)


class AppearanceDialog(QDialog):
    """Fenêtre de personnalisation de l'apparence de l'overlay."""

    COLOR_LABELS: tuple[tuple[str, str], ...] = (
        ("background_color", "Fond (haut)"),
        ("background_color_bottom", "Fond (bas)"),
        ("text_color", "Texte"),
        ("key_background_color", "Touches (fond)"),
        ("key_text_color", "Touches (texte)"),
        ("accent_color", "Accents"),
    )

    def __init__(
        self,
        config: Config,
        font_family: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._base_config = config
        self._updating = False
        self.setWindowTitle(f"{APP_NAME} — {_t('Apparence')}")
        self.setWindowIcon(build_app_icon())
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumWidth(580)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)

        title = QLabel(_t("Personnaliser l'overlay"), self)
        title.setStyleSheet("font-size: 15pt; font-weight: 600;")
        outer.addWidget(title)

        subtitle = QLabel(
            _t(
                "Les couleurs, la police et la mise en forme sont appliquées à "
                "l'overlay et enregistrées dans le fichier de configuration."
            ),
            self,
        )
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        colors_group = QGroupBox(_t("Couleurs"), self)
        grid = QGridLayout(colors_group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.color_buttons: dict[str, ColorButton] = {}
        for index, (key, label) in enumerate(self.COLOR_LABELS):
            row = index // 3
            column = index % 3
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(QLabel(_t(label), colors_group))
            button = ColorButton(_config_color(config, key), colors_group)
            cell.addWidget(button)
            grid.addLayout(cell, row, column)
            self.color_buttons[key] = button
        for column in range(3):
            grid.setColumnStretch(column, 1)
        outer.addWidget(colors_group)

        form_group = QGroupBox(_t("Mise en forme"), self)
        form = QFormLayout(form_group)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        self.font_combo = QFontComboBox(form_group)
        self.font_combo.setCurrentFont(QFont(font_family))
        form.addRow(_t("Police"), self.font_combo)

        self.font_size = QSpinBox(form_group)
        self.font_size.setRange(9, 40)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(config.font_size)
        form.addRow(_t("Taille"), self.font_size)

        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal, form_group)
        self.opacity_slider.setRange(15, 100)
        self.opacity_slider.setValue(round(config.opacity * 100))
        self.opacity_slider.setMinimumWidth(200)
        self.opacity_label = QLabel(form_group)
        self.opacity_label.setMinimumWidth(46)
        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_label)
        form.addRow(_t("Opacité"), opacity_row)

        self.corner_radius = QSpinBox(form_group)
        self.corner_radius.setRange(0, 40)
        self.corner_radius.setSuffix(" px")
        self.corner_radius.setValue(config.corner_radius)
        form.addRow(_t("Coins arrondis"), self.corner_radius)

        self.margin = QSpinBox(form_group)
        self.margin.setRange(0, 400)
        self.margin.setSuffix(" px")
        self.margin.setValue(config.margin)
        form.addRow(_t("Marge écran"), self.margin)

        self.max_width = QSpinBox(form_group)
        self.max_width.setRange(220, 1600)
        self.max_width.setSingleStep(10)
        self.max_width.setSuffix(" px")
        self.max_width.setValue(config.max_width)
        form.addRow(_t("Largeur maximale"), self.max_width)
        outer.addWidget(form_group)

        display_group = QGroupBox(_t("Affichage"), self)
        display_form = QFormLayout(display_group)
        display_form.setHorizontalSpacing(14)
        display_form.setVerticalSpacing(8)

        self.mode_combo = QComboBox(display_group)
        for value, label in (
            ("overlay", _t("Overlay standard")),
            ("keyboard", _t("Clavier complet")),
        ):
            self.mode_combo.addItem(label, value)
        index = self.mode_combo.findData(str(config.display_mode).strip().lower())
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        display_form.addRow(_t("Mode d'affichage"), self.mode_combo)

        self.layout_combo = QComboBox(display_group)
        for value, label in (
            ("azerty", _t("AZERTY (français)")),
            ("qwerty", _t("QWERTY (anglais)")),
        ):
            self.layout_combo.addItem(label, value)
        index = self.layout_combo.findData(str(config.keyboard_layout).strip().lower())
        self.layout_combo.setCurrentIndex(index if index >= 0 else 0)
        display_form.addRow(_t("Disposition du clavier"), self.layout_combo)
        outer.addWidget(display_group)

        interface_group = QGroupBox(_t("Interface"), self)
        interface_form = QFormLayout(interface_group)
        interface_form.setHorizontalSpacing(14)
        interface_form.setVerticalSpacing(8)
        self.language_combo = QComboBox(interface_group)
        for value, label in (
            (LANGUAGE_AUTO, _t("Automatique (système)")),
            ("fr", "Français"),
            ("en", "English"),
        ):
            self.language_combo.addItem(label, value)
        index = self.language_combo.findData(
            str(config.language).strip().lower()
        )
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        interface_form.addRow(_t("Langue"), self.language_combo)
        outer.addWidget(interface_group)

        preview_group = QGroupBox(_t("Aperçu"), self)
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview = PreviewPanel(config, font_family)
        preview_scroll = QScrollArea(preview_group)
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setWidget(self.preview)
        preview_scroll.setMinimumHeight(160)
        preview_scroll.setMaximumHeight(200)
        preview_layout.addWidget(preview_scroll)
        outer.addWidget(preview_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(_t("Enregistrer"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_t("Annuler"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        reset = QPushButton(_t("Réinitialiser"), self)
        bottom = QHBoxLayout()
        bottom.addWidget(reset)
        bottom.addStretch(1)
        bottom.addWidget(buttons)
        outer.addLayout(bottom)

        reset.clicked.connect(self._reset)
        for button in self.color_buttons.values():
            button.color_changed.connect(self._refresh_preview)
        self.font_combo.currentFontChanged.connect(self._refresh_preview)
        self.font_size.valueChanged.connect(self._refresh_preview)
        self.opacity_slider.valueChanged.connect(self._refresh_preview)
        self.corner_radius.valueChanged.connect(self._refresh_preview)
        self.margin.valueChanged.connect(self._refresh_preview)
        self.max_width.valueChanged.connect(self._refresh_preview)
        self.mode_combo.currentIndexChanged.connect(self._refresh_preview)
        self.layout_combo.currentIndexChanged.connect(self._refresh_preview)

        self._refresh_preview()
        self.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geometry = self.frameGeometry()
            geometry.moveCenter(screen.availableGeometry().center())
            self.move(geometry.topLeft())
        self.font_combo.setFocus()

    # ------------------------------------------------------------------
    def values(self) -> dict[str, object]:
        """Réglages choisis, prêts à être appliqués et enregistrés."""
        family = self.font_combo.currentFont().family().strip()
        if not family:
            family = self._base_config.font_family
        payload: dict[str, object] = {
            "language": self.language_combo.currentData() or LANGUAGE_AUTO,
            "display_mode": self.mode_combo.currentData() or "overlay",
            "keyboard_layout": self.layout_combo.currentData() or "azerty",
            "opacity": self.opacity_slider.value() / 100.0,
            "font_family": family,
            "font_size": self.font_size.value(),
            "max_width": self.max_width.value(),
            "corner_radius": self.corner_radius.value(),
            "margin": self.margin.value(),
        }
        for key in APPEARANCE_COLOR_FIELDS:
            payload[key] = _color_to_text(self.color_buttons[key].color())
        return payload

    # ------------------------------------------------------------------
    def _preview_config(self) -> Config:
        config = replace(self._base_config)
        for key, value in self.values().items():
            setattr(config, key, value)
        config.validate()
        return config

    def _refresh_preview(self) -> None:
        if self._updating:
            return
        config = self._preview_config()
        self.preview.update_appearance(config, _choose_font_family(config))
        self.opacity_label.setText(f"{round(config.opacity * 100)} %")

    def _reset(self) -> None:
        defaults = Config()
        self._updating = True
        try:
            for key, button in self.color_buttons.items():
                button.set_color(QColor(getattr(defaults, key)), emit=False)
            self.font_combo.setCurrentFont(QFont(_choose_font_family(defaults)))
            self.font_size.setValue(defaults.font_size)
            self.opacity_slider.setValue(round(defaults.opacity * 100))
            self.corner_radius.setValue(defaults.corner_radius)
            self.margin.setValue(defaults.margin)
            self.max_width.setValue(defaults.max_width)
            index = self.language_combo.findData(defaults.language)
            self.language_combo.setCurrentIndex(index if index >= 0 else 0)
            index = self.mode_combo.findData(defaults.display_mode)
            self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
            index = self.layout_combo.findData(defaults.keyboard_layout)
            self.layout_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self._updating = False
        self._refresh_preview()


def _choose_font_family(config: Config) -> str:
    """Choisit une police moderne disponible sur le système."""
    if config.font_family:
        return config.font_family
    try:
        available = set(QFontDatabase.families())
    except Exception:
        available = set()
    for candidate in (
        "Segoe UI Variable Text",
        "Segoe UI",
        "SF Pro Text",
        "Helvetica Neue",
        "Inter",
        "Ubuntu",
        "Cantarell",
        "DejaVu Sans",
    ):
        if candidate in available:
            return candidate
    default = QApplication.font().family()
    return default or "Sans Serif"

