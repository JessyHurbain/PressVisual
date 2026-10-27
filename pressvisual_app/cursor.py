"""Pastille affichée près du curseur pour un clic ou un défilement.

Elle sert au réglage « suivi de la souris » : au lieu d'empiler les clics dans
la bulle, l'événement s'affiche à côté du pointeur, là où le geste se produit.
La fenêtre ne prend ni le focus ni les clics : elle ne gêne jamais l'action.

La pastille montre un petit schéma de souris — le bouton enfoncé, le bouton
latéral ou le sens du défilement s'allument — plutôt qu'une phrase : le geste
se lit d'un coup d'œil. Les modificateurs tenus s'inscrivent à gauche du
schéma (``Ctrl``, ``Maj``) et un clic multiple ajoute son compte (``×2``).
Le cadre suit ``cursor_style``, le schéma ``mouse_style``, celui du clavier
complet.
"""

from __future__ import annotations

from dataclasses import replace
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

from .keymap import CURSOR_STYLES, MOUSE_STYLES
from .mouse import DEFAULT_MOUSE_STYLE, MOUSE_BUTTONS, MouseView
from .theme import Palette, _blend, _with_alpha

#: Durée d'affichage (ms) : un cran de molette n'a pas de relâchement.
CURSOR_BADGE_MS = 700

#: Dessin utilisé quand la configuration n'en donne pas (ou un inconnu).
DEFAULT_CURSOR_STYLE = "classic"

#: Décalage par rapport au pointeur (px), pour ne pas masquer son extrémité.
CURSOR_OFFSET = 18
#: Hauteur du petit schéma de souris (px).
GLYPH_HEIGHT = 48.0
#: Traits du schéma renforcés : à cette taille, les traits fins disparaissent.
GLYPH_STROKES = 1.7
#: Marge entre le cadre et son contenu (px).
PADDING = 7.0
#: Écart entre les modificateurs et la souris (px).
CHIP_GAP = 6.0
#: Arête d'une pastille « touche de clavier » (px).
KEYCAP_EDGE = 3.0


def _normalize_style(style: str) -> str:
    """Nom de dessin valide, ou « classic »."""
    value = str(style or "").strip().lower()
    return value if value in CURSOR_STYLES else DEFAULT_CURSOR_STYLE


def _normalize_mouse_style(style: str) -> str:
    """Nom de dessin de souris valide, ou « classic »."""
    value = str(style or "").strip().lower()
    return value if value in MOUSE_STYLES else DEFAULT_MOUSE_STYLE


def _glyph_palette(palette: Palette, style: str) -> Palette:
    """Palette du petit schéma : une encre et un fond lisibles sur le cadre.

    Le cadre donne le fond (accent, panneau ou touche) ; le schéma s'y dessine
    avec la couleur de texte correspondante, pour rester net dans les trois
    dessins.
    """
    if style == "outline":
        ink, back = palette.text, palette.panel_bottom
    elif style == "keycap":
        ink, back = palette.key_text, palette.key_bg
    else:
        ink, back = palette.on_accent, palette.accent
    #: Le corps de la souris se détache légèrement du cadre, sinon il
    #: disparaît dans un fond de même couleur (touche claire, panneau sombre).
    body = _blend(back, ink, 0.12)
    return replace(
        palette,
        text=ink,
        key_text=ink,
        key_bg=body,
        accent=ink,
        accent_soft=ink,
        on_accent=back,
    )


