"""Clavier compact affiché en mode « clavier complet ».

Deux dispositions sont fournies, AZERTY et QWERTY. Elles se limitent aux
touches utiles à une démonstration : lettres, chiffres, ponctuation courante,
modificateurs, Tab, Verr Maj, Espace, Entrée, Retour, Échap et flèches.

La vue ne dessine que les touches : c'est la fenêtre de l'overlay qui peint le
panneau, les coins arrondis et l'opacité.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from .config import KEYBOARD_SCALE_MAX, KEYBOARD_SCALE_MIN, Config
from .i18n import _t
from .mouse import MouseView
from .theme import Palette, _with_alpha


@dataclass(frozen=True)
class Key:
    """Une touche : étiquette, jetons qui l'allument et largeur en unités."""

    label: str
    tokens: frozenset[str] = frozenset()
    width: float = 1.0
    #: Glyphe secondaire (majuscule ou symbole obtenu avec Maj).
    secondary: str = ""
    #: Nom du modificateur tenu qui allume la touche (``ctrl``, ``shift``...).
    modifier: str = ""


def _key(
    label: str,
    *tokens: str,
    secondary: str = "",
    width: float = 1.0,
    modifier: str = "",
) -> Key:
    return Key(
        label=label,
        tokens=frozenset(tokens),
        width=width,
        secondary=secondary,
        modifier=modifier,
    )


@dataclass(frozen=True)
class KeyboardLayout:
    """Disposition complète : une suite de rangées de touches."""

    name: str
    rows: tuple[tuple[Key, ...], ...]

    @property
    def width(self) -> float:
        """Largeur totale, en unités de touche."""
        return max(sum(key.width for key in row) for row in self.rows)

    def keys(self) -> Iterator[Key]:
        for row in self.rows:
            yield from row

    def keys_for_token(self, token: str) -> tuple[Key, ...]:
        """Touches qui correspondent à un jeton de capture."""
        return tuple(key for key in self.keys() if token in key.tokens)


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------


def _modifier_row() -> tuple[Key, ...]:
    """Rangée du bas, commune aux deux dispositions."""
    return (
        _key("Ctrl", width=1.2, modifier="ctrl"),
        _key("Win", width=1.2, modifier="win"),
        _key("Alt", width=1.2, modifier="alt"),
        _key("Espace", "space", width=6.2),
        _key("Ctrl", width=1.2, modifier="ctrl"),
        _key("←", "left"),
        _key("↑", "up"),
        _key("↓", "down"),
        _key("→", "right"),
    )


AZERTY = KeyboardLayout(
    name="azerty",
    rows=(
        (
            _key("Échap", "esc", width=1.5),
            _key("&", "&", "1", secondary="1"),
            _key("é", "é", "2", secondary="2"),
            _key('"', '"', "3", secondary="3"),
            _key("'", "'", "4", secondary="4"),
            _key("(", "(", "5", secondary="5"),
            _key("-", "-", "6", secondary="6"),
            _key("è", "è", "7", secondary="7"),
            _key("_", "_", "8", secondary="8"),
            _key("ç", "ç", "9", secondary="9"),
            _key("à", "à", "0", secondary="0"),
            _key(")", ")", "°", secondary="°"),
            _key("=", "=", "+", secondary="+"),
            _key("Retour", "backspace", width=1.5),
        ),
        (
            _key("Tab", "tab", width=1.5),
            _key("A", "a"),
            _key("Z", "z"),
            _key("E", "e"),
            _key("R", "r"),
            _key("T", "t"),
            _key("Y", "y"),
            _key("U", "u"),
            _key("I", "i"),
            _key("O", "o"),
            _key("P", "p"),
            _key("^", "^", "¨", secondary="¨"),
            _key("$", "$", "£", secondary="£"),
            _key("Entrée", "enter", width=1.5),
        ),
        (
            _key("Verr Maj", "caps_lock", width=1.75),
            _key("Q", "q"),
            _key("S", "s"),
            _key("D", "d"),
            _key("F", "f"),
            _key("G", "g"),
            _key("H", "h"),
            _key("J", "j"),
            _key("K", "k"),
            _key("L", "l"),
            _key("M", "m"),
            _key("ù", "ù", "%", secondary="%"),
            _key("*", "*", "µ", secondary="µ", width=2.25),
        ),
        (
            _key("Maj", width=2.25, modifier="shift"),
            _key("W", "w"),
            _key("X", "x"),
            _key("C", "c"),
            _key("V", "v"),
            _key("B", "b"),
            _key("N", "n"),
            _key(",", ",", "?", secondary="?"),
            _key(";", ";", ".", secondary="."),
            _key(":", ":", "/", secondary="/"),
            _key("!", "!", "§", secondary="§"),
            _key("Maj", width=2.75, modifier="shift"),
        ),
        _modifier_row(),
    ),
)

