"""Fenêtre de personnalisation de l'apparence de l'overlay."""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
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
    QRegion,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedLayout,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import APPEARANCE_COLOR_FIELDS, Config, _color_to_text
from .constants import APP_NAME
from .i18n import LANGUAGE_AUTO, _t
from .icon import build_app_icon
from .keyboard import InputView
from .keyeditor import KeyShapeEditor
from .keymap import (
    CURSOR_STYLE_LABELS,
    CURSOR_STYLES,
    MOUSE_STYLE_LABELS,
    MOUSE_STYLES,
    ROW_ANIMATION_LABELS,
    ROW_ANIMATIONS,
    TRANSITION_LABELS,
    TRANSITIONS,
    key_shape_for,
    modifier_side_token,
    transition_geometry,
)
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


#: Cadence des étapes de la démonstration animée de l'aperçu (ms).
#: Assez lente pour suivre des yeux la touche enfoncée, la relâcher, puis le
#: clic : une démonstration trop rapide ne laisse voir qu'un clignotement.
DEMO_STEP_MS = 1200
#: Pause sur la bulle visible avant de la faire sortir (ms).
#: La transition elle-même garde la durée choisie ; seule cette pause la
#: précède, pour laisser le temps de voir la bulle au repos.
PREVIEW_HOLD_MS = 1500
#: Pause sur la bulle masquée avant qu'elle revienne (ms).
PREVIEW_GAP_MS = 260
#: Attente avant de rejouer la démonstration après un réglage (ms).
#: Un curseur glissé d'un trait envoie une valeur par cran : sans cette
#: attente, la démonstration repartirait des dizaines de fois et resterait
#: figée sur sa première étape pendant tout le geste.
PREVIEW_DEBOUNCE_MS = 220
#: Réglages qui ne concernent que l'entrée et la sortie de la bulle.
TRANSITION_FIELDS = ("transition", "transition_out_ms", "transition_in_ms")