class CursorBadge(QWidget):
    """Petit schéma de souris près du pointeur, transparent aux clics."""

    def __init__(
        self,
        palette: Palette,
        font: Optional[QFont] = None,
        style: str = DEFAULT_CURSOR_STYLE,
        mouse_style: str = DEFAULT_MOUSE_STYLE,
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
        self._chip_font = QFont(self._font)
        self._chip_font.setWeight(QFont.Weight.Medium)
        self._apply_chip_size()

        self._mouse = MouseView(
            _glyph_palette(palette, self._style),
            self,
            mouse_style,
            GLYPH_STROKES,
        )
        self._mouse.set_height(GLYPH_HEIGHT)
        self._mouse.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        self._chips: list[str] = []
        self._button: Optional[str] = None
        self._scroll: Optional[tuple[str, int]] = None
        self._chip_rect = QRectF()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_badge)
        self.hide()

    # ------------------------------------------------------------------
    @property
    def style(self) -> str:
        """Dessin du cadre (``classic``, ``outline`` ou ``keycap``)."""
        return self._style

    @property
    def mouse_style(self) -> str:
        """Dessin du petit schéma de souris."""
        return self._mouse.style

    @property
    def buttons(self) -> tuple[str, ...]:
        """Boutons allumés dans le schéma (un seul à la fois)."""
        return (self._button,) if self._button else ()

    @property
    def scroll(self) -> Optional[tuple[str, int]]:
        """Dernier défilement affiché : ``(axe, sens)`` ou ``None``."""
        return self._scroll

    @property
    def chips(self) -> tuple[str, ...]:
        """Modificateurs et compte affichés au-dessus de la souris."""
        return tuple(self._chips)

    def set_style(self, style: str) -> None:
        """Change le cadre ; le geste affiché est conservé."""
        value = _normalize_style(style)
        if value != self._style:
            self._style = value
            self._sync_palette()
            self._relayout()
            self.update()

    def set_mouse_style(self, style: str) -> None:
        """Change le dessin du petit schéma de souris."""
        self._mouse.set_style(style)

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        self._sync_palette()
        self.update()

    def set_font(self, font: QFont) -> None:
        self._font = QFont(font)
        self._font.setWeight(QFont.Weight.DemiBold)
        self._apply_chip_size()
        self._chip_font.setWeight(QFont.Weight.Medium)
        if self._chips:
            self._relayout()
        self.update()

    def show_event(
        self,
        button: Optional[str] = None,
        scroll: Optional[tuple[str, int]] = None,
        chips: tuple[str, ...] = (),
    ) -> None:
        """Affiche un geste près du pointeur, puis l'efface après un délai."""
        self._button = button if button in MOUSE_BUTTONS else None
        self._scroll = scroll
        self._chips = [chip for chip in chips if chip]
        self._mouse.set_buttons(self.buttons)
        if scroll is not None:
            self._mouse.set_scroll(*scroll)
        else:
            self._mouse.clear_scroll()
        self._relayout()
        self._move_next_to_cursor()
        self.show()
        self._timer.start(CURSOR_BADGE_MS)
        self.update()

    def hide_badge(self) -> None:
        """Efface la pastille et arrête le minuteur."""
        self._timer.stop()
        self.hide()

    # ------------------------------------------------------------------
    def _apply_chip_size(self) -> None:
        """Les modificateurs restent petits devant le schéma de souris."""
        size = self._font.pointSizeF()
        if size > 0:
            self._chip_font.setPointSizeF(max(7.0, size - 7.0))

    def _sync_palette(self) -> None:
        """Reporte le cadre courant sur la palette du petit schéma."""
        self._mouse.set_palette(_glyph_palette(self._palette, self._style))

    def _ink(self):
        """Couleur du texte des modificateurs, selon le cadre."""
        if self._style == "outline":
            return self._palette.text
        if self._style == "keycap":
            return self._palette.key_text
        return self._palette.on_accent

    def _relayout(self) -> None:
        """Dimensionne le cadre autour du schéma et des modificateurs."""
        edge = KEYCAP_EDGE if self._style == "keycap" else 0.0
        metrics = QFontMetrics(self._chip_font)
        text = " + ".join(self._chips)
        chip_width = metrics.horizontalAdvance(text) if text else 0

        mouse_width = self._mouse.width()
        mouse_height = self._mouse.height()
        chips_width = chip_width + CHIP_GAP if text else 0
        width = 2 * PADDING + chips_width + mouse_width
        height = 2 * PADDING + edge + mouse_height

        self.resize(round(width), round(height))
        self._chip_rect = QRectF(
            PADDING, PADDING, chip_width, height - 2 * PADDING - edge
        )
        self._mouse.move(
            round(width - PADDING - mouse_width),
            round(height - PADDING - edge - mouse_height),
        )

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
            self._paint_keycap(painter, rect)
        elif self._style == "outline":
            self._paint_outline(painter, rect)
        else:
            self._paint_pill(painter, rect)

        if self._chips:
            painter.setFont(self._chip_font)
            painter.setPen(_with_alpha(self._ink(), 0.96))
            painter.drawText(
                self._chip_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                " + ".join(self._chips),
            )

    def _paint_pill(self, painter: QPainter, rect: QRectF) -> None:
        """Cadre plein de la couleur d'accent."""
        radius = min(10.0, rect.height() * 0.28)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, _with_alpha(self._palette.accent, 0.94))
        painter.setPen(QPen(_with_alpha(self._palette.accent_soft, 0.9), 1.0))
        painter.drawPath(path)

    def _paint_outline(self, painter: QPainter, rect: QRectF) -> None:
        """Fond du panneau et trait d'accent : la version « contour »."""
        radius = min(10.0, rect.height() * 0.28)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, _with_alpha(self._palette.panel_bottom, 0.94))
        painter.setPen(QPen(_with_alpha(self._palette.accent, 0.95), 1.4))
        painter.drawPath(path)

    def _paint_keycap(self, painter: QPainter, rect: QRectF) -> None:
        """Cadre en touche de clavier, avec son arête plus sombre."""
        edge = min(KEYCAP_EDGE, rect.height() * 0.16)
        radius = min(8.0, rect.height() * 0.22)
        base = QPainterPath()
        base.addRoundedRect(rect, radius, radius)
        shade = _blend(self._palette.key_bg, QColor(0, 0, 0), 0.45)
        painter.fillPath(base, _with_alpha(shade, 0.98))

        cap = QRectF(rect.left(), rect.top(), rect.width(), rect.height() - edge)
        cap_radius = min(8.0, cap.height() * 0.22)
        path = QPainterPath()
        path.addRoundedRect(cap, cap_radius, cap_radius)
        painter.fillPath(path, _with_alpha(self._palette.key_bg, 0.98))
        painter.setPen(QPen(_with_alpha(self._palette.key_text, 0.16), 1.0))
        painter.drawPath(path)
