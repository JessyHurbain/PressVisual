"""Fenêtre flottante affichant les frappes et les clics."""

from __future__ import annotations

import time
from typing import Iterable, Optional

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
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
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QScreen,
)
from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout, QWidget

from .appearance import AppearanceDialog, _choose_font_family
from .config import (
    APPEARANCE_CONFIG_KEYS,
    KEYBOARD_SCALE_MAX,
    KEYBOARD_SCALE_MIN,
    Config,
)
from .constants import APP_NAME
from .cursor import CursorBadge
from .events import KeyEvent, MouseEvent
from .i18n import _t
from .keyboard import InputView
from .keymap import (
    MODIFIER_ORDER,
    MULTI_CLICK_LABELS,
    POSITION_CHOICES,
    POSITION_LABELS,
    SLIDE_DIRECTIONS,
    key_label,
    key_shape_for,
    modifier_label,
    should_use_combo,
    transition_geometry,
)
from .mouse import MOUSE_SCROLL_FLASH_MS
from .theme import Palette, _with_alpha
from .widgets import KeyRow

#: Longueur maximale du tampon de texte affiché.
MAX_TEXT_LENGTH = 200
#: Fenêtre de temps (s) d'agrégation des événements de molette.
SCROLL_AGGREGATE_WINDOW = 0.9
#: Nombre maximal de touches allumées simultanément (sécurité anti-blocage).
KEYBOARD_MAX_LIT = 16
#: Côté de la zone de la poignée qui redimensionne le clavier (px).
RESIZE_GRIP_SIZE = 22

