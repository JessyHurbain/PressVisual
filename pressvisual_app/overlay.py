"""Fenêtre flottante affichant les frappes et les clics."""

from __future__ import annotations

import time
from typing import Iterable, Optional

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
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
from .config import APPEARANCE_CONFIG_KEYS, Config
from .constants import APP_NAME
from .events import KeyEvent, MouseEvent
from .i18n import _t
from .keymap import (
    MODIFIER_ORDER,
    MULTI_CLICK_LABELS,
    POSITION_CHOICES,
    POSITION_LABELS,
    key_label,
    modifier_label,
    should_use_combo,
)
from .theme import Palette
from .widgets import KeyRow

#: Longueur maximale du tampon de texte affiché.
MAX_TEXT_LENGTH = 200
#: Fenêtre de temps (s) d'agrégation des événements de molette.
SCROLL_AGGREGATE_WINDOW = 0.9

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

        self._capture_enabled = not config.start_hidden
        self._click_through = False
        self._masked = False
        self._dragging = False
        self._drag_origin = QPoint(0, 0)
        self._fade_target = "idle"

        # Ancrage : bords conservés lors des changements de taille (coin
        # haut/bas, gauche/centre/droite).
        self._anchor_mode = "right"
        self._vertical_mode = "bottom"
        self._position_name = config.position
        self._anchor = QPoint(0, 0)

        # --- Animations et minuteries ------------------------------------
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.finished.connect(self._on_fade_finished)

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._fade_out)

        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._finish_text)

        self._anchoring_ready = False
        self.resize(320, 64)
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

    def apply_appearance(self, values: dict[str, object]) -> None:
        """Applique de nouveaux réglages d'apparence à l'overlay."""
        for key, value in values.items():
            if hasattr(self._cfg, key) and key != "path":
                setattr(self._cfg, key, value)
        self._cfg.validate()

        self._rebuild_fonts()
        self._palette.update_from_config(self._cfg)
        for row in self._rows:
            row.set_font(self._badge_font)
        if self._text_row is not None:
            self._render_text()

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
                if self._dragging
                else self._palette.border,
                1.0,
            )
        )
        painter.drawPath(path)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        # Le redimensionnement du layout peut survenir après le calcul de la
        # position (Qt différe parfois l'application de la taille) : on
        # réapplique l'ancrage avec la taille définitive.
        super().resizeEvent(event)
        if self._anchoring_ready and not self._dragging:
            self._apply_anchor()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
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
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - API Qt
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self._snap_anchor_to_position()
            self.update()
            # Rattrape un éventuel changement de contenu pendant le glisser.
            self._relayout()
            # La bulle reste affichée un délai complet après avoir été posée.
            self._bump()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _hold_visible(self) -> None:
        """Empêche la bulle de s'effacer pendant un déplacement manuel.

        Le minuteur de disparition est suspendu tant que le bouton reste
        enfoncé, et un fondu déjà commencé est annulé.
        """
        self._idle_timer.stop()
        if self._fade_target != "out":
            return
        self._fade.stop()
        self._fade_target = "idle"
        self.setWindowOpacity(1.0)

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

    def _fade_in(self) -> None:
        if (
            self._fade.state() == QAbstractAnimation.State.Running
            and self._fade_target == "in"
        ):
            return

        self._fade_target = "in"
        if self.isVisible() and self.windowOpacity() >= 0.999:
            # Interrompt un éventuel fondu de disparition qui vient de débuter.
            self._fade.stop()
            return

        self._fade.stop()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self._relayout()
            self.show()
        self._fade.setDuration(self._cfg.fade_in_ms)
        self._fade.setStartValue(max(0.0, self.windowOpacity()))
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()

    def _fade_out(self) -> None:
        if not self.isVisible():
            return
        self._fade.stop()
        self._fade_target = "out"
        self._idle_timer.stop()
        self._fade.setDuration(self._cfg.fade_out_ms)
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._fade_target != "out":
            return
        self.hide()
        self.setWindowOpacity(1.0)
        self._clear_rows()

    def _hide_now(self) -> None:
        self._fade.stop()
        self._fade_target = "idle"
        self._idle_timer.stop()
        self._typing_timer.stop()
        self.hide()
        self.setWindowOpacity(1.0)

    # ------------------------------------------------------------------
    # Lignes de l'overlay
    # ------------------------------------------------------------------
    def _new_row(self, items: Iterable[tuple[str, str]]) -> KeyRow:
        row = KeyRow(self._badge_font, self._palette, self)
        row.set_items(items)
        self._rows.append(row)
        self._layout.addWidget(row)
        self._trim_rows()
        self._update_levels()
        self._relayout()
        self._bump()
        return row

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

    def _on_key(self, event: KeyEvent) -> None:
        if not self._capture_enabled:
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
                self._new_row([(key_label(self._cfg, "space"), "key")])
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
                self._new_row([(label, "key")])
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
        else:
            self._new_row(items)

    # ------------------------------------------------------------------
    # Souris
    # ------------------------------------------------------------------
    def _on_mouse(self, event: MouseEvent) -> None:
        if not self._capture_enabled or not self._cfg.capture_mouse:
            return

        if self._cfg.ignore_overlay_clicks and not self._click_through and self.isVisible():
            if self.geometry().contains(QPoint(event.x, event.y)):
                return

        if event.kind == "scroll":
            self._on_scroll(event)
            return
        if event.kind == "click" and event.button:
            self._on_click(event)

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

        if button == "right":
            label = _t(self._cfg.click_right_label)
        elif button == "middle":
            label = _t(self._cfg.click_middle_label)
        elif button == "back":
            label = _t(self._cfg.click_back_label)
        elif button == "forward":
            label = _t(self._cfg.click_forward_label)
        elif event.count >= 2:
            label = _t(MULTI_CLICK_LABELS.get(event.count, MULTI_CLICK_LABELS[3]))
        else:
            label = _t(self._cfg.click_left_label)

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

