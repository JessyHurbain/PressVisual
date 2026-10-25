"""Palette et utilitaires de couleur de l'overlay."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QColor

from .config import Config

# ---------------------------------------------------------------------------
# Widgets de l'overlay
# ---------------------------------------------------------------------------


def _with_alpha(color: QColor, factor: float) -> QColor:
    """Copie d'une couleur avec son alpha multiplié par ``factor``."""
    result = QColor(color)
    alpha = int(round(color.alpha() * max(0.0, min(1.0, factor))))
    result.setAlpha(max(0, min(255, alpha)))
    return result


def _config_color(config: Config, name: str) -> QColor:
    """Couleur de configuration, avec repli sur la valeur par défaut."""
    value = getattr(config, name)
    color = QColor(value) if isinstance(value, str) else QColor()
    return color if color.isValid() else QColor(getattr(Config, name))


def _blend(color: QColor, other: QColor, factor: float) -> QColor:
    """Mélange ``color`` vers ``other`` (0 = color, 1 = other)."""
    factor = max(0.0, min(1.0, factor))
    return QColor(
        int(round(color.red() + (other.red() - color.red()) * factor)),
        int(round(color.green() + (other.green() - color.green()) * factor)),
        int(round(color.blue() + (other.blue() - color.blue()) * factor)),
    )


def _luminance(color: QColor) -> float:
    """Luminance relative simplifiée (0 = noir, 1 = blanc)."""
    return (
        0.2126 * color.redF()
        + 0.7152 * color.greenF()
        + 0.0722 * color.blueF()
    )


@dataclass
class Palette:
    """Couleurs effectives de l'overlay, dérivées de la configuration."""

    panel_top: QColor
    panel_bottom: QColor
    border: QColor
    border_drag: QColor
    text: QColor
    muted: QColor
    key_bg: QColor
    key_text: QColor
    mod_bg: QColor
    mod_border: QColor
    accent: QColor
    accent_soft: QColor
    on_accent: QColor

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: Config) -> "Palette":
        def color(value: str, fallback: str) -> QColor:
            parsed = QColor(value) if isinstance(value, str) else QColor()
            return parsed if parsed.isValid() else QColor(fallback)

        text = color(config.text_color, Config.text_color)
        key_bg = color(config.key_background_color, Config.key_background_color)
        key_text = color(config.key_text_color, Config.key_text_color)
        accent = color(config.accent_color, Config.accent_color)

        soft = _blend(accent, QColor(255, 255, 255), 0.48)
        soft.setAlpha(245)
        on_accent = (
            QColor(0, 0, 0)
            if _luminance(accent) > 0.55
            else QColor(255, 255, 255)
        )
        on_accent.setAlpha(240)

        return cls(
            panel_top=color(config.background_color, Config.background_color),
            panel_bottom=color(
                config.background_color_bottom, Config.background_color_bottom
            ),
            border=_with_alpha(text, 40 / max(1, text.alpha())),
            border_drag=_with_alpha(text, 105 / max(1, text.alpha())),
            text=text,
            muted=_with_alpha(text, 130 / max(1, text.alpha())),
            key_bg=key_bg,
            key_text=key_text,
            mod_bg=_with_alpha(text, 28 / max(1, text.alpha())),
            mod_border=_with_alpha(text, 38 / max(1, text.alpha())),
            accent=accent,
            accent_soft=soft,
            on_accent=on_accent,
        )

    # ------------------------------------------------------------------
    def update_from_config(self, config: Config) -> None:
        """Met à jour la palette sur place (les badges la partagent)."""
        fresh = Palette.from_config(config)
        self.__dict__.update(fresh.__dict__)