class Overlay(QWidget):
    """Fenêtre flottante affichant les frappes et les clics."""

    state_changed = pyqtSignal()
    language_changed = pyqtSignal(str)

    def __init__(self, config: Config) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self._cfg = config
        self._palette = Palette.from_config(config)
        self._rebuild_fonts()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle(APP_NAME)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 12, 16, 13)
        self._layout.setSpacing(7)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignBottom)

        # --- État interne ------------------------------------------------
        self._rows: list[KeyRow] = []
        self._text_row: Optional[KeyRow] = None
        self._text = ""
        self._combo_row: Optional[KeyRow] = None
        self._scroll_row: Optional[KeyRow] = None
        self._scroll_direction = 0
        self._scroll_axis = "vertical"
        self._scroll_count = 0
        self._scroll_time = 0.0
        self._scroll_mods: tuple[str, ...] = ()
        self._last_left_row: Optional[KeyRow] = None
        self._last_left_time = 0.0
        #: Dernière ligne d'appui : elle peut compter les appuis suivants.
        self._repeat_row: Optional[KeyRow] = None

        self._capture_enabled = not config.start_hidden
        self._click_through = False
        self._masked = False
        self._mode = "keyboard" if config.display_mode == "keyboard" else "overlay"
        self._kb_active: set[str] = set()
        self._kb_modifiers: set[str] = set()
        #: Côtés physiques (``ctrl_l``...) : un seul Ctrl s'allume.
        self._kb_modifier_sides: set[str] = set()
        self._mouse_buttons: set[str] = set()
        self._mouse_scroll: Optional[tuple[str, int]] = None
        #: Pastille près du pointeur (suivi de la souris), créée au premier usage.
        self._cursor_badge: Optional[CursorBadge] = None
        self._dragging = False
        self._drag_origin = QPoint(0, 0)
        self._resizing = False
        self._resize_start = QPoint(0, 0)
        self._resize_start_scale = 1.0
        self._resize_start_size = QSize(0, 0)
        self._fade_target = "idle"
        self._slide_target = "idle"
        # Transition en cours : "slide" (déplacement) ou "zoom" (échelle).
        self._slide_mode = ""
        self._slide_style = ""
        self._zoom_base: Optional[QRect] = None

        # Ancrage : bords conservés lors des changements de taille (coin
        # haut/bas, gauche/centre/droite).
        self._anchor_mode = "right"
        self._vertical_mode = "bottom"
        self._position_name = config.position
        self._anchor = QPoint(0, 0)

        # --- Animations et minuteries ------------------------------------
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.finished.connect(self._on_fade_finished)
        # Glissement et zoom : la bulle sort par un bord (ou rétrécit) puis
        # revient. Le déplacement et l'échelle sont appliqués nous-mêmes, pour
        # reprendre la main sur la géométrie dès l'animation terminée.
        self._slide = QVariantAnimation(self)
        self._slide.valueChanged.connect(self._slide_to)
        self._slide.finished.connect(self._on_slide_finished)
        self._slide_origin: Optional[QPoint] = None

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._fade_out)

        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._finish_text)

        # Un cran de molette n'a pas de relâchement : le sens affiché
        # s'éteint seul après un court délai.
        self._mouse_scroll_timer = QTimer(self)
        self._mouse_scroll_timer.setSingleShot(True)
        self._mouse_scroll_timer.timeout.connect(self._end_mouse_scroll)

        # Vue « clavier complet » : la disposition choisie, puis la souris.
        self._visual = InputView(
            self._cfg, self._badge_font, self._palette, self
        )
        self._keyboard = self._visual.keyboard
        self._mouse = self._visual.mouse
        if self._mode == "keyboard":
            self._layout.addWidget(self._visual)
        self._visual.set_mode_visible(self._mode == "keyboard")

        self._anchoring_ready = False
        self._snapping = False
        self.resize(320, 64)
        if not self._restore_free_position():
            self._reset_anchor_position(config.position)
        self._anchoring_ready = True
        self.setWindowOpacity(0.0)
        self.hide()

        if config.click_through_on_start:
            self.set_click_through(True, announce=False)

    # ------------------------------------------------------------------
    # Propriétés publiques (utilisées par le menu de notification)
    # ------------------------------------------------------------------
    @property
    def capture_enabled(self) -> bool:
        return self._capture_enabled

    @property
    def click_through(self) -> bool:
        return self._click_through

    @property
    def masked(self) -> bool:
        return self._masked

    @property
    def position_name(self) -> str:
        """Position préréglée courante (chaîne vide après un glisser)."""
        return self._position_name

    # ------------------------------------------------------------------
    # Apparence et peinture
    # ------------------------------------------------------------------
    def _rebuild_fonts(self) -> None:
        """Recalcule les polices à partir de la configuration."""
        self._font_family = _choose_font_family(self._cfg)

        self._badge_font = QFont(self._font_family)
        self._badge_font.setPointSize(max(9, self._cfg.font_size - 1))
        self._badge_font.setWeight(QFont.Weight.DemiBold)
        self._badge_font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing, 0.3
        )

        self._text_font = QFont(self._font_family)
        self._text_font.setPointSize(self._cfg.font_size)
        self._text_font.setWeight(QFont.Weight.Medium)
        self._text_metrics = QFontMetrics(self._text_font)

        visual = getattr(self, "_visual", None)
        if visual is not None:
            visual.set_font(self._badge_font)
        badge = getattr(self, "_cursor_badge", None)
        if badge is not None:
            badge.set_font(self._badge_font)

    def apply_appearance(self, values: dict[str, object]) -> None:
        """Applique de nouveaux réglages d'apparence à l'overlay."""
        for key, value in values.items():
            if hasattr(self._cfg, key) and key != "path":
                setattr(self._cfg, key, value)
        self._cfg.validate()

        self._rebuild_fonts()
        self._palette.update_from_config(self._cfg)
        if self._cursor_badge is not None:
            self._cursor_badge.set_palette(self._palette)
            self._cursor_badge.set_style(self._cfg.cursor_style)
            self._cursor_badge.set_mouse_style(self._cfg.mouse_style)
            self._cursor_badge.set_font(self._badge_font)
            if not self._cfg.mouse_tracking:
                self._cursor_badge.hide_badge()
        for row in self._rows:
            row.set_font(self._badge_font)
        if self._text_row is not None:
            self._render_text()
        self._apply_display_mode()

        # Une marge différente doit replacer un coin préréglé ; un
        # déplacement libre conserve sa position.
        if self._position_name:
            screen = QGuiApplication.screenAt(self._anchor)
            if screen is None:
                screen = QGuiApplication.screenAt(self.frameGeometry().center())
            self._reset_anchor_position(self._position_name, screen)
        self._relayout()
        self.update()

    # ------------------------------------------------------------------
    # Mode d'affichage
    # ------------------------------------------------------------------
    def _apply_display_mode(self) -> None:
        """Bascule entre les pastilles et le clavier complet."""
        mode = "keyboard" if self._cfg.display_mode == "keyboard" else "overlay"
        self._visual.set_config(self._cfg)
        self._visual.set_font(self._badge_font)
        self._visual.set_mode_visible(mode == "keyboard")
        self._keyboard.set_masked(self._masked)

        if mode == self._mode:
            self._relayout()
            return

        self._mode = mode
        self._clear_rows()
        self._clear_keyboard()
        if mode == "keyboard":
            self._layout.addWidget(self._visual)
        else:
            self._layout.removeWidget(self._visual)
        self._relayout()

    def _press_key(self, event: KeyEvent) -> None:
        """Allume la touche pressée ; elle s'éteint au relâchement."""
        self._kb_active.add(event.token)
        # Une relâche manquée (changement de fenêtre, raccourci système) ne
        # doit pas laisser le clavier éclairé indéfiniment.
        if len(self._kb_active) > KEYBOARD_MAX_LIT:
            self._kb_active = {event.token}
        self._apply_keyboard_state()
        self._bump()

    def _on_key_release(self, token: str) -> None:
        """Éteint la touche dès qu'elle est relâchée."""
        if self._mode != "keyboard":
            return
        if token in self._kb_active:
            self._kb_active.discard(token)
            self._apply_keyboard_state()

    def _clear_keyboard(self) -> None:
        """Éteint toutes les touches du clavier et les boutons de la souris."""
        self._kb_active.clear()
        self._kb_modifier_sides.clear()
        self._clear_mouse()
        self._apply_keyboard_state()

    def _clear_mouse(self) -> None:
        """Éteint les boutons de la souris et le sens du défilement."""
        self._mouse_buttons.clear()
        self._mouse_scroll = None
        self._mouse_scroll_timer.stop()

    def _apply_keyboard_state(self) -> None:
        self._keyboard.set_masked(self._masked)
        self._keyboard.set_modifiers(self._kb_modifiers)
        self._keyboard.set_modifier_sides(self._kb_modifier_sides)
        self._keyboard.set_active(self._kb_active)
        self._mouse.set_buttons(self._mouse_buttons)
        if self._mouse_scroll is None:
            self._mouse.clear_scroll()
        else:
            self._mouse.set_scroll(*self._mouse_scroll)

    # ------------------------------------------------------------------
    # Peinture et déplacement
    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = float(self._cfg.corner_radius)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        background_alpha = int(round(255 * self._cfg.opacity))
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        top = QColor(self._palette.panel_top)
        top.setAlpha(background_alpha)
        bottom = QColor(self._palette.panel_bottom)
        bottom.setAlpha(background_alpha)
        gradient.setColorAt(0.0, top)
        gradient.setColorAt(1.0, bottom)

        painter.fillPath(path, gradient)
        painter.setPen(
            QPen(
                self._palette.border_drag
                if self._dragging or self._resizing
                else self._palette.border,
                1.0,
            )
        )
        painter.drawPath(path)
        self._paint_resize_grip(painter)

    def _paint_resize_grip(self, painter: QPainter) -> None:
        """Poignée du coin : glisser dessus règle la taille du clavier."""
        if self._mode != "keyboard":
            return
        inset = 7.0
        right = self.width() - inset
        bottom = self.height() - inset
        painter.setPen(
            QPen(
                _with_alpha(self._palette.text, 0.45 if self._resizing else 0.30),
                1.4,
            )
        )
        for offset in (0.0, 4.0, 8.0):
            painter.drawLine(
                QPointF(right - offset, bottom), QPointF(right, bottom - offset)
            )

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        # Le redimensionnement du layout peut survenir après le calcul de la
        # position (Qt différe parfois l'application de la taille) : on
        # réapplique l'ancrage avec la taille définitive.
        super().resizeEvent(event)
        # Pendant un zoom, la taille change volontairement : c'est
        # l'animation qui place la fenêtre, pas l'ancrage.
        if self._anchoring_ready and not self._dragging and not self._slide_mode:
            self._apply_anchor()

    def moveEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().moveEvent(event)
        # La plateforme graphique applique parfois en différé la géométrie
        # d'une animation terminée : une fenêtre masquée est ramenée à sa
        # place pour que la prochaine apparition parte du bon endroit.
        if (
            self._anchoring_ready
            and not self.isVisible()
            and not self._dragging
            and not self._slide_mode
            and not self._snapping
        ):
            self._snapping = True
            try:
                self._apply_anchor()
            finally:
                self._snapping = False

    def _resize_to(self, cursor: QPoint) -> None:
        """Règle la taille du clavier d'après le glisser de la poignée.

        Le glisser se mesure depuis l'appui, dans la direction la plus
        marquée : horizontalement ou verticalement, au choix.
        """
        width = max(1, self._resize_start_size.width())
        height = max(1, self._resize_start_size.height())
        dx = cursor.x() - self._resize_start.x()
        dy = cursor.y() - self._resize_start.y()
        ratio = (
            (width + dx) / width
            if abs(dx) >= abs(dy)
            else (height + dy) / height
        )
        scale = min(
            KEYBOARD_SCALE_MAX,
            max(KEYBOARD_SCALE_MIN, self._resize_start_scale * ratio),
        )
        if abs(scale - self._cfg.keyboard_scale) < 0.005:
            return
        self._cfg.keyboard_scale = round(scale, 3)
        self._visual.set_scale(self._cfg.keyboard_scale)
        self._relayout()

    def _grip_rect(self) -> QRect:
        """Zone de la poignée, dans le coin bas droit de la bulle."""
        return QRect(
            self.width() - RESIZE_GRIP_SIZE,
            self.height() - RESIZE_GRIP_SIZE,
            RESIZE_GRIP_SIZE,
            RESIZE_GRIP_SIZE,
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            if self._mode == "keyboard" and self._grip_rect().contains(
                event.position().toPoint()
            ):
                self._resizing = True
                self._resize_start = event.globalPosition().toPoint()
                self._resize_start_scale = self._cfg.keyboard_scale
                self._resize_start_size = self.size()
                self._hold_visible()
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                self.update()
                event.accept()
                return
            self._drag_origin = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self._dragging = True
            self._hold_visible()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - API Qt
        if self._resizing and event.buttons() & Qt.MouseButton.LeftButton:
            self._resize_to(event.globalPosition().toPoint())
            event.accept()
            return
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - API Qt
        if self._resizing and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()
            self._relayout()
            # La taille choisie est conservée au prochain lancement.
            self._cfg.remember_keyboard_scale(self._cfg.keyboard_scale)
            self._bump()
            event.accept()
            return
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._snap_anchor_to_position()
            self.update()
            # Rattrape un éventuel changement de contenu pendant le glisser.
            self._relayout()
            # Mémorise la position choisie pour le prochain lancement.
            self._cfg.remember_free_position(
                self.x(), self.y(), self.width(), self.height()
            )
            # La bulle reste affichée un délai complet après avoir été posée.
            self._bump()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _hold_visible(self) -> None:
        """Empêche la bulle de s'effacer pendant un déplacement manuel.

        Le minuteur de disparition est suspendu tant que le bouton reste
        enfoncé, et une transition déjà commencée est annulée.
        """
        self._idle_timer.stop()
        if not self._transition_running("out"):
            return
        self._fade.stop()
        self._slide.stop()
        self._fade_target = "idle"
        self._slide_target = "idle"
        self._reset_transition_state()

    def _restore_free_position(self) -> bool:
        """Replace la bulle à la position libre mémorisée, si elle existe."""
        if self._cfg.free_position is None:
            return False
        x, y, width, height = self._cfg.free_position
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(width, available.width())
            height = min(height, available.height())
        self.setGeometry(int(x), int(y), int(width), int(height))
        self._snap_anchor_to_position()
        # Ramène la bulle dans la zone visible si l'écran a changé depuis.
        self._apply_anchor()
        return True

    def _snap_anchor_to_position(self) -> None:
        """Conserve les bords proches du centre de l'écran après un glisser.

        La bulle grandit ainsi vers le centre de l'écran plutôt que de sortir
        par un bord lorsqu'elle est déposée dans un coin.
        """
        screen = QGuiApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        center = self.frameGeometry().center()
        if center.x() >= available.center().x():
            self._anchor_mode = "right"
            x = self.x() + self.width()
        else:
            self._anchor_mode = "left"
            x = self.x()
        if center.y() >= available.center().y():
            self._vertical_mode = "bottom"
            y = self.y() + self.height()
        else:
            self._vertical_mode = "top"
            y = self.y()
        self._anchor = QPoint(x, y)
        # Position libre : aucun préréglage de coin n'est plus sélectionné.
        self._position_name = ""
        self.state_changed.emit()

    # ------------------------------------------------------------------
    # Positionnement
    # ------------------------------------------------------------------
    def set_position(self, position: str, announce: bool = True) -> None:
        """Place l'overlay dans un coin et mémorise ce choix."""
        if position not in POSITION_CHOICES:
            position = (
                self._cfg.position
                if self._cfg.position in POSITION_CHOICES
                else "bottom-right"
            )
        self._cfg.position = position
        self._reset_anchor_position(position)
        self._relayout()
        self._cfg.remember_position(position)
        if announce:
            self._status(
                _t("Position : {label}").format(
                    label=_t(POSITION_LABELS.get(position, position))
                )
            )
        self.state_changed.emit()

    def _reset_anchor_position(
        self, position: str, screen: Optional[QScreen] = None
    ) -> None:
        if position not in POSITION_CHOICES:
            position = "bottom-right"
        self._position_name = position
        self._anchor_mode = (
            "center"
            if position == "bottom-center"
            else "right"
            if position.endswith("right")
            else "left"
        )
        self._vertical_mode = "top" if position.startswith("top") else "bottom"

        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        margin = self._cfg.margin

        if self._vertical_mode == "top":
            y = available.top() + margin
        else:
            y = available.bottom() - margin + 1

        if self._anchor_mode == "center":
            x = available.center().x()
        elif self._anchor_mode == "right":
            x = available.right() - margin + 1
        else:
            x = available.left() + margin

        self._anchor = QPoint(x, y)

    def _apply_anchor(self) -> None:
        screen = QGuiApplication.screenAt(self._anchor)
        if screen is None:
            screen = QGuiApplication.screenAt(self.frameGeometry().center())
        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()
        width, height = self.width(), self.height()

        if self._anchor_mode == "center":
            x = self._anchor.x() - width // 2
        elif self._anchor_mode == "left":
            x = self._anchor.x()
        else:
            x = self._anchor.x() - width
        if self._vertical_mode == "top":
            y = self._anchor.y()
        else:
            y = self._anchor.y() - height

        max_x = available.right() - width + 1
        max_y = available.bottom() - height + 1
        x = max(available.left(), min(x, max_x))
        y = max(available.top(), min(y, max_y))
        self.move(int(x), int(y))

    def _relayout(self) -> None:
        if self._dragging:
            return
        self._layout.invalidate()
        self.adjustSize()
        self._apply_anchor()
        self.update()

    # ------------------------------------------------------------------
    # Rafraîchissement / minuteries
    # ------------------------------------------------------------------
    def _bump(self) -> None:
        """Relance le délai de disparition et affiche la fenêtre."""
        if not self._capture_enabled:
            return
        self._idle_timer.start(int(self._cfg.display_duration * 1000))
        self._fade_in()

    def _transition_running(self, direction: str) -> bool:
        """Une transition (fondu, glissement ou zoom) est-elle en cours ?"""
        running = QAbstractAnimation.State.Running
        return (
            self._fade.state() == running and self._fade_target == direction
        ) or (
            self._slide.state() == running and self._slide_target == direction
        )

    def _transition_duration(self) -> int:
        """Durée de la transition de disparition, en millisecondes."""
        if self._cfg.transition == "none":
            return 0
        return max(0, int(self._cfg.transition_out_ms))

    def _entry_duration(self) -> int:
        """Durée de l'apparition.

        Elle reprend la même transition mais reste brève (``transition_in_ms``)
        pour qu'une frappe allume la bulle sans délai perceptible ; une
        durée de disparition plus courte s'applique telle quelle.
        """
        duration = self._transition_duration()
        if duration <= 0:
            return 0
        return min(max(0, int(self._cfg.transition_in_ms)), duration)

    def _fade_in(self) -> None:
        """Affiche la bulle avec la transition d'apparition choisie."""
        if self._transition_running("in"):
            return

        self._fade.stop()
        self._slide.stop()
        self._fade_target = "in"
        self._slide_target = "idle"
        # Une disparition en cours est annulée : la bulle retrouve tout de
        # suite sa position et sa taille, sans rester à moitié sortie.
        self._reset_transition_state()

        if self.isVisible():
            return

        self._relayout()
        self.show()
        self._start_entry()

    def _start_entry(self) -> None:
        """Anime l'apparition depuis le bord choisi, ou par zoom."""
        duration = self._entry_duration()
        transition = self._cfg.transition
        if duration <= 0 or transition == "none":
            self.setWindowOpacity(1.0)
            return

        if transition in SLIDE_DIRECTIONS:
            self._slide_mode = "slide"
            self._slide_style = transition
            self._slide_origin = self.pos()
            self._slide.setDuration(duration)
            self._slide.setStartValue(1.0)
            self._slide.setEndValue(0.0)
            self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._slide_to(1.0)
            self._slide_target = "in"
            self._slide.start()
            return

        if transition == "zoom":
            self._slide_mode = "zoom"
            self._zoom_base = QRect(self.geometry())
            # La taille minimale imposée par le contenu empêcherait de
            # rétrécir : elle est relâchée le temps du zoom.
            self.setMinimumSize(1, 1)
            self._slide.setDuration(duration)
            self._slide.setStartValue(1.0)
            self._slide.setEndValue(0.0)
            self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._slide_to(1.0)
            self._slide_target = "in"
            self._slide.start()
            return

        self.setWindowOpacity(0.0)
        self._fade.setDuration(duration)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()

    def _fade_out(self) -> None:
        """Fait disparaître la bulle selon la transition configurée."""
        if not self.isVisible():
            return
        self._fade.stop()
        self._slide.stop()
        self._fade_target = "idle"
        self._slide_target = "idle"
        self._idle_timer.stop()
        # La sortie part toujours de la bulle en place, à taille pleine :
        # une apparition interrompue ne doit pas gauchir le point de départ.
        self._reset_transition_state()

        duration = self._transition_duration()
        transition = self._cfg.transition
        if duration == 0 or transition == "none":
            self._finish_hiding()
            return

        if transition in SLIDE_DIRECTIONS:
            self._slide_mode = "slide"
            self._slide_style = transition
            self._slide_origin = self.pos()
            self._slide.setDuration(duration)
            self._slide.setStartValue(0.0)
            self._slide.setEndValue(1.0)
            self._slide.setEasingCurve(QEasingCurve.Type.InCubic)
            self._slide_target = "out"
            self._slide.start()
            return

        if transition == "zoom":
            self._slide_mode = "zoom"
            self._zoom_base = QRect(self.geometry())
            self.setMinimumSize(1, 1)
            self._slide.setDuration(duration)
            self._slide.setStartValue(0.0)
            self._slide.setEndValue(1.0)
            self._slide.setEasingCurve(QEasingCurve.Type.InCubic)
            self._slide_target = "out"
            self._slide.start()
            return

        self._fade_target = "out"
        self._fade.setDuration(duration)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade.start()

    def _end_zoom(self) -> None:
        """Rend à la bulle sa taille pleine, après un zoom."""
        if self._slide_mode != "zoom":
            return
        if self._zoom_base is not None:
            self.setGeometry(self._zoom_base)
        self._zoom_base = None
        # Rend la main au layout, qui réimpose la taille minimale du contenu.
        self.setMinimumSize(0, 0)

    def _reset_transition_state(self) -> None:
        """Remet la bulle à sa place et à sa taille, opacité pleine."""
        self._end_zoom()
        self.setWindowOpacity(1.0)
        self._slide_mode = ""
        self._slide_style = ""
        self._slide_origin = None
        if self.isVisible():
            self._apply_anchor()

    def _on_fade_finished(self) -> None:
        if self._fade_target != "out":
            return
        self._finish_hiding()

    def _on_slide_finished(self) -> None:
        if self._slide_target == "out":
            self._finish_hiding()
            return
        self._slide_target = "idle"
        self._reset_transition_state()

    def _finish_hiding(self) -> None:
        """Termine la disparition : fenêtre masquée, contenu éteint."""
        self._fade.stop()
        self._slide.stop()
        self._fade_target = "idle"
        self._slide_target = "idle"
        self.hide()
        # Un zoom a réduit la fenêtre : elle retrouve sa taille pleine avant
        # de revenir à sa position d'ancrage.
        self._end_zoom()
        self._slide_mode = ""
        self._slide_style = ""
        self._slide_origin = None
        self.setWindowOpacity(1.0)
        self._clear_rows()
        self._clear_keyboard()
        # Après un glissement, la bulle reprend sa place pour la prochaine
        # fois ; un second passage rattrape le déplacement que la plateforme
        # graphique applique encore après la fin de l'animation.
        self._apply_anchor()
        QTimer.singleShot(0, self._restore_position)

    def _restore_position(self) -> None:
        """Remet la bulle à sa position d'ancrage, sans la réafficher."""
        if not self.isVisible():
            self._apply_anchor()

    def _slide_to(self, progress: float) -> None:
        """Applique l'avancement de la transition (0 = bulle en place)."""
        value = float(progress)
        if self._slide_mode == "zoom":
            base = self._zoom_base
            if base is None:
                return
            _, _, scale, opacity = transition_geometry(
                "zoom", base.width(), base.height(), value
            )
            width = max(1, int(round(base.width() * scale)))
            height = max(1, int(round(base.height() * scale)))
            self.setGeometry(
                base.x() + (base.width() - width) // 2,
                base.y() + (base.height() - height) // 2,
                width,
                height,
            )
            self.setWindowOpacity(max(0.0, min(1.0, opacity)))
            return

        if self._slide_mode != "slide" or self._slide_origin is None:
            return
        dx, dy, _, _ = transition_geometry(
            self._slide_style, self.width(), self.height(), value
        )
        self.move(
            self._slide_origin.x() + int(round(dx)),
            self._slide_origin.y() + int(round(dy)),
        )

    def _hide_now(self) -> None:
        self._fade.stop()
        self._slide.stop()
        self._fade_target = "idle"
        self._slide_target = "idle"
        self._end_zoom()
        self._slide_mode = ""
        self._slide_style = ""
        self._slide_origin = None
        self._idle_timer.stop()
        self._typing_timer.stop()
        # La bulle s'efface : les appuis suivants repartent d'un compte neuf.
        self._repeat_row = None
        if self._cursor_badge is not None:
            self._cursor_badge.hide_badge()
        self.hide()
        self.setWindowOpacity(1.0)
        self._apply_anchor()

    def closeEvent(self, event) -> None:  # noqa: N802 - API Qt
        """Referme la pastille du curseur avec la fenêtre."""
        if self._cursor_badge is not None:
            self._cursor_badge.close()
            self._cursor_badge = None
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Lignes de l'overlay
    # ------------------------------------------------------------------
    def _new_row(self, items: Iterable[tuple[str, str]]) -> KeyRow:
        row = KeyRow(
            self._badge_font,
            self._palette,
            self,
            # La bulle suit les formes de l'éditeur de touches ; la règle est
            # relue à chaque badge pour qu'un réglage s'applique sans
            # reconstruire les lignes.
            shape_for=lambda label: key_shape_for(self._cfg, label),
        )
        row.set_items(items)
        self._rows.append(row)
        self._layout.addWidget(row)
        self._trim_rows()
        self._update_levels()
        self._relayout()
        self._bump()
        return row

    def _merge_repeat(self, row: KeyRow) -> None:
        """Absorbe une ligne identique à la précédente en « ×N ».

        Deux appuis de suite sur la même touche ne doivent pas empiler deux
        pastilles identiques : la première compte les appuis. Une touche
        intercalée, un texte, une ligne de souris ou un passage masqué
        interrompt le compte.
        """
        previous = self._repeat_target(row)
        if previous is None:
            self._repeat_row = row
            return
        self._remove_row(row)
        # Le premier compteur vaut « ×2 » : la pastille gardée est le premier
        # appui, la ligne absorbée est le second.
        previous.set_count(max(2, previous.count + 1))
        self._repeat_row = previous
        self._update_levels()
        self._relayout()
        self._bump()

    def _repeat_target(self, row: KeyRow) -> Optional[KeyRow]:
        """Ligne qui peut compter l'appui, si c'est bien le même."""
        if not self._cfg.count_repeats or row not in self._rows:
            return None
        items = row.items
        if not items or any(kind == "text" for _, kind in items):
            return None
        index = self._rows.index(row)
        if index == 0:
            return None
        previous = self._rows[index - 1]
        # Seule la ligne de l'appui précédent compte : après une autre touche
        # ou un passage masqué, l'appui repart de un.
        if previous is not self._repeat_row or previous.items != items:
            return None
        return previous

    def _remove_row(self, row: Optional[KeyRow]) -> None:
        if row is None or row not in self._rows:
            return
        self._rows.remove(row)
        self._layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        if row is self._text_row:
            self._text_row = None
            self._text = ""
        if row is self._combo_row:
            self._combo_row = None
        if row is self._scroll_row:
            self._scroll_row = None
        if row is self._last_left_row:
            self._last_left_row = None
        if row is self._repeat_row:
            self._repeat_row = None
        self._update_levels()
        self._relayout()

    def _trim_rows(self) -> None:
        while len(self._rows) > self._cfg.max_rows:
            old = self._rows.pop(0)
            self._layout.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
            if old is self._text_row:
                self._text_row = None
                self._text = ""
            if old is self._combo_row:
                self._combo_row = None
            if old is self._scroll_row:
                self._scroll_row = None
            if old is self._last_left_row:
                self._last_left_row = None
            if old is self._repeat_row:
                self._repeat_row = None

    def _update_levels(self) -> None:
        levels = (1.0, 0.62, 0.34)
        count = len(self._rows)
        for index, row in enumerate(self._rows):
            depth = count - 1 - index
            row.set_alpha(levels[min(depth, len(levels) - 1)])

    def _clear_rows(self) -> None:
        for row in self._rows:
            self._layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        self._text_row = None
        self._text = ""
        self._combo_row = None
        self._scroll_row = None
        self._last_left_row = None
        self._repeat_row = None
        self._typing_timer.stop()
        self._relayout()

    # ------------------------------------------------------------------
    # Construction des badges
    # ------------------------------------------------------------------
    def _combo_items(
        self,
        mods: Iterable[str],
        key: Optional[str] = None,
        key_kind: str = "key",
    ) -> list[tuple[str, str]]:
        parts: list[tuple[str, str]] = [
            (modifier_label(self._cfg, mod), "mod")
            for mod in MODIFIER_ORDER
            if mod in set(mods)
        ]
        if key is not None:
            parts.append((key, key_kind))

        items: list[tuple[str, str]] = []
        for index, part in enumerate(parts):
            if index:
                items.append(("+", "plus"))
            items.append(part)
        return items

    def _mouse_items(
        self, mods: Iterable[str], label: str
    ) -> list[tuple[str, str]]:
        """Badges d'un clic ou d'un cran de molette, modificateurs compris."""
        return self._combo_items(mods, label, key_kind="mouse")

    def _event_key_label(self, event: KeyEvent) -> str:
        if event.char:
            return event.char.upper() if len(event.char) == 1 else event.char
        return key_label(self._cfg, event.token)

    def _fit_text(self, text: str) -> str:
        """Tronque le début du texte pour tenir dans la largeur maximale."""
        if not text:
            return ""
        limit = max(140, self._cfg.max_width - 40)
        if self._text_metrics.horizontalAdvance(text) <= limit:
            return text
        trimmed = text
        while trimmed and self._text_metrics.horizontalAdvance("… " + trimmed) > limit:
            trimmed = trimmed[1:]
        return "… " + trimmed if trimmed else "…"

    # ------------------------------------------------------------------
    # Texte continu
    # ------------------------------------------------------------------
    def _add_text_char(self, char: str) -> None:
        if self._masked:
            char = "•"

        if self._text_row is None and not self._text:
            if char.isspace():
                return
            self._text_row = self._new_row([])
            self._text = char
        else:
            self._text += char
            if len(self._text) > MAX_TEXT_LENGTH:
                self._text = self._text[-MAX_TEXT_LENGTH:]

        self._render_text()
        self._typing_timer.start(int(self._cfg.typing_join_delay * 1000))
        self._bump()

    def _render_text(self) -> None:
        if self._text_row is None:
            return
        display = self._fit_text(self._text.rstrip())
        self._text_row.set_items([(display, "text")] if display else [])
        self._relayout()

    def _finish_text(self) -> None:
        self._typing_timer.stop()
        if self._text_row is None:
            return
        text = self._text.rstrip()
        if text:
            self._text_row.set_items([(self._fit_text(text), "text")])
        else:
            self._remove_row(self._text_row)
        self._text_row = None
        self._text = ""
        self._relayout()

    def _flush_typing(self) -> None:
        if self._text_row is not None or self._text:
            self._finish_text()

    # ------------------------------------------------------------------
    # Combinaisons et touches spéciales
    # ------------------------------------------------------------------
    def _close_combo(self, remove: bool = False) -> None:
        row = self._combo_row
        self._combo_row = None
        if row is not None and remove:
            self._remove_row(row)

    def cancel_live_combo(self) -> None:
        """Retire la ligne de modificateurs en cours (raccourci global)."""
        self._close_combo(remove=True)

    def _on_modifiers(self, mods: Iterable[str]) -> None:
        if not self._capture_enabled:
            return
        snapshot = tuple(m for m in MODIFIER_ORDER if m in set(mods))

        if self._mode == "keyboard":
            self._kb_modifiers = set(snapshot)
            self._apply_keyboard_state()
            if snapshot:
                self._bump()
            return

        if self._combo_row is not None:
            if not snapshot:
                # Modificateurs relâchés sans touche : la ligne reste affichée.
                self._combo_row = None
                self._bump()
                return
            self._combo_row.set_items(self._combo_items(snapshot))
            self._update_levels()
            self._relayout()
            self._bump()
            return

        if not snapshot:
            return
        # Maj seul ne crée pas de bulle : il accompagne une touche ou du texte.
        if not ({"ctrl", "alt", "win"} & set(snapshot)):
            return

        self._flush_typing()
        self._combo_row = self._new_row(self._combo_items(snapshot))
        self._bump()

    def _on_modifier_sides(self, sides: Iterable[str]) -> None:
        """Retient les côtés physiques enfoncés (``ctrl_l``, ``shift_r``...)."""
        if not self._capture_enabled:
            return
        self._kb_modifier_sides = set(sides)
        if self._mode == "keyboard":
            self._apply_keyboard_state()

    def _on_key(self, event: KeyEvent) -> None:
        if not self._capture_enabled:
            return
        if self._mode == "keyboard":
            self._press_key(event)
            return

        mods = tuple(m for m in MODIFIER_ORDER if m in set(event.mods))
        plain = not ({"ctrl", "alt", "win"} & set(mods))

        # Retour arrière : édite le texte affiché s'il est encore en cours.
        if (
            self._cfg.concat_text
            and event.token == "backspace"
            and plain
            and self._text_row is not None
        ):
            self._close_combo()
            self._scroll_row = None
            self._text = self._text[:-1]
            if self._text:
                self._render_text()
                self._typing_timer.start(int(self._cfg.typing_join_delay * 1000))
                self._bump()
            else:
                row = self._text_row
                self._text_row = None
                self._remove_row(row)
                self._bump()
            return

        # Espace : prolonge le mot en cours, ou s'affiche seul en début de ligne.
        if self._cfg.concat_text and event.token == "space" and plain:
            self._close_combo()
            self._scroll_row = None
            if self._text_row is None and not self._text:
                self._merge_repeat(
                    self._new_row([(key_label(self._cfg, "space"), "key")])
                )
            else:
                self._add_text_char(" ")
            return

        if event.char and not should_use_combo(mods, event.char):
            # Caractère accentué alors que Ctrl/Alt sont enfoncés : il s'agit
            # d'AltGr. La ligne de modificateurs affichée était transitoire.
            if ord(event.char) > 0x7F and ({"ctrl", "alt"} & set(mods)):
                self._close_combo(remove=True)
            else:
                self._close_combo()
            self._scroll_row = None
            if self._cfg.concat_text:
                self._add_text_char(event.char)
            else:
                # Mode touche par touche : une pastille par caractère.
                label = "•" if self._masked else event.char
                self._merge_repeat(self._new_row([(label, "key")]))
            return

        # Touche spéciale (Entrée, Tab, flèches...) ou combinaison.
        self._flush_typing()
        self._scroll_row = None
        items = self._combo_items(mods, self._event_key_label(event))

        if self._combo_row is not None:
            row = self._combo_row
            self._combo_row = None
            row.set_items(items)
            self._update_levels()
            self._relayout()
            self._bump()
            self._merge_repeat(row)
        else:
            self._merge_repeat(self._new_row(items))

    # ------------------------------------------------------------------
    # Souris
    # ------------------------------------------------------------------
    def _on_mouse(self, event: MouseEvent) -> None:
        if not self._capture_enabled or not self._cfg.capture_mouse:
            return

        # Un clic sur la bulle elle-même ne doit pas s'afficher lorsqu'on
        # demande d'ignorer les clics faits sur l'overlay.
        ignores_overlay = (
            self._cfg.ignore_overlay_clicks
            and not self._click_through
            and self.isVisible()
        )
        if ignores_overlay and self.geometry().contains(QPoint(event.x, event.y)):
            return

        # Suivi de la souris : le clic ou le cran s'affiche près du pointeur.
        if self._cfg.mouse_tracking and (
            event.kind == "scroll" or (event.kind == "click" and event.button)
        ):
            self._show_cursor_event(event)

        # Le mode clavier n'affiche ni texte ni pastilles : la souris allume
        # ses boutons sur le schéma au lieu de créer une ligne.
        if self._mode == "keyboard":
            self._on_mouse_visual(event)
            return

        if self._cfg.mouse_tracking:
            # Le geste est déjà montré près du curseur : pas de doublon dans
            # la bulle.
            return

        if event.kind == "scroll":
            self._on_scroll(event)
            return
        if event.kind == "click" and event.button:
            self._on_click(event)

    # ------------------------------------------------------------------
    # Suivi de la souris : pastille près du pointeur
    # ------------------------------------------------------------------
    def _cursor_indicator(self) -> CursorBadge:
        """Pastille du curseur, créée au premier clic affiché."""
        if self._cursor_badge is None:
            self._cursor_badge = CursorBadge(
                self._palette,
                self._badge_font,
                self._cfg.cursor_style,
                self._cfg.mouse_style,
            )
        return self._cursor_badge

    def _show_cursor_event(self, event: MouseEvent) -> None:
        """Allume près du pointeur le bouton ou le cran qui vient d'agir.

        La pastille dessine une souris : elle n'a besoin que du geste et des
        modificateurs tenus, pas du libellé de la bulle.
        """
        mods = tuple(m for m in MODIFIER_ORDER if m in set(event.mods))
        chips = [modifier_label(self._cfg, name) for name in mods]
        badge = self._cursor_indicator()
        if event.kind == "scroll":
            axis = event.axis or "vertical"
            direction = 1 if event.direction >= 0 else -1
            badge.show_event(scroll=(axis, direction), chips=tuple(chips))
            return

        button = event.button or "left"
        if button == "left" and event.count >= 2:
            chips.append(f"×{event.count}")
        badge.show_event(button=button, chips=tuple(chips))

    # ------------------------------------------------------------------
    # Souris du mode clavier
    # ------------------------------------------------------------------
    def _on_mouse_visual(self, event: MouseEvent) -> None:
        """Allume le bouton enfoncé ou le sens du défilement."""
        if event.kind == "click" and event.button:
            self._mouse_buttons.add(event.button)
            self._apply_keyboard_state()
            self._bump()
        elif event.kind == "scroll":
            axis = event.axis or "vertical"
            self._mouse_scroll = (axis, 1 if event.direction >= 0 else -1)
            self._apply_keyboard_state()
            self._mouse_scroll_timer.start(MOUSE_SCROLL_FLASH_MS)
            self._bump()

    def _on_mouse_release(self, button: str) -> None:
        """Éteint le bouton dès qu'il est relâché."""
        if self._mode != "keyboard":
            return
        if button in self._mouse_buttons:
            self._mouse_buttons.discard(button)
            self._apply_keyboard_state()

    def _end_mouse_scroll(self) -> None:
        """Éteint l'indicateur de défilement après son court délai."""
        if self._mouse_scroll is None:
            return
        self._mouse_scroll = None
        self._apply_keyboard_state()

    def _on_scroll(self, event: MouseEvent) -> None:
        now = time.monotonic()
        mods = tuple(m for m in MODIFIER_ORDER if m in set(event.mods))
        axis = event.axis or "vertical"
        recent = (
            self._scroll_row is not None
            and self._rows
            and self._rows[-1] is self._scroll_row
            and event.direction == self._scroll_direction
            and axis == self._scroll_axis
            and mods == self._scroll_mods
            and now - self._scroll_time <= SCROLL_AGGREGATE_WINDOW
        )
        if recent:
            self._scroll_count += 1
            self._scroll_time = now
            base = self._scroll_label(axis, self._scroll_direction)
            self._scroll_row.set_items(
                self._mouse_items(mods, f"{base} ×{self._scroll_count}")
            )
            self._update_levels()
            self._relayout()
            self._bump()
            return

        self._flush_typing()
        self._close_combo(remove=True)
        self._scroll_direction = event.direction
        self._scroll_axis = axis
        self._scroll_count = 1
        self._scroll_time = now
        self._scroll_mods = mods
        base = self._scroll_label(axis, event.direction)
        self._scroll_row = self._new_row(self._mouse_items(mods, base))
        self._last_left_row = None

    def _scroll_label(self, axis: str, direction: int) -> str:
        """Libellé d'un cran de molette, selon l'axe et le sens."""
        if axis == "horizontal":
            label = (
                self._cfg.scroll_right_label
                if direction > 0
                else self._cfg.scroll_left_label
            )
        else:
            label = (
                self._cfg.scroll_up_label
                if direction > 0
                else self._cfg.scroll_down_label
            )
        return _t(label)

    def _click_label(self, event: MouseEvent) -> str:
        """Libellé d'un clic, selon le bouton et le nombre de clics."""
        button = event.button or "left"
        if button == "right":
            return _t(self._cfg.click_right_label)
        if button == "middle":
            return _t(self._cfg.click_middle_label)
        if button == "back":
            return _t(self._cfg.click_back_label)
        if button == "forward":
            return _t(self._cfg.click_forward_label)
        if event.count >= 2:
            return _t(MULTI_CLICK_LABELS.get(event.count, MULTI_CLICK_LABELS[3]))
        return _t(self._cfg.click_left_label)

    def _on_click(self, event: MouseEvent) -> None:
        button = event.button or "left"
        now = time.monotonic()
        mods = tuple(m for m in MODIFIER_ORDER if m in set(event.mods))

        # Double / triple clic : on enrichit la ligne du clic précédent au lieu
        # d'empiler une nouvelle ligne.
        if (
            button == "left"
            and event.count >= 2
            and self._last_left_row is not None
            and self._last_left_row in self._rows
            and now - self._last_left_time <= 0.9
        ):
            label = _t(MULTI_CLICK_LABELS.get(event.count, MULTI_CLICK_LABELS[3]))
            self._last_left_row.set_items(self._mouse_items(mods, label))
            self._last_left_time = now
            self._update_levels()
            self._relayout()
            self._bump()
            return

        self._flush_typing()
        self._close_combo(remove=True)
        self._scroll_row = None

        label = self._click_label(event)

        row = self._new_row(self._mouse_items(mods, label))
        if button == "left":
            self._last_left_row = row
            self._last_left_time = now
        else:
            self._last_left_row = None

    # ------------------------------------------------------------------
    # Actions globales
    # ------------------------------------------------------------------
    def _status(self, text: str) -> None:
        # Aucun retour visuel pendant le mode privé : les lignes créées
        # resteraient invisibles puis réapparaîtraient à la réactivation.
        if not self._capture_enabled:
            return
        # Le mode clavier n'affiche pas de ligne de texte.
        if self._mode == "keyboard":
            return
        self._flush_typing()
        self._close_combo(remove=True)
        self._scroll_row = None
        self._new_row([(text, "status")])

    def set_capture_enabled(self, enabled: bool, announce: bool = False) -> None:
        """Active ou suspend la capture affichée (mode privé)."""
        enabled = bool(enabled)
        if enabled == self._capture_enabled:
            return
        self._capture_enabled = enabled
        if enabled:
            if announce:
                self._status(_t("Capture activée"))
        else:
            self._hide_now()
            self._clear_rows()
            self._clear_keyboard()
        self.state_changed.emit()

    def toggle_visible(self) -> None:
        self.set_capture_enabled(not self._capture_enabled, announce=True)

    def set_click_through(self, enabled: bool, announce: bool = True) -> None:
        """Rend la fenêtre transparente aux clics (ou de nouveau interactive)."""
        enabled = bool(enabled)
        if enabled == self._click_through:
            return

        geometry = self.geometry()
        was_visible = self.isVisible()
        opacity = self.windowOpacity()

        self._click_through = enabled
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setGeometry(geometry)
        if was_visible:
            self.setWindowOpacity(opacity)
            self.show()

        if announce:
            self._status(
                _t("Clics traversants : activés")
                if enabled
                else _t("Clics traversants : désactivés")
            )
        self.state_changed.emit()

    def toggle_click_through(self) -> None:
        self.set_click_through(not self._click_through)

    def toggle_masking(self) -> None:
        """Active/désactive le masquage des caractères saisis."""
        self._masked = not self._masked
        self._clear_rows()
        self._keyboard.set_masked(self._masked)
        self._status(
            _t("Masquage des frappes : activé")
            if self._masked
            else _t("Masquage des frappes : désactivé")
        )
        self.state_changed.emit()

    # ------------------------------------------------------------------
    # Personnalisation
    # ------------------------------------------------------------------
    def edit_appearance(self) -> None:
        """Ouvre la fenêtre d'apparence et enregistre les changements."""
        # Suspend l'affichage pendant les réglages : les frappes saisies dans
        # la fenêtre ne doivent pas apparaître dans l'overlay.
        was_enabled = self._capture_enabled
        accepted = QDialog.DialogCode.Rejected
        if was_enabled:
            self.set_capture_enabled(False)
        try:
            dialog = AppearanceDialog(self._cfg, self._font_family)
            accepted = dialog.exec()
        finally:
            if was_enabled:
                self.set_capture_enabled(True)
        if accepted != QDialog.DialogCode.Accepted:
            return

        previous_language = self._cfg.language
        self.apply_appearance(dialog.values())
        if self._cfg.language != previous_language:
            self.language_changed.emit(self._cfg.language)
        payload = {
            key: getattr(self._cfg, key) for key in APPEARANCE_CONFIG_KEYS
        }
        if not self._cfg.save_appearance(payload):
            QMessageBox.warning(
                None,
                f"{APP_NAME} — {_t('configuration')}",
                _t(
                    "L'apparence a été appliquée, mais elle n'a pas pu être "
                    "enregistrée dans :\n{path}\n\n"
                    "Vérifiez que le dossier est accessible en écriture."
                ).format(path=self._cfg.path),
            )