QWERTY = KeyboardLayout(
    name="qwerty",
    rows=(
        (
            _key("Échap", "esc", width=1.5),
            _key("1", "1", "!", secondary="!"),
            _key("2", "2", "@", secondary="@"),
            _key("3", "3", "#", secondary="#"),
            _key("4", "4", "$", secondary="$"),
            _key("5", "5", "%", secondary="%"),
            _key("6", "6", "^", secondary="^"),
            _key("7", "7", "&", secondary="&"),
            _key("8", "8", "*", secondary="*"),
            _key("9", "9", "(", secondary="("),
            _key("0", "0", ")", secondary=")"),
            _key("-", "-", "_", secondary="_"),
            _key("=", "=", "+", secondary="+"),
            _key("Retour", "backspace", width=1.5),
        ),
        (
            _key("Tab", "tab", width=1.5),
            _key("Q", "q"),
            _key("W", "w"),
            _key("E", "e"),
            _key("R", "r"),
            _key("T", "t"),
            _key("Y", "y"),
            _key("U", "u"),
            _key("I", "i"),
            _key("O", "o"),
            _key("P", "p"),
            _key("[", "[", "{", secondary="{"),
            _key("]", "]", "}", secondary="}"),
            _key("Entrée", "enter", width=1.5),
        ),
        (
            _key("Verr Maj", "caps_lock", width=1.75),
            _key("A", "a"),
            _key("S", "s"),
            _key("D", "d"),
            _key("F", "f"),
            _key("G", "g"),
            _key("H", "h"),
            _key("J", "j"),
            _key("K", "k"),
            _key("L", "l"),
            _key(";", ";", ":", secondary=":"),
            _key("'", "'", '"', secondary='"'),
            _key("\\", "\\", "|", secondary="|", width=2.25),
        ),
        (
            _key("Maj", width=2.25, modifier="shift"),
            _key("Z", "z"),
            _key("X", "x"),
            _key("C", "c"),
            _key("V", "v"),
            _key("B", "b"),
            _key("N", "n"),
            _key("M", "m"),
            _key(",", ",", "<", secondary="<"),
            _key(".", ".", ">", secondary=">"),
            _key("/", "/", "?", secondary="?"),
            _key("Maj", width=2.75, modifier="shift"),
        ),
        _modifier_row(),
    ),
)

#: Dispositions disponibles, dans l'ordre de présentation.
LAYOUTS: dict[str, KeyboardLayout] = {"azerty": AZERTY, "qwerty": QWERTY}


def layout_for(name: str) -> KeyboardLayout:
    """Disposition demandée, ou AZERTY pour un nom inconnu."""
    return LAYOUTS.get(str(name or "").strip().lower(), AZERTY)


# ---------------------------------------------------------------------------
# Vue
# ---------------------------------------------------------------------------