def _paint_checkerboard(painter: QPainter, width: int, height: int) -> None:
    """Damier transparent, visible autour de la bulle."""
    painter.fillRect(0, 0, width, height, QColor("#eceef2"))
    checker = 12
    for y in range(0, height, checker):
        for x in range(0, width, checker):
            if (x // checker + y // checker) % 2:
                painter.fillRect(x, y, checker, checker, QColor("#e2e5ea"))


class BubbleSurface(QWidget):
    """Bulle de l'aperçu : fond arrondi, dégradé et contenu réel."""

    def __init__(
        self, config: Config, palette: Palette, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._palette = palette

    def set_config(self, config: Config) -> None:
        self._config = config
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

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


class TransitionStage(QWidget):
    """Rejoue l'image de la bulle avec la transition choisie.

    L'aperçu n'est pas une vraie fenêtre : la bulle y est dessinée comme une
    image, décalée ou rétrécie selon l'avancement, sur le damier.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._shot: Optional[QPixmap] = None
        self._origin = QPoint(0, 0)
        self._style = "fade"
        self._progress = 0.0

    def set_frame(
        self,
        shot: Optional[QPixmap],
        origin: QPoint,
        style: str,
        progress: float,
    ) -> None:
        self._shot = shot
        self._origin = origin
        self._style = style
        self._progress = max(0.0, min(1.0, float(progress)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        _paint_checkerboard(painter, self.width(), self.height())

        shot = self._shot
        if shot is None:
            return

        width = shot.width() / shot.devicePixelRatio()
        height = shot.height() / shot.devicePixelRatio()
        # Même géométrie que l'overlay : les deux ne peuvent pas diverger.
        dx, dy, scale, opacity = transition_geometry(
            self._style, width, height, self._progress
        )
        painter.setOpacity(max(0.0, min(1.0, opacity)))

        center = QPointF(
            self._origin.x() + width / 2 + dx,
            self._origin.y() + height / 2 + dy,
        )
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-width / 2, -height / 2)
        painter.drawPixmap(QPointF(0, 0), shot)


class PreviewPanel(QWidget):
    """Aperçu compact de l'overlay avec les réglages en cours.

    Une petite démonstration anime l'aperçu : une lettre s'allume sur le
    clavier, un bouton de souris s'enfonce, puis une combinaison et un clic
    droit prennent le relais. Le mode standard montre la même chose sous
    forme de pastilles.

    La bulle disparaît et revient ensuite avec la transition choisie, sur
    sa durée réelle, pour juger du réglage sans ouvrir l'overlay.

    La démonstration ne tourne pas en boucle : elle se joue une fois, à
    l'ouverture de la fenêtre puis à chaque changement de réglage — une seule
    fois par geste, quand les valeurs se stabilisent — et l'aperçu reste
    ensuite sur la dernière image.
    """

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

        # Deux pages de même taille : la bulle réelle, puis son image animée
        # pendant la transition. Le passage de l'une à l'autre ne fait pas
        # bouger la mise en page.
        self._surface = BubbleSurface(config, self._palette, self)
        self._stage = TransitionStage(self)
        self._stack = QStackedLayout()
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._surface)
        self._stack.addWidget(self._stage)
        self._stack.setCurrentWidget(self._surface)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._stack)

        self._layout = QVBoxLayout(self._surface)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(7)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._min_timer = QTimer(self)
        self._min_timer.setSingleShot(True)
        self._min_timer.timeout.connect(self._sync_minimum_size)

        font = QFont(font_family)
        font.setPointSize(max(9, config.font_size - 1))
        font.setWeight(QFont.Weight.DemiBold)

        # Démonstration animée : une pastille dont le contenu change pour
        # montrer une frappe puis un clic dans le mode standard. Elle est
        # placée en tête pour rester visible sans faire défiler l'aperçu.
        self._demo_row = KeyRow(
            font, self._palette, self._surface, shape_for=self._shape_for
        )
        self._layout.addWidget(self._demo_row)

        self._rows: list[KeyRow] = []
        samples: tuple[tuple[tuple[str, str], ...], ...] = (
            ((_t("Ctrl"), "mod"), ("+", "plus"), ("C", "key")),
            ((_t("Maj"), "mod"), ("+", "plus"), ("→", "key")),
            ((_t("Clic gauche"), "mouse"),),
            ((_t("bonjour"), "text"),),
        )
        for items in samples:
            row = KeyRow(
                font, self._palette, self._surface, shape_for=self._shape_for
            )
            row.set_items(items)
            self._layout.addWidget(row)
            self._rows.append(row)

        keyboard_font = QFont(font)
        keyboard_font.setPointSize(max(9, config.font_size - 4))
        self._visual = InputView(
            config, keyboard_font, self._palette, self._surface
        )
        self._keyboard = self._visual.keyboard
        self._mouse = self._visual.mouse
        self._layout.addWidget(self._visual, 0, Qt.AlignmentFlag.AlignLeft)

        # La démonstration se joue une fois par réglage : le minuteur est
        # relancé à chaque étape, puis laissé s'arrêter, au lieu de boucler.
        self._demo_step = 0
        self._demo_timer = QTimer(self)
        self._demo_timer.setSingleShot(True)
        self._demo_timer.setInterval(DEMO_STEP_MS)
        self._demo_timer.timeout.connect(self._advance_demo)

        # Cycle de la transition : bulle visible, sortie, pause, retour.
        self._phase = "idle"
        self._progress = 0.0
        self._shot: Optional[QPixmap] = None
        self._origin = QPoint(0, 0)
        self._transition = QVariantAnimation(self)
        self._transition.valueChanged.connect(self._on_transition_value)
        self._transition.finished.connect(self._on_transition_finished)
        self._cycle_timer = QTimer(self)
        self._cycle_timer.setSingleShot(True)
        self._cycle_timer.timeout.connect(self._on_cycle_timeout)

        # Rejeu différé : un même geste (curseur, molette de réglage) arme
        # une seule démonstration, jouée quand les valeurs se stabilisent.
        self._replay_transition = False
        self._replay_timer = QTimer(self)
        self._replay_timer.setSingleShot(True)
        self._replay_timer.setInterval(PREVIEW_DEBOUNCE_MS)
        self._replay_timer.timeout.connect(self._replay)

        self._apply_mode(config)
        self._sync_minimum_size()
        self.play_demo()

    # ------------------------------------------------------------------
    # Démonstration animée
    # ------------------------------------------------------------------
    def play_demo(self) -> None:
        """Rejoue une fois la démonstration, puis la transition.

        L'aperçu ne s'anime plus en boucle : il redevient immobile une fois
        la démonstration finie, jusqu'au prochain réglage.
        """
        self._reset_animation()
        self._demo_step = 0
        self._apply_demo_step()
        self._demo_timer.start()

    def play_transition(self) -> None:
        """Rejoue la transition une fois, sans la démonstration des gestes.

        Un réglage de transition se juge en le voyant : inutile de le faire
        attendre la fin d'une frappe simulée.
        """
        self._reset_animation()
        self._cycle_timer.start(PREVIEW_HOLD_MS)

    def _schedule_replay(self, transition_only: bool) -> None:
        """Programme un rejeu, une fois le réglage stabilisé."""
        self._replay_transition = transition_only
        self._replay_timer.start()

    def _replay(self) -> None:
        """Rejoue ce que demandait le dernier réglage modifié."""
        if self._replay_transition:
            self.play_transition()
        else:
            self.play_demo()

    def _reset_animation(self) -> None:
        """Ramène l'aperçu à la bulle visible, prête à être rejouée."""
        self._replay_timer.stop()
        self._demo_timer.stop()
        self._transition.stop()
        self._cycle_timer.stop()
        self._phase = "idle"
        self._progress = 0.0
        self._shot = None
        self._stack.setCurrentWidget(self._surface)
        self.update()

    def _demo_steps(
        self,
    ) -> tuple[
        tuple[
            tuple[str, ...],
            tuple[str, ...],
            tuple[str, ...],
            Optional[tuple[str, int]],
            tuple[tuple[str, str], ...],
        ],
        ...,
    ]:
        """Étapes de la démonstration : touches, modificateurs, boutons,
        molette et pastille équivalente dans le mode standard."""
        letter = (("a", "key"),)
        click = ((_t("Clic droit"), "mouse"),)
        return (
            (("a",), (), ("left",), None, letter),
            ((), (), (), None, letter),
            (("e",), ("shift",), ("right",), ("vertical", 1), click),
            ((), (), (), None, click),
        )

    def _advance_demo(self) -> None:
        """Passe à l'étape suivante, puis rejoue la transition à la fin."""
        steps = self._demo_steps()
        next_step = self._demo_step + 1
        if next_step >= len(steps):
            # Fin de la démonstration : la bulle sort et revient une dernière
            # fois, puis l'aperçu reste au repos.
            self._demo_timer.stop()
            self._start_exit()
            return
        self._demo_step = next_step
        self._apply_demo_step()
        self._demo_timer.start()

    def _apply_demo_step(self) -> None:
        """Applique l'étape courante au clavier, à la souris et à la pastille."""
        steps = self._demo_steps()
        keys, modifiers, buttons, scroll, items = steps[
            self._demo_step % len(steps)
        ]
        self._keyboard.set_modifiers(modifiers)
        # La démonstration enfonce la touche de gauche : un seul Maj s'allume,
        # comme dans l'overlay quand le côté est connu.
        self._keyboard.set_modifier_sides(
            modifier_side_token(modifier, "left") for modifier in modifiers
        )
        self._keyboard.set_active(keys)
        self._mouse.set_buttons(buttons)
        if scroll is None:
            self._mouse.clear_scroll()
        else:
            self._mouse.set_scroll(*scroll)
        self._demo_row.set_items(items)

    # ------------------------------------------------------------------
    def _apply_mode(self, config: Config) -> None:
        """N'affiche que la vue correspondant au mode choisi."""
        keyboard_mode = config.display_mode == "keyboard"
        self._visual.set_mode_visible(keyboard_mode)
        for row in self._rows:
            row.setVisible(not keyboard_mode)
        self._demo_row.setVisible(not keyboard_mode)

    # ------------------------------------------------------------------
    def _sync_minimum_size(self) -> None:
        """Laisse l'aperçu grandir et défiler aux grandes tailles de police."""
        self._layout.invalidate()
        self._layout.activate()
        minimum = self._layout.minimumSize()
        self.setMinimumSize(minimum.width(), max(180, minimum.height()))

    # ------------------------------------------------------------------
    def _shape_for(self, label: str) -> str:
        """Forme d'une touche de la bulle, lue dans la configuration courante."""
        return key_shape_for(self._config, label)

    def update_appearance(self, config: Config, font_family: str) -> None:
        previous = self._config
        self._config = config
        self._palette.update_from_config(config)
        self._surface.set_config(config)

        font = QFont(font_family)
        font.setPointSize(max(9, config.font_size - 1))
        font.setWeight(QFont.Weight.DemiBold)
        for row in self._rows:
            row.set_font(font)
        self._demo_row.set_font(font)

        keyboard_font = QFont(font_family)
        keyboard_font.setPointSize(max(9, config.font_size - 4))
        self._visual.set_config(config)
        self._visual.set_font(keyboard_font)
        self._apply_mode(config)
        self._sync_minimum_size()
        # Un réglage de transition se juge en le voyant : il rejoue la
        # transition seule, les autres la démonstration des gestes. Dans les
        # deux cas le rejeu attend la fin du geste.
        self._schedule_replay(self._transition_changed(previous, config))
        # Le QScrollArea réévalue la taille du widget après le layout : on
        # réapplique la taille minimale une fois celui-ci stabilisé.
        self._min_timer.start(0)
        self.update()

    def _transition_changed(self, previous: Config, config: Config) -> bool:
        """Vrai si le changement touche la transition elle-même."""
        return any(
            getattr(previous, name, None) != getattr(config, name, None)
            for name in TRANSITION_FIELDS
        )

    # ------------------------------------------------------------------
    # Aperçu de la transition
    # ------------------------------------------------------------------
    def _transition_style(self) -> str:
        """Transition à montrer : celle de la configuration, sinon fondu."""
        style = str(self._config.transition or "fade").strip().lower()
        return style if style in TRANSITION_LABELS else "fade"

    def _exit_duration(self) -> int:
        if self._transition_style() == "none":
            return 0
        return max(0, int(self._config.transition_out_ms))

    def _entry_duration(self) -> int:
        duration = self._exit_duration()
        if duration <= 0:
            return 0
        return min(max(0, int(self._config.transition_in_ms)), duration)

    def hideEvent(self, event) -> None:  # noqa: N802 - API Qt
        """Suspend les animations quand l'aperçu n'est plus visible."""
        self._replay_timer.stop()
        self._demo_timer.stop()
        self._transition.stop()
        self._cycle_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - API Qt
        """Rejoue la démonstration à l'ouverture de la fenêtre."""
        super().showEvent(event)
        self.play_demo()

    def _on_cycle_timeout(self) -> None:
        if self._phase == "idle":
            self._start_exit()
        elif self._phase == "hidden":
            self._start_entry()

    def _freeze(self) -> None:
        """Copie l'image de la bulle, sans le damier de l'aperçu."""
        surface = self._surface
        ratio = surface.devicePixelRatioF()
        pixmap = QPixmap(surface.size() * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        surface.render(
            painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren
        )
        painter.end()
        self._shot = pixmap
        self._origin = surface.pos()

    def _start_exit(self) -> None:
        """Gèle l'image de la bulle et la fait sortir."""
        # La pause qui précède appartient à la phase précédente.
        self._cycle_timer.stop()
        style = self._transition_style()
        duration = self._exit_duration()
        if style == "none" or duration <= 0:
            self._shot = None
            self._stack.setCurrentWidget(self._stage)
            self._phase = "hidden"
            self._progress = 1.0
            self._update_stage()
            self._cycle_timer.start(PREVIEW_GAP_MS)
            return
        self._freeze()
        self._stack.setCurrentWidget(self._stage)
        self._phase = "exit"
        self._progress = 0.0
        self._update_stage()
        self._run(duration, 1.0, QEasingCurve.Type.InCubic)

    def _start_entry(self) -> None:
        """Ramenne la bulle avec la même transition, en sens inverse."""
        self._cycle_timer.stop()
        duration = self._entry_duration()
        if duration <= 0:
            self._finish_entry()
            return
        self._freeze()
        self._phase = "entry"
        self._progress = 1.0
        self._update_stage()
        self._run(duration, 0.0, QEasingCurve.Type.OutCubic)

    def _run(
        self, duration: int, end: float, easing: QEasingCurve.Type
    ) -> None:
        self._transition.stop()
        self._transition.setDuration(max(1, duration))
        self._transition.setEasingCurve(easing)
        self._transition.setStartValue(0.0 if end else 1.0)
        self._transition.setEndValue(end)
        self._transition.start()

    def _on_transition_value(self, value: float) -> None:
        self._progress = float(value)
        self._update_stage()

    def _on_transition_finished(self) -> None:
        if self._phase == "exit":
            self._phase = "hidden"
            self._progress = 1.0
            self._update_stage()
            self._cycle_timer.start(PREVIEW_GAP_MS)
            return
        if self._phase == "entry":
            self._finish_entry()

    def _finish_entry(self) -> None:
        """Rend la vraie bulle à l'aperçu, au repos jusqu'au prochain réglage."""
        self._cycle_timer.stop()
        self._phase = "idle"
        self._progress = 0.0
        self._shot = None
        self._stack.setCurrentWidget(self._surface)
        self.update()

    def _update_stage(self) -> None:
        self._stage.set_frame(
            self._shot, self._origin, self._transition_style(), self._progress
        )

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        _paint_checkerboard(painter, self.width(), self.height())


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
        self.setMinimumWidth(620)

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

        self.show_mouse = QCheckBox(
            _t("Afficher la souris à côté du clavier"), display_group
        )
        self.show_mouse.setChecked(bool(config.show_mouse))
        display_form.addRow(self.show_mouse)

        self.mouse_style_combo = QComboBox(display_group)
        for value in MOUSE_STYLES:
            self.mouse_style_combo.addItem(_t(MOUSE_STYLE_LABELS[value]), value)
        index = self.mouse_style_combo.findData(
            str(config.mouse_style).strip().lower()
        )
        self.mouse_style_combo.setCurrentIndex(index if index >= 0 else 0)
        display_form.addRow(_t("Design de la souris"), self.mouse_style_combo)

        self.mouse_tracking = QCheckBox(
            _t("Afficher les clics et la molette près du curseur"), display_group
        )
        self.mouse_tracking.setChecked(bool(config.mouse_tracking))
        display_form.addRow(self.mouse_tracking)

        self.count_repeats = QCheckBox(
            _t("Regrouper les appuis répétés de la même touche (×2)"),
            display_group,
        )
        self.count_repeats.setChecked(bool(config.count_repeats))
        self.count_repeats.setToolTip(
            _t("Deux appuis de suite affichent « ×2 » au lieu de deux pastilles.")
        )
        display_form.addRow(self.count_repeats)

        self.cursor_style_combo = QComboBox(display_group)
        for value in CURSOR_STYLES:
            self.cursor_style_combo.addItem(
                _t(CURSOR_STYLE_LABELS[value]), value
            )
        index = self.cursor_style_combo.findData(
            str(config.cursor_style).strip().lower()
        )
        self.cursor_style_combo.setCurrentIndex(index if index >= 0 else 0)
        display_form.addRow(
            _t("Design des clics près du curseur"), self.cursor_style_combo
        )

        self.transition_combo = QComboBox(display_group)
        for value in TRANSITIONS:
            self.transition_combo.addItem(_t(TRANSITION_LABELS[value]), value)
        index = self.transition_combo.findData(
            str(config.transition).strip().lower()
        )
        self.transition_combo.setCurrentIndex(index if index >= 0 else 0)
        display_form.addRow(_t("Transition de la bulle"), self.transition_combo)

        self.transition_duration = QSpinBox(display_group)
        self.transition_duration.setRange(0, 3000)
        self.transition_duration.setSingleStep(50)
        self.transition_duration.setSuffix(" ms")
        self.transition_duration.setValue(int(config.transition_out_ms))
        display_form.addRow(_t("Durée de la disparition"), self.transition_duration)

        self.animation_combo = QComboBox(display_group)
        for value in ROW_ANIMATIONS:
            self.animation_combo.addItem(_t(ROW_ANIMATION_LABELS[value]), value)
        index = self.animation_combo.findData(
            str(config.row_animation).strip().lower()
        )
        self.animation_combo.setCurrentIndex(index if index >= 0 else 0)
        display_form.addRow(_t("Animation des lignes"), self.animation_combo)

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

        language_note = QLabel(
            _t("La langue s'applique dès l'enregistrement, sans redémarrer."),
            interface_group,
        )
        language_note.setWordWrap(True)
        interface_form.addRow(language_note)

        shapes_group = QGroupBox(_t("Formes des touches"), self)
        shapes_layout = QVBoxLayout(shapes_group)
        shapes_layout.setContentsMargins(10, 10, 10, 10)
        self.key_editor = KeyShapeEditor(config, font_family, shapes_group)
        shapes_layout.addWidget(self.key_editor)

        #: Onglets des réglages : chaque page défile si la fenêtre est basse,
        #: l'aperçu et les boutons restant toujours visibles.
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        #: Assez haut pour voir plusieurs réglages ; les pages défilent.
        self.tabs.setMinimumHeight(200)
        self.tabs.addTab(
            self._make_page(display_group), _t("Affichage")
        )
        self.tabs.addTab(self._make_page(colors_group), _t("Couleurs"))
        self.tabs.addTab(
            self._make_page(form_group), _t("Mise en forme")
        )
        self.tabs.addTab(self._make_page(shapes_group), _t("Touches"))
        self.tabs.addTab(
            self._make_page(interface_group, margin=6), _t("Interface")
        )
        outer.addWidget(self.tabs, 1)

        preview_group = QGroupBox(_t("Aperçu"), self)
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        self.preview = PreviewPanel(config, font_family)
        preview_scroll = QScrollArea(preview_group)
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setWidget(self.preview)
        preview_scroll.setFixedHeight(240)
        preview_layout.addWidget(preview_scroll)
        preview_group.setMaximumHeight(290)
        outer.addWidget(preview_group, 0)
        self.preview_scroll = preview_scroll

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(_t("Enregistrer"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(_t("Annuler"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.buttons = buttons

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
        self.show_mouse.toggled.connect(self._refresh_preview)
        self.count_repeats.toggled.connect(self._refresh_preview)
        self.mouse_style_combo.currentIndexChanged.connect(self._refresh_preview)
        self.transition_combo.currentIndexChanged.connect(self._refresh_preview)
        self.transition_duration.valueChanged.connect(self._refresh_preview)
        self.animation_combo.currentIndexChanged.connect(self._refresh_preview)
        self.key_editor.changed.connect(self._refresh_preview)
        self.layout_combo.currentIndexChanged.connect(self._sync_key_layout)

        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None and screen.availableGeometry().height() < 760:
            # Écran bas : l'aperçu et les onglets cèdent de la place plutôt
            # que de pousser les boutons hors de la fenêtre.
            self.tabs.setMinimumHeight(150)
            self.preview_scroll.setFixedHeight(150)

        self._refresh_preview()
        self.adjustSize()
        if screen is not None:
            available = screen.availableGeometry()
            # La fenêtre ne dépasse jamais l'écran : les pages défilent et
            # les boutons restent accessibles.
            self.resize(
                min(self.width(), max(460, available.width() - 40)),
                min(self.height(), max(420, available.height() - 60)),
            )
            geometry = self.frameGeometry()
            geometry.moveCenter(available.center())
            self.move(geometry.topLeft())
        self.font_combo.setFocus()

    # ------------------------------------------------------------------
    def _sync_key_layout(self) -> None:
        """La grille de l'éditeur suit la disposition choisie."""
        self.key_editor.set_layout(str(self.layout_combo.currentData() or "azerty"))

    def _make_page(self, *groups: QWidget, margin: int = 10) -> QScrollArea:
        """Page d'onglet : les groupes, dans une zone qui défile au besoin."""
        content = QWidget(self.tabs)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(10)
        for group in groups:
            layout.addWidget(group)
        layout.addStretch(1)

        page = QScrollArea(self.tabs)
        page.setWidgetResizable(True)
        page.setFrameShape(QFrame.Shape.NoFrame)
        page.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        page.setWidget(content)
        return page

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
            "show_mouse": self.show_mouse.isChecked(),
            "mouse_style": self.mouse_style_combo.currentData() or "classic",
            "mouse_tracking": self.mouse_tracking.isChecked(),
            "count_repeats": self.count_repeats.isChecked(),
            "cursor_style": self.cursor_style_combo.currentData() or "classic",
            **self.key_editor.values(),
            "transition": self.transition_combo.currentData() or "fade",
            "transition_out_ms": self.transition_duration.value(),
            "row_animation": self.animation_combo.currentData() or "fade",
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
            self.show_mouse.setChecked(defaults.show_mouse)
            index = self.mouse_style_combo.findData(defaults.mouse_style)
            self.mouse_style_combo.setCurrentIndex(index if index >= 0 else 0)
            self.mouse_tracking.setChecked(defaults.mouse_tracking)
            self.count_repeats.setChecked(defaults.count_repeats)
            index = self.cursor_style_combo.findData(defaults.cursor_style)
            self.cursor_style_combo.setCurrentIndex(index if index >= 0 else 0)
            index = self.transition_combo.findData(defaults.transition)
            self.transition_combo.setCurrentIndex(index if index >= 0 else 0)
            self.transition_duration.setValue(int(defaults.transition_out_ms))
            index = self.animation_combo.findData(defaults.row_animation)
            self.animation_combo.setCurrentIndex(index if index >= 0 else 0)
            self.key_editor.reset()
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

