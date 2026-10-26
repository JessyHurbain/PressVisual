"""Chargement, validation et persistance de la configuration."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QColor

from .constants import APP_NAME
from .i18n import LANGUAGE_AUTO, SUPPORTED_LANGUAGES, _t
from .keymap import (
    DISPLAY_MODES,
    KEYBOARD_LAYOUTS,
    POSITION_CHOICES,
    TRANSITIONS,
)

#: Couleurs personnalisables de l'overlay (format ``#RRGGBB`` ou ``#AARRGGBB``).
APPEARANCE_COLOR_FIELDS: tuple[str, ...] = (
    "background_color",
    "background_color_bottom",
    "text_color",
    "key_background_color",
    "key_text_color",
    "accent_color",
)

#: Bornes de la taille du clavier réglée à la souris (poignée de la bulle).
KEYBOARD_SCALE_MIN = 0.6
KEYBOARD_SCALE_MAX = 2.0

#: Réglages enregistrés par la fenêtre de personnalisation.
APPEARANCE_CONFIG_KEYS: tuple[str, ...] = (
    *APPEARANCE_COLOR_FIELDS,
    "language",
    "opacity",
    "font_family",
    "font_size",
    "max_width",
    "corner_radius",
    "margin",
    "display_mode",
    "keyboard_layout",
    "show_mouse",
    "transition",
    "fade_out_ms",
)
# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """Paramètres de l'application.

    Toutes les valeurs peuvent être surchargées par un fichier JSON
    (``config.json``) puis par les options de la ligne de commande.
    """

    # --- Affichage ---------------------------------------------------------
    display_duration: float = 2.0      # durée de maintien à l'écran (s)
    fade_in_ms: int = 120              # durée du fondu d'apparition (ms)
    fade_out_ms: int = 420             # durée du fondu de disparition (ms)
    opacity: float = 0.86              # opacité du fond (0.15 - 1.0)
    font_family: str = ""              # vide = police système automatique
    font_size: int = 16
    max_rows: int = 4                  # nombre de lignes conservées
    max_width: int = 620               # largeur maximale du contenu (px)
    corner_radius: int = 16
    margin: int = 28                   # marge avec le bord de l'écran (px)
    position: str = "bottom-right"     # top-left | top-right | bottom-left | bottom-right | bottom-center
    display_mode: str = "overlay"      # overlay (pastilles) | keyboard (clavier complet)
    keyboard_layout: str = "azerty"    # azerty | qwerty
    show_mouse: bool = True            # souris à côté du clavier (mode keyboard)
    keyboard_scale: float = 1.0        # taille du clavier, réglée à la souris
    #: Transition de la bulle (apparition et disparition) : fade (fondu),
    #: slide / slide-up / slide-left / slide-right (glissements), zoom
    #: (rétrécissement), none (immédiate).
    transition: str = "fade"
    #: Position libre mémorisée : (x, y, largeur, hauteur).
    free_position: Optional[tuple[int, int, int, int]] = None
    language: str = LANGUAGE_AUTO       # auto (système) | fr | en
    concat_text: bool = False           # True = regrouper le texte, False = touche par touche
    typing_join_delay: float = 1.1     # délai de concaténation du texte (s)

    # --- Couleurs (format #RRGGBB ou #AARRGGBB) ----------------------------
    background_color: str = "#26282f"
    background_color_bottom: str = "#0e0f12"
    text_color: str = "#f6f7f9"
    key_background_color: str = "#f5f6f8"
    key_text_color: str = "#111216"
    accent_color: str = "#548eff"

    # --- Capture -----------------------------------------------------------
    capture_keyboard: bool = True
    capture_mouse: bool = True
    ignore_key_repeats: bool = True
    ignore_overlay_clicks: bool = True  # ne pas afficher les clics sur l'overlay
    filtered_keys: list[str] = field(default_factory=list)

    # --- Libellés ----------------------------------------------------------
    ctrl_label: str = "Ctrl"
    alt_label: str = "Alt"
    shift_label: str = "Maj"
    win_label: str = "Win"
    click_left_label: str = "Clic gauche"
    click_right_label: str = "Clic droit"
    click_middle_label: str = "Clic milieu"
    #: Boutons latéraux de la souris (précédent / suivant).
    click_back_label: str = "Précédent"
    click_forward_label: str = "Suivant"
    scroll_up_label: str = "Scroll ↑"
    scroll_down_label: str = "Scroll ↓"
    #: Molette inclinable (défilement horizontal).
    scroll_left_label: str = "Scroll ←"
    scroll_right_label: str = "Scroll →"

    # --- Raccourcis globaux (chaîne vide = désactivé) ----------------------
    hotkey_toggle: str = "ctrl+f12"
    hotkey_click_through: str = "ctrl+f11"
    hotkey_masking: str = "ctrl+f10"
    hotkey_quit: str = "ctrl+f9"

    # --- Démarrage ---------------------------------------------------------
    start_hidden: bool = False
    click_through_on_start: bool = False

    #: Fichier d'où provient la configuration (non sérialisé, non comparable).
    path: Optional[Path] = field(
        default=None, repr=False, compare=False, init=False
    )

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path, warn) -> "Config":
        """Charge un fichier JSON en ignorant les clés inconnues."""
        config = cls()
        config.path = path
        if not path.exists():
            return config
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warn(
                _t("Configuration illisible ({path}) : {exc}").format(
                    path=path, exc=exc
                )
            )
            return config
        if not isinstance(raw, dict):
            warn(
                _t("Configuration ignorée ({path}) : un objet JSON est attendu.").format(
                    path=path
                )
            )
            return config
        for key, value in raw.items():
            if key == "path":
                # Champ interne (emplacement du fichier) : jamais chargé.
                warn(_t("Clé réservée ignorée : path"))
                continue
            if not hasattr(config, key):
                warn(
                    _t("Clé de configuration inconnue ignorée : {key}").format(key=key)
                )
                continue
            setattr(config, key, value)
        return config

    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Convertit et borne les valeurs ; renvoie la liste des corrections."""
        notes: list[str] = []

        def number(name: str, low: float, high: float, cast, unit: str = "") -> None:
            value = getattr(self, name)
            try:
                converted = cast(value)
            except (TypeError, ValueError):
                notes.append(
                    _t("{name} invalide ({value}) : valeur par défaut utilisée.").format(
                        name=name, value=repr(value)
                    )
                )
                converted = cast(getattr(Config, name))
            if converted < low or converted > high:
                notes.append(
                    _t("{name} hors limites : ramené dans [{low}, {high}]{unit}.").format(
                        name=name, low=low, high=high, unit=unit
                    )
                )
                converted = min(max(converted, low), high)
            setattr(self, name, converted)

        number("display_duration", 0.3, 30.0, float, " s")
        number("fade_in_ms", 0, 2000, int, " ms")
        number("fade_out_ms", 0, 3000, int, " ms")
        number("opacity", 0.15, 1.0, float)
        number("font_size", 9, 40, int, " pt")
        number("max_rows", 1, 8, int)
        number("max_width", 220, 1600, int, " px")
        number("corner_radius", 0, 40, int, " px")
        number("margin", 0, 400, int, " px")
        number("typing_join_delay", 0.2, 10.0, float, " s")
        number("keyboard_scale", KEYBOARD_SCALE_MIN, KEYBOARD_SCALE_MAX, float)

        for name in APPEARANCE_COLOR_FIELDS:
            value = getattr(self, name)
            color = QColor(value) if isinstance(value, str) else QColor()
            if not color.isValid():
                notes.append(
                    _t(
                        "{name} invalide ({value}) : couleur par défaut utilisée."
                    ).format(name=name, value=repr(value))
                )
                color = QColor(getattr(Config, name))
            setattr(self, name, _color_to_text(color))

        if self.position not in POSITION_CHOICES:
            notes.append(
                _t("position inconnue ({value}) : « bottom-right » utilisée.").format(
                    value=repr(self.position)
                )
            )
            self.position = "bottom-right"

        free = self.free_position
        if free is None:
            pass
        elif (
            isinstance(free, (list, tuple))
            and len(free) == 4
            and all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in free
            )
            and free[2] > 0
            and free[3] > 0
        ):
            self.free_position = (free[0], free[1], free[2], free[3])
        else:
            notes.append(
                _t(
                    "free_position invalide ({value}) : position préréglée utilisée."
                ).format(value=repr(free))
            )
            self.free_position = None

        transition = str(self.transition or "fade").strip().lower()
        if transition not in TRANSITIONS:
            notes.append(
                _t("transition inconnue ({value}) : « fade » utilisée.").format(
                    value=repr(self.transition)
                )
            )
            transition = "fade"
        self.transition = transition

        mode = str(self.display_mode or "overlay").strip().lower()
        if mode not in DISPLAY_MODES:
            notes.append(
                _t("display_mode inconnu ({value}) : « overlay » utilisé.").format(
                    value=repr(self.display_mode)
                )
            )
            mode = "overlay"
        self.display_mode = mode

        layout = str(self.keyboard_layout or "azerty").strip().lower()
        if layout not in KEYBOARD_LAYOUTS:
            notes.append(
                _t(
                    "keyboard_layout inconnu ({value}) : « azerty » utilisé."
                ).format(value=repr(self.keyboard_layout))
            )
            layout = "azerty"
        self.keyboard_layout = layout

        self.language = str(self.language or LANGUAGE_AUTO).strip().lower()
        if self.language not in (LANGUAGE_AUTO, *SUPPORTED_LANGUAGES):
            notes.append(
                _t("langue inconnue ({value}) : « auto » utilisée.").format(
                    value=repr(self.language)
                )
            )
            self.language = LANGUAGE_AUTO

        for flag in (
            "capture_keyboard",
            "capture_mouse",
            "show_mouse",
            "ignore_key_repeats",
            "ignore_overlay_clicks",
            "concat_text",
            "start_hidden",
            "click_through_on_start",
        ):
            setattr(self, flag, _as_bool(getattr(self, flag), True))

        if not isinstance(self.filtered_keys, (list, tuple)):
            notes.append(_t("filtered_keys doit être une liste : valeur ignorée."))
            self.filtered_keys = []
        else:
            self.filtered_keys = [str(item).lower() for item in self.filtered_keys]

        for name in (
            "font_family",
            "ctrl_label",
            "alt_label",
            "shift_label",
            "win_label",
            "click_left_label",
            "click_right_label",
            "click_middle_label",
            "click_back_label",
            "click_forward_label",
            "scroll_up_label",
            "scroll_down_label",
            "scroll_left_label",
            "scroll_right_label",
            "hotkey_toggle",
            "hotkey_click_through",
            "hotkey_masking",
            "hotkey_quit",
        ):
            setattr(self, name, str(getattr(self, name) or "").strip())

        return notes


    # ------------------------------------------------------------------
    def remember_position(self, position: str) -> bool:
        """Enregistre ``position`` dans le fichier JSON de configuration.

        Un coin préréglé remplace la position libre : celle-ci est effacée.
        """
        if position not in POSITION_CHOICES:
            return False
        self.free_position = None
        return self._update_config(
            {"position": position, "free_position": None}, _t("Position")
        )

    # ------------------------------------------------------------------
    def remember_keyboard_scale(self, scale: float) -> bool:
        """Mémorise la taille du clavier réglée avec la poignée."""
        value = min(KEYBOARD_SCALE_MAX, max(KEYBOARD_SCALE_MIN, float(scale)))
        self.keyboard_scale = round(value, 3)
        return self._update_config(
            {"keyboard_scale": self.keyboard_scale}, _t("Taille du clavier")
        )

    # ------------------------------------------------------------------
    def remember_free_position(self, x: int, y: int, width: int, height: int) -> bool:
        """Mémorise la position et la taille libres dans le fichier JSON."""
        values = (int(x), int(y), int(width), int(height))
        self.free_position = values
        return self._update_config({"free_position": list(values)}, _t("Position"))

    # ------------------------------------------------------------------
    def save_appearance(self, values: dict[str, object]) -> bool:
        """Enregistre les réglages d'apparence dans le fichier de configuration."""
        payload = {key: values[key] for key in APPEARANCE_CONFIG_KEYS if key in values}
        return self._update_config(payload, _t("Apparence"))

    # ------------------------------------------------------------------
    def _update_config(self, values: dict[str, object], what: str) -> bool:
        """Met à jour quelques clés du fichier JSON en conservant les autres.

        Renvoie ``True`` si le fichier est à jour (ou s'il n'y a rien à
        enregistrer). En cas d'échec, l'application continue normalement et
        l'erreur est signalée sur la sortie d'erreur.
        """
        if self.path is None:
            return True

        path = self.path
        data: dict[str, object] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                sys.stderr.write(
                    f"[{APP_NAME}] "
                    + _t("{what} non enregistrée ({path}) : {exc}").format(
                        what=what, path=path, exc=exc
                    )
                    + "\n"
                )
                return False
            if not isinstance(raw, dict):
                sys.stderr.write(
                    f"[{APP_NAME}] "
                    + _t(
                        "{what} non enregistrée ({path}) : "
                        "un objet JSON est attendu."
                    ).format(what=what, path=path)
                    + "\n"
                )
                return False
            data = raw

        changed = {
            key: value for key, value in values.items() if data.get(key) != value
        }
        if not changed:
            return True
        data.update(changed)

        temp_path = path.with_name(path.name + ".tmp")
        try:
            temp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_path, path)
        except OSError as exc:
            sys.stderr.write(
                f"[{APP_NAME}] "
                + _t("{what} non enregistrée ({path}) : {exc}").format(
                    what=what, path=path, exc=exc
                )
                + "\n"
            )
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True


def _as_bool(value: object, default: bool) -> bool:
    """Convertit une valeur JSON en booléen."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "oui", "yes", "1", "on"):
            return True
        if lowered in ("false", "non", "no", "0", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _color_to_text(color: QColor) -> str:
    """Forme ``#rrggbb`` (ou ``#aarrggbb`` si la couleur est translucide)."""
    if color.alpha() == 255:
        return color.name(QColor.NameFormat.HexRgb)
    return color.name(QColor.NameFormat.HexArgb)