class KeyboardView(QWidget):
    """Clavier compact dont s'allument les touches pressées et maintenues."""

    KEY_GAP = 4.0
    ROW_GAP = 5.0

    def __init__(
        self,
        config: Config,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = config
        self._palette = palette
        self._definition = layout_for(config.keyboard_layout)
        self._base_font = QFont(font)
        self._base_small_font = QFont(font)
        self._base_small_font.setPointSize(max(7, font.pointSize() - 3))
        self._scale = 1.0
        self._font = QFont(font)
        self._small_font = QFont(self._base_small_font)
        self._active: frozenset[str] = frozenset()
        self._modifiers: frozenset[str] = frozenset()
        self._masked = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------
    # État
    # ------------------------------------------------------------------
    @property
    def layout(self) -> KeyboardLayout:
        return self._definition

    def set_font(self, font: QFont) -> None:
        """Change la police de base ; la taille réglée est conservée."""
        self._base_font = QFont(font)
        self._base_small_font = QFont(font)
        self._base_small_font.setPointSize(max(7, font.pointSize() - 3))
        self._apply_scale()

    def set_scale(self, scale: float) -> None:
        """Agrandit ou réduit le clavier (police et touches comprises)."""
        scale = min(KEYBOARD_SCALE_MAX, max(KEYBOARD_SCALE_MIN, float(scale)))
        if scale == self._scale:
            return
        self._scale = scale
        self._apply_scale()

    @property
    def scale(self) -> float:
        return self._scale

    def _apply_scale(self) -> None:
        """Recalcule les polices effectives à partir du facteur d'échelle."""
        self._font = QFont(self._base_font)
        self._font.setPointSizeF(
            max(4.0, self._base_font.pointSizeF() * self._scale)
        )
        self._small_font = QFont(self._base_small_font)
        self._small_font.setPointSizeF(
            max(4.0, self._base_small_font.pointSizeF() * self._scale)
        )
        self.updateGeometry()
        self.update()

    def set_config(self, config: Config) -> None:
        """Change la configuration lue (aperçu de la fenêtre d'apparence)."""
        self._cfg = config
        self.refresh_layout()

    def refresh_layout(self) -> None:
        """Relit la disposition choisie dans la configuration."""
        definition = layout_for(self._cfg.keyboard_layout)
        if definition is self._definition:
            return
        self._definition = definition
        self.updateGeometry()
        self.update()

    def set_active(self, tokens: Iterable[str]) -> None:
        active = frozenset(tokens)
        if active != self._active:
            self._active = active
            self.update()

    def set_modifiers(self, modifiers: Iterable[str]) -> None:
        held = frozenset(modifiers)
        if held != self._modifiers:
            self._modifiers = held
            self.update()

    def set_masked(self, masked: bool) -> None:
        masked = bool(masked)
        if masked != self._masked:
            self._masked = masked
            self.update()

    def active_labels(self) -> list[str]:
        """Étiquettes des touches actuellement allumées (tests, débogage)."""
        return [
            self._label(key)
            for key in self._definition.keys()
            if self._is_active(key)
        ]

    # ------------------------------------------------------------------
    # Dimensions
    # ------------------------------------------------------------------
    def _unit(self) -> float:
        """Largeur d'une touche : mesurée sur la police de base, puis réduite."""
        metrics = QFontMetrics(self._base_font)
        base = max(metrics.height() * 1.8, metrics.horizontalAdvance("W") + 12.0)
        return base * self._scale

    def _key_height(self) -> float:
        return float(QFontMetrics(self._base_font).height() + 16) * self._scale

    def _gap(self, gap: float) -> float:
        """Espacement réduit avec le clavier, pour garder les mêmes proportions."""
        return max(1.0, gap * self._scale)

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        rows = len(self._definition.rows)
        width = self._definition.width * self._unit()
        height = rows * self._key_height() + (rows - 1) * self._gap(self.ROW_GAP)
        return QSize(round(width), round(height))

    # ------------------------------------------------------------------
    # Peinture
    # ------------------------------------------------------------------
    def _is_active(self, key: Key) -> bool:
        if key.modifier:
            return key.modifier in self._modifiers
        matching = key.tokens & self._active
        if not matching:
            return False
        # Mode masqué : aucune touche de caractère ne s'allume.
        if self._masked and all(len(token) == 1 for token in matching):
            return False
        return True

    def _label(self, key: Key) -> str:
        """Étiquette affichée, en respectant les libellés de la configuration."""
        if key.modifier == "ctrl":
            return _t(self._cfg.ctrl_label)
        if key.modifier == "alt":
            return _t(self._cfg.alt_label)
        if key.modifier == "shift":
            return _t(self._cfg.shift_label)
        if key.modifier == "win":
            return _t(self._cfg.win_label)
        return _t(key.label)

    def _paint_key(self, painter: QPainter, key: Key, rect: QRectF) -> None:
        active = self._is_active(key)
        radius = max(3.0, min(6.0, rect.height() * 0.2))

        if active:
            painter.setBrush(_with_alpha(self._palette.accent, 0.95))
            painter.setPen(QPen(_with_alpha(self._palette.accent_soft, 0.9), 1.0))
            main_color = _with_alpha(self._palette.on_accent, 0.98)
            secondary_color = _with_alpha(self._palette.on_accent, 0.7)
        else:
            painter.setBrush(_with_alpha(self._palette.key_bg, 0.9))
            painter.setPen(QPen(_with_alpha(self._palette.mod_border, 0.85), 1.0))
            main_color = _with_alpha(self._palette.key_text, 0.92)
            secondary_color = _with_alpha(self._palette.key_text, 0.55)
        painter.drawRoundedRect(rect, radius, radius)

        label = self._label(key)
        font = QFont(self._small_font) if len(label) > 3 else QFont(self._font)
        padding = max(4.0, 8.0 * self._scale)
        available = int(max(10.0, rect.width() - padding))
        metrics = QFontMetrics(font)
        # Les libellés longs (« Verr Maj », « Entrée ») rétrécissent plutôt
        # que d'être tronqués dans une touche étroite. Le plancher suit la
        # taille du clavier, sinon les petites tailles tronquent sans essayer.
        floor = max(4.0, 6.0 * self._scale)
        while (
            metrics.horizontalAdvance(label) > available
            and font.pointSizeF() > floor
        ):
            font.setPointSizeF(font.pointSizeF() - 0.5)
            metrics = QFontMetrics(font)
        painter.setFont(font)
        painter.setPen(main_color)
        text_rect = QRectF(rect)
        if key.secondary:
            text_rect.setTop(rect.top() + rect.height() * 0.26)
        if metrics.horizontalAdvance(label) <= available:
            text = label
        else:
            text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, available)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        if not key.secondary:
            return
        small = QRectF(
            rect.left() + 5.0,
            rect.top() + 1.0,
            max(6.0, rect.width() - 9.0),
            rect.height() * 0.42,
        )
        painter.setFont(self._small_font)
        painter.setPen(secondary_color)
        painter.drawText(
            small,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            key.secondary,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        unit = self._unit()
        height = self._key_height()
        gap = self._gap(self.KEY_GAP)
        y = 0.0
        for row in self._definition.rows:
            x = 0.0
            for key in row:
                advance = key.width * unit
                rect = QRectF(
                    x + gap / 2.0,
                    y,
                    max(4.0, advance - gap),
                    height,
                )
                self._paint_key(painter, key, rect)
                x += advance
            y += height + self._gap(self.ROW_GAP)


class InputView(QWidget):
    """Clavier complet et souris, côte à côte."""

    GAP = 12

    def __init__(
        self,
        config: Config,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = config
        self._visible = True

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.GAP)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignBottom)

        self.keyboard = KeyboardView(config, font, palette, self)
        self.keyboard.set_scale(config.keyboard_scale)
        self.mouse = MouseView(palette, self)
        self._layout.addWidget(self.keyboard, 0, Qt.AlignmentFlag.AlignBottom)
        self._layout.addWidget(self.mouse, 0, Qt.AlignmentFlag.AlignBottom)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._sync_mouse()
        self._apply_visibility()

    # ------------------------------------------------------------------
    def set_font(self, font: QFont) -> None:
        self.keyboard.set_font(font)
        self._sync_mouse()

    def set_config(self, config: Config) -> None:
        """Relit la configuration (aperçu de la fenêtre d'apparence)."""
        self._cfg = config
        self.keyboard.set_config(config)
        self.keyboard.set_scale(config.keyboard_scale)
        self._sync_mouse()
        self._apply_visibility()

    def set_scale(self, scale: float) -> None:
        """Applique la taille du clavier choisie avec la poignée."""
        self.keyboard.set_scale(scale)
        self._sync_mouse()

    def refresh_layout(self) -> None:
        self.keyboard.refresh_layout()
        self._sync_mouse()

    def set_mode_visible(self, visible: bool) -> None:
        """Affiche la vue complète, ou la masque en mode pastilles."""
        self._visible = bool(visible)
        self._apply_visibility()

    def _sync_mouse(self) -> None:
        """La souris prend la hauteur du clavier pour rester alignée."""
        self.mouse.set_height(self.keyboard.sizeHint().height())
        self.updateGeometry()

    def _apply_visibility(self) -> None:
        # La souris n'a de sens que si elle est affichée et capturée.
        mouse_visible = (
            self._visible
            and bool(self._cfg.capture_mouse)
            and bool(self._cfg.show_mouse)
        )
        self.keyboard.setVisible(self._visible)
        self.mouse.setVisible(mouse_visible)
        self.setVisible(self._visible)
