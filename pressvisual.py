#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PressVisual — overlay de visualisation des frappes clavier et des clics souris.

Application de bureau (PyQt6 + pynput) pensée pour les captures d'écran,
tutoriels et formations en ligne :

* overlay sombre translucide, coins arrondis, sans bordure, toujours au premier plan ;
* déplacement à la souris par cliquer-glisser ;
* combinaisons de touches affichées sous forme de badges (Ctrl / Alt / Maj / Win) ;
* affichage touche par touche (une pastille par frappe), avec concaténation du
  texte en option ;
* clics gauche / droit / milieu, double-clic, molette (agrégée) ;
* apparence personnalisable (couleurs, police, opacité) via une fenêtre dédiée ;
* apparition immédiate, maintien configurable puis fondu de disparition ;
* raccourcis globaux : afficher/masquer, clics traversants, masquage des frappes, quitter ;
* icône de notification (system tray) pour piloter l'application sans clavier.

Exécution :
    python pressvisual.py
    python pressvisual.py --help

Licence : libre d'utilisation et de modification.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Dépendances externes
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtCore import (
        QAbstractAnimation,
        QCoreApplication,
        QEasingCurve,
        QLocale,
        QObject,
        QPoint,
        QPropertyAnimation,
        QRectF,
        QSize,
        Qt,
        QTimer,
        QTranslator,
        pyqtSignal,
    )
    from PyQt6.QtGui import (
        QAction,
        QActionGroup,
        QColor,
        QCursor,
        QFont,
        QFontDatabase,
        QFontMetrics,
        QGuiApplication,
        QIcon,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QPixmap,
        QScreen,
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
        QMenu,
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QSystemTrayIcon,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - dépend de l'environnement
    sys.stderr.write(
        "Impossible de démarrer PressVisual : une dépendance graphique est manquante.\n"
        "Installez les prérequis avec :\n"
        "    python -m pip install -r requirements.txt\n"
        f"Détail : {exc}\n"
    )
    raise SystemExit(1) from exc

try:
    from pynput import keyboard, mouse
except Exception as exc:  # pragma: no cover - dépend de l'environnement
    sys.stderr.write(
        "Impossible de démarrer PressVisual : la bibliothèque pynput est indisponible.\n"
        "Sur Linux, installez aussi les dépendances X11 (python3-xlib).\n"
        "    python -m pip install -r requirements.txt\n"
        f"Détail : {exc}\n"
    )
    raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# Constantes de présentation
# ---------------------------------------------------------------------------

APP_NAME = "PressVisual"

#: Langues pour lesquelles un catalogue ``.qm`` est fourni (le français est
#: la langue source, écrite directement dans le code).
SUPPORTED_LANGUAGES: tuple[str, ...] = ("fr", "en")

#: Valeur de configuration « suivre la langue du système ».
LANGUAGE_AUTO = "auto"

#: Contexte utilisé par toutes les chaînes traduisibles.
TRANSLATION_CONTEXT = "PressVisual"

#: Positions proposées pour l'overlay (quatre coins + bas centre).
POSITION_CHOICES: tuple[str, ...] = (
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "bottom-center",
)

POSITION_LABELS: dict[str, str] = {
    "top-left": "Haut gauche",
    "top-right": "Haut droite",
    "bottom-left": "Bas gauche",
    "bottom-right": "Bas droite",
    "bottom-center": "Bas centre",
}

#: Ordre d'affichage des modificateurs dans une combinaison.
MODIFIER_ORDER: tuple[str, ...] = ("ctrl", "alt", "shift", "win")

#: Noms pynput des touches modificatrices -> nom canonique.
MODIFIER_KEYS: dict[str, str] = {
    "ctrl": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "shift": "shift",
    "shift_l": "shift",
    "shift_r": "shift",
    "cmd": "win",
    "cmd_l": "win",
    "cmd_r": "win",
}

#: Alias acceptés dans les raccourcis de configuration.
MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "maj": "shift",
    "win": "win",
    "cmd": "win",
    "command": "win",
    "super": "win",
    "meta": "win",
}

#: Libellés des touches spéciales (français).
SPECIAL_KEY_LABELS: dict[str, str] = {
    "space": "Espace",
    "enter": "Entrée",
    "tab": "Tab",
    "backspace": "Retour",
    "esc": "Échap",
    "delete": "Suppr",
    "insert": "Inser",
    "home": "Début",
    "end": "Fin",
    "page_up": "Page ↑",
    "page_down": "Page ↓",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "caps_lock": "Verr Maj",
    "num_lock": "Verr Num",
    "scroll_lock": "Verr défil",
    "print_screen": "Impr. écran",
    "pause": "Pause",
    "menu": "Menu",
    "alt_gr": "Alt Gr",
    "media_play_pause": "Lecture/Pause",
    "media_stop": "Stop",
    "media_volume_up": "Vol +",
    "media_volume_down": "Vol −",
    "media_volume_mute": "Muet",
    "media_previous": "Précédent",
    "media_next": "Suivant",
}

#: Couleurs personnalisables de l'overlay (format ``#RRGGBB`` ou ``#AARRGGBB``).
APPEARANCE_COLOR_FIELDS: tuple[str, ...] = (
    "background_color",
    "background_color_bottom",
    "text_color",
    "key_background_color",
    "key_text_color",
    "accent_color",
)

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
)

#: Codes virtuels Windows du pavé numérique -> caractère affiché.
#: (pynput fournit souvent ``char=None`` pour ces touches, car le pavé
#: numérique dépend de l'état de Verr Num au moment de la traduction.)
NUMPAD_VK_CHARS: dict[int, str] = {
    96: "0",
    97: "1",
    98: "2",
    99: "3",
    100: "4",
    101: "5",
    102: "6",
    103: "7",
    104: "8",
    105: "9",
    106: "*",
    107: "+",
    109: "-",
    110: ".",
    111: "/",
}

#: Noms des boutons de souris.
MOUSE_BUTTON_NAMES: dict[object, str] = {
    mouse.Button.left: "left",
    mouse.Button.right: "right",
    mouse.Button.middle: "middle",
}

#: Libellé des clics multiples.
MULTI_CLICK_LABELS: dict[int, str] = {2: "Double clic", 3: "Triple clic"}

#: Fenêtre de temps (s) pendant laquelle deux clics forment un double-clic.
DOUBLE_CLICK_WINDOW = 0.45
#: Fenêtre de temps (s) d'agrégation des événements de molette.
SCROLL_AGGREGATE_WINDOW = 0.9
#: Longueur maximale du tampon de texte affiché.
MAX_TEXT_LENGTH = 200


# ---------------------------------------------------------------------------
# Traductions
# ---------------------------------------------------------------------------


def _t(text: str) -> str:
    """Traduit un texte d'interface (la source est en français)."""
    return QCoreApplication.translate(TRANSLATION_CONTEXT, text)


def translations_directory() -> Path:
    """Dossier des catalogues ``.qm`` (compatible PyInstaller)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle:
        candidate = Path(bundle) / "translations"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent / "translations"


def resolve_language(configured: str) -> str:
    """Langue effective : choix explicite, sinon langue du système.

    Une locale inconnue (allemand, espagnol...) retombe sur l'anglais, qui
    sert de langue de repli aux côtés du français.
    """
    value = str(configured or LANGUAGE_AUTO).strip().lower().replace("_", "-")
    if value in SUPPORTED_LANGUAGES:
        return value
    if value.startswith("fr"):
        return "fr"
    if value.startswith("en"):
        return "en"
    system = QLocale.system().name().lower()
    return "fr" if system.startswith("fr") else "en"


def install_translator(
    app: QApplication, language: str, previous: Optional[QTranslator] = None
) -> Optional[QTranslator]:
    """Installe le catalogue de ``language`` et renvoie le traducteur.

    Le français étant la langue source, aucun catalogue n'est nécessaire :
    l'application affiche alors ses chaînes telles quelles.
    """
    if previous is not None:
        app.removeTranslator(previous)
    if language == "fr":
        return None

    translator = QTranslator(app)
    path = translations_directory() / f"pressvisual_{language}.qm"
    if not translator.load(str(path)):
        sys.stderr.write(
            f"[{APP_NAME}] "
            + _t("Traduction introuvable ou illisible : {path}").format(path=path)
            + "\n"
        )
        return None
    app.installTranslator(translator)
    return translator


def apply_language_change(
    app: QApplication,
    tray: "TrayController",
    translator: Optional[QTranslator],
    language: str,
) -> Optional[QTranslator]:
    """Installe la langue choisie et rafraîchit les textes du menu."""
    translator = install_translator(app, resolve_language(language), translator)
    tray.retranslate()
    return translator


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
    scroll_up_label: str = "Scroll ↑"
    scroll_down_label: str = "Scroll ↓"

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
            "scroll_up_label",
            "scroll_down_label",
            "hotkey_toggle",
            "hotkey_click_through",
            "hotkey_masking",
            "hotkey_quit",
        ):
            setattr(self, name, str(getattr(self, name) or "").strip())

        return notes


    # ------------------------------------------------------------------
    def remember_position(self, position: str) -> bool:
        """Enregistre ``position`` dans le fichier JSON de configuration."""
        if position not in POSITION_CHOICES:
            return False
        return self._update_config({"position": position}, _t("Position"))

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


# ---------------------------------------------------------------------------
# Raccourcis globaux et libellés
# ---------------------------------------------------------------------------


def parse_hotkey(spec: str) -> Optional[tuple[frozenset[str], str]]:
    """Transforme ``"ctrl+f12"`` en ``(frozenset({"ctrl"}), "f12")``.

    Renvoie ``None`` si le raccourci est vide ou invalide.
    """
    spec = (spec or "").strip()
    if not spec:
        return None
    modifiers: set[str] = set()
    key: Optional[str] = None
    for part in spec.split("+"):
        token = part.strip().lower()
        if not token:
            return None
        if token in MODIFIER_ALIASES:
            modifiers.add(MODIFIER_ALIASES[token])
        elif key is None:
            key = token
        else:
            return None
    if key is None:
        return None
    return frozenset(modifiers), key


def modifier_label(config: Config, modifier: str) -> str:
    """Libellé d'un modificateur selon la configuration."""
    return _t(
        {
            "ctrl": config.ctrl_label,
            "alt": config.alt_label,
            "shift": config.shift_label,
            "win": config.win_label,
        }.get(modifier, modifier.capitalize())
    )


def key_label(config: Config, token: str) -> str:
    """Libellé lisible d'une touche non imprimable."""
    lowered = token.lower()
    if lowered in MODIFIER_ORDER:
        return modifier_label(config, lowered)
    if lowered in SPECIAL_KEY_LABELS:
        return _t(SPECIAL_KEY_LABELS[lowered])
    if len(lowered) > 1 and lowered[0] == "f" and lowered[1:].isdigit():
        return lowered.upper()
    if len(token) == 1:
        return token.upper()
    return token.capitalize()


def describe_hotkey(config: Config, spec: str) -> str:
    """Raccourci sous forme lisible (pour les menus), ou ``""``."""
    parsed = parse_hotkey(spec)
    if parsed is None:
        return ""
    modifiers, key = parsed
    parts = [modifier_label(config, m) for m in MODIFIER_ORDER if m in modifiers]
    parts.append(key_label(config, key))
    return " + ".join(parts)


def should_use_combo(mods: tuple[str, ...], char: Optional[str]) -> bool:
    """Détermine si une frappe est une combinaison (badges) ou du texte.

    Les caractères imprimables sont traités comme du texte (touche par touche,
    ou concaténés selon la configuration), sauf lorsqu'une touche Windows/Cmd
    est enfoncée. Ctrl et Alt sont traités comme des combinaisons, sauf pour les
    caractères non ASCII qui proviennent presque toujours d'AltGr (accents sur
    un clavier AZERTY, par exemple).
    """
    if "win" in mods:
        return True
    if ("ctrl" in mods or "alt" in mods) and char is not None:
        return ord(char) <= 0x7F
    return "ctrl" in mods or "alt" in mods


# ---------------------------------------------------------------------------
# Événements échangés entre le fil de capture et l'interface
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeyEvent:
    """Une frappe de touche non modificatrice."""

    token: str
    char: Optional[str]
    mods: tuple[str, ...] = ()
    repeat: bool = False


@dataclass(frozen=True)
class MouseEvent:
    """Un clic ou un cran de molette."""

    kind: str                       # "click" | "scroll"
    button: Optional[str] = None    # "left" | "right" | "middle"
    count: int = 1
    direction: int = 0              # +1 haut, -1 bas (molette)
    x: int = 0
    y: int = 0
    mods: tuple[str, ...] = ()      # Ctrl / Alt / Maj / Win maintenus


# ---------------------------------------------------------------------------
# Pont de signaux Qt <-> fils de capture
# ---------------------------------------------------------------------------


class InputBridge(QObject):
    """Signaux Qt émis depuis les fils pynput vers l'interface.

    Les connexions Qt entre fils sont mises en file d'attente : le thread de
    capture ne touche jamais directement aux widgets.
    """

    key_event = pyqtSignal(object)        # KeyEvent
    mouse_event = pyqtSignal(object)      # MouseEvent
    modifiers_changed = pyqtSignal(object)  # tuple[str, ...]
    hotkey = pyqtSignal(str)              # "toggle" | "masking" | ...
    error = pyqtSignal(str)


# ---------------------------------------------------------------------------
# Fils de capture des entrées globales
# ---------------------------------------------------------------------------


class InputListener(threading.Thread):
    """Écoute les entrées globales via pynput, dans un fil dédié.

    Ce fil ne réalise aucune opération graphique : il se contente d'émettre
    des signaux Qt (``InputBridge``). Il est arrêté proprement par
    :meth:`stop`.
    """

    def __init__(self, bridge: InputBridge, config: Config, hotkeys: dict) -> None:
        super().__init__(name="PressVisualInputListener", daemon=True)
        self._bridge = bridge
        self._config = config
        self._hotkeys = hotkeys
        self._filtered = set(config.filtered_keys)
        self._stop_event = threading.Event()

        self._mods: set[str] = set()
        self._held: set[str] = set()
        self._altgr = False
        self._last_click: Optional[tuple[float, int, int, int]] = None
        self._error_reported = False
        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Demande l'arrêt et attend la fin des écouteurs (2 s maximum)."""
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=2.0)

    def run(self) -> None:  # noqa: D401 - méthode de Thread
        errors: list[str] = []

        # Le clavier est toujours écouté afin que les raccourcis globaux
        # restent disponibles, même en mode « souris seulement ».
        try:
            self._keyboard_listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._keyboard_listener.start()
        except Exception as exc:  # permission refusée, pas de session X11, ...
            self._keyboard_listener = None
            errors.append(_t("clavier : {error}").format(error=exc))

        if self._config.capture_mouse:
            try:
                self._mouse_listener = mouse.Listener(
                    on_click=self._on_click,
                    on_scroll=self._on_scroll,
                )
                self._mouse_listener.start()
            except Exception as exc:
                self._mouse_listener = None
                errors.append(_t("souris : {error}").format(error=exc))

        if errors:
            self._report_error(
                _t(
                    "Impossible de démarrer la capture globale des entrées.\n"
                    "{details}\n\n"
                    "• macOS : autorisez le Terminal (ou PressVisual) dans Réglages "
                    "Système → Confidentialité et sécurité → Accessibilité.\n"
                    "• Linux : un serveur X11 (ou XWayland) est nécessaire pour les "
                    "raccourcis globaux."
                ).format(details="\n".join(f"• {error}" for error in errors))
            )

        if self._keyboard_listener is None and self._mouse_listener is None:
            return

        self._stop_event.wait()

        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.join(timeout=1.0)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Clavier
    # ------------------------------------------------------------------
    def _mods_snapshot(self) -> tuple[str, ...]:
        return tuple(m for m in MODIFIER_ORDER if m in self._mods)

    def _on_press(self, key) -> None:
        try:
            if _is_altgr(key):
                self._altgr = True
                return

            token, char, is_modifier = _classify_key(key)
            if is_modifier:
                self._mods.add(token)
                if self._config.capture_keyboard and not self._altgr:
                    self._bridge.modifiers_changed.emit(self._mods_snapshot())
                return
            if not token:
                return

            token_lower = token.lower()
            repeat = token_lower in self._held
            self._held.add(token_lower)

            # Les raccourcis de contrôle restent actifs même lorsque
            # l'affichage des frappes est désactivé.
            action = self._hotkeys.get((frozenset(self._mods), token_lower))
            if action is not None:
                if not repeat:
                    self._bridge.hotkey.emit(action)
                return

            if token_lower in self._filtered:
                return
            if not self._config.capture_keyboard:
                return
            if repeat and self._config.ignore_key_repeats:
                return

            mods = self._mods_snapshot()
            if self._altgr and char is not None:
                # AltGr produit du texte (é, ~, ...) : ne pas l'afficher comme
                # une combinaison Ctrl/Alt.
                mods = ()

            self._bridge.key_event.emit(
                KeyEvent(
                    token=token_lower,
                    char=char,
                    mods=mods,
                    repeat=repeat,
                )
            )
        except Exception as exc:  # ne jamais laisser mourir le hook
            self._report_error(
                _t("Erreur pendant la lecture du clavier : {error}").format(error=exc)
            )

    def _on_release(self, key) -> None:
        try:
            if _is_altgr(key):
                self._altgr = False
                return
            token, _char, is_modifier = _classify_key(key)
            if is_modifier:
                self._mods.discard(token)
                if token == "alt":
                    self._altgr = False
                if self._config.capture_keyboard and not self._altgr:
                    self._bridge.modifiers_changed.emit(self._mods_snapshot())
                return
            if token:
                self._held.discard(token.lower())
        except Exception as exc:
            self._report_error(
                _t("Erreur pendant la lecture du clavier : {error}").format(error=exc)
            )

    # ------------------------------------------------------------------
    # Souris
    # ------------------------------------------------------------------
    def _on_click(self, x, y, button, pressed) -> None:
        if not pressed:
            return
        try:
            name = MOUSE_BUTTON_NAMES.get(button)
            if name is None:
                return

            now = time.monotonic()
            count = 1
            if name == "left" and self._last_click is not None:
                last_time, last_x, last_y, last_count = self._last_click
                if (
                    now - last_time <= DOUBLE_CLICK_WINDOW
                    and abs(x - last_x) <= 6
                    and abs(y - last_y) <= 6
                ):
                    count = min(last_count + 1, 3)
            self._last_click = (now, int(x), int(y), count)

            self._bridge.mouse_event.emit(
                MouseEvent(
                    kind="click",
                    button=name,
                    count=count,
                    x=int(x),
                    y=int(y),
                    mods=self._mods_snapshot(),
                )
            )
        except Exception as exc:
            self._report_error(
                _t("Erreur pendant la lecture de la souris : {error}").format(error=exc)
            )

    def _on_scroll(self, x, y, dx, dy) -> None:
        try:
            if dy:
                direction = 1 if dy > 0 else -1
            elif dx:
                direction = 1 if dx > 0 else -1
            else:
                return
            self._bridge.mouse_event.emit(
                MouseEvent(
                    kind="scroll",
                    direction=direction,
                    x=int(x),
                    y=int(y),
                    mods=self._mods_snapshot(),
                )
            )
        except Exception as exc:
            self._report_error(
                _t("Erreur pendant la lecture de la souris : {error}").format(error=exc)
            )

    # ------------------------------------------------------------------
    def _report_error(self, message: str) -> None:
        if self._error_reported:
            return
        self._error_reported = True
        self._bridge.error.emit(message)


def _is_altgr(key) -> bool:
    """Vrai si la touche est AltGr (Windows/macOS)."""
    return isinstance(key, keyboard.Key) and key.name == "alt_gr"


def _classify_key(key) -> tuple[Optional[str], Optional[str], bool]:
    """Analyse une touche pynput.

    Renvoie ``(jeton, caractère imprimable, est_modificateur)``.
    """
    if isinstance(key, keyboard.Key):
        name = key.name
        modifier = MODIFIER_KEYS.get(name)
        if modifier is not None:
            return modifier, None, True
        if name == "alt_gr":
            # AltGr produit des caractères accentués : ne pas l'afficher comme
            # un modificateur afin de laisser le texte se concaténer.
            return None, None, False
        return name, None, False

    vk = getattr(key, "vk", None)

    # Pavé numérique (Windows) : les codes virtuels 96-111 sont fiables même
    # lorsque pynput ne fournit aucun caractère (Verr Num, disposition
    # clavier, touche « / » traduite par erreur en « ! », etc.).
    if sys.platform == "win32" and isinstance(vk, int):
        numpad_char = NUMPAD_VK_CHARS.get(vk)
        if numpad_char is not None:
            return numpad_char, numpad_char, False

    char = getattr(key, "char", None)
    if (
        isinstance(char, str)
        and len(char) == 1
        and char.isprintable()
        and char not in ("\x00",)
    ):
        return char.lower(), char, False

    # Touche non imprimable liée à une lettre ou un chiffre (Ctrl+lettre,
    # Ctrl+Maj+lettre, etc.) : pynput fournit alors un caractère de contrôle.
    if isinstance(vk, int):
        if 65 <= vk <= 90:
            letter = chr(vk)
            return letter.lower(), letter, False
        if 48 <= vk <= 57:
            digit = chr(vk)
            return digit, digit, False
    return None, None, False


# ---------------------------------------------------------------------------
# Widgets de l'overlay
# ---------------------------------------------------------------------------


def _with_alpha(color: QColor, factor: float) -> QColor:
    """Copie d'une couleur avec son alpha multiplié par ``factor``."""
    result = QColor(color)
    alpha = int(round(color.alpha() * max(0.0, min(1.0, factor))))
    result.setAlpha(max(0, min(255, alpha)))
    return result


def _color_to_text(color: QColor) -> str:
    """Forme ``#rrggbb`` (ou ``#aarrggbb`` si la couleur est translucide)."""
    if color.alpha() == 255:
        return color.name(QColor.NameFormat.HexRgb)
    return color.name(QColor.NameFormat.HexArgb)


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


class Badge(QWidget):
    """Petite pastille arrondie affichant une touche, un modificateur, etc.

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

    def __init__(
        self,
        label: str,
        kind: str,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._kind = kind
        self._font = QFont(font)
        self._metrics = QFontMetrics(self._font)
        self._palette = palette
        self._alpha = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ------------------------------------------------------------------
    def set_alpha(self, alpha: float) -> None:
        alpha = max(0.0, min(1.0, alpha))
        if abs(alpha - self._alpha) > 0.001:
            self._alpha = alpha
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
        if self._kind == "mouse":
            return QSize(12 + 6 + 7 + text_width + 12, height)
        return QSize(text_width + 2 * self.HORIZONTAL_PADDING, height)

    # ------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setFont(self._font)

        alpha = self._alpha
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(9.0, rect.height() / 2.0)

        if self._kind == "plus":
            painter.setPen(_with_alpha(self._palette.muted, alpha))
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
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(_with_alpha(self._palette.text, alpha))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)
            return

        # Touche principale : pastille claire, texte sombre.
        painter.setBrush(_with_alpha(self._palette.key_bg, alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)
        painter.setPen(_with_alpha(self._palette.key_text, alpha))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)


class KeyRow(QWidget):
    """Une ligne de badges (une frappe ou une combinaison)."""

    def __init__(
        self,
        font: QFont,
        palette: Palette,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._font = QFont(font)
        self._palette = palette
        self._items: list[tuple[str, str]] = []
        self._badges: list[Badge] = []
        self._alpha = 1.0
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(5)
        self._layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # ------------------------------------------------------------------
    def set_items(self, items: Iterable[tuple[str, str]]) -> None:
        """Remplace le contenu de la ligne par ``[(libellé, type), ...]``."""
        self._items = list(items)
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

        for label, kind in self._items:
            badge = Badge(label, kind, self._font, self._palette, parent=self)
            badge.set_alpha(self._alpha)
            self._layout.addWidget(badge)
            self._badges.append(badge)

        self.updateGeometry()
        self.update()

    def set_alpha(self, alpha: float) -> None:
        self._alpha = alpha
        for badge in self._badges:
            badge.set_alpha(alpha)


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
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
        recent = (
            self._scroll_row is not None
            and self._rows
            and self._rows[-1] is self._scroll_row
            and event.direction == self._scroll_direction
            and mods == self._scroll_mods
            and now - self._scroll_time <= SCROLL_AGGREGATE_WINDOW
        )
        if recent:
            self._scroll_count += 1
            self._scroll_time = now
            base = _t(
                self._cfg.scroll_up_label
                if self._scroll_direction > 0
                else self._cfg.scroll_down_label
            )
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
        self._scroll_count = 1
        self._scroll_time = now
        self._scroll_mods = mods
        base = _t(
            self._cfg.scroll_up_label
            if event.direction > 0
            else self._cfg.scroll_down_label
        )
        self._scroll_row = self._new_row(self._mouse_items(mods, base))
        self._last_left_row = None

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
        self._sync_minimum_size()

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


# ---------------------------------------------------------------------------
# Icône et menu de notification
# ---------------------------------------------------------------------------


def _icon_pixmap(size: int) -> QPixmap:
    """Dessine l'icône de l'application (touche clavier stylisée)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    rect = QRectF(size * 0.02, size * 0.02, size * 0.96, size * 0.96)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor(91, 155, 255))
    gradient.setColorAt(1.0, QColor(46, 99, 232))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(rect, size * 0.26, size * 0.26)

    painter.setBrush(QColor(255, 255, 255, 240))
    key_width = size * 0.16
    key_height = size * 0.12
    gap = size * 0.07
    total = 3 * key_width + 2 * gap
    start_x = (size - total) / 2.0
    top_y = size * 0.34
    radius = size * 0.03
    for index in range(3):
        painter.drawRoundedRect(
            QRectF(start_x + index * (key_width + gap), top_y, key_width, key_height),
            radius,
            radius,
        )
    painter.drawRoundedRect(
        QRectF(size * 0.28, size * 0.57, size * 0.44, size * 0.11),
        radius,
        radius,
    )
    painter.end()
    return pixmap


def build_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_icon_pixmap(size))
    return icon


class TrayController(QObject):
    """Icône de notification et menu de contrôle de PressVisual."""

    def __init__(
        self,
        app: QApplication,
        overlay: Overlay,
        config: Config,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._overlay = overlay
        self._cfg = config

        self.tray = QSystemTrayIcon(build_app_icon(), self)
        self.tray.setToolTip(self._tooltip())
        self.menu = QMenu()

        self.act_visible = QAction("", self)
        self.act_visible.setCheckable(True)
        self.act_visible.triggered.connect(self._overlay.toggle_visible)

        self.act_click_through = QAction("", self)
        self.act_click_through.setCheckable(True)
        self.act_click_through.triggered.connect(self._overlay.toggle_click_through)

        self.act_masking = QAction("", self)
        self.act_masking.setCheckable(True)
        self.act_masking.triggered.connect(self._overlay.toggle_masking)

        self.act_quit = QAction("", self)
        self.act_quit.triggered.connect(app.quit)

        self.menu.addAction(self.act_visible)
        self.menu.addAction(self.act_click_through)
        self.menu.addAction(self.act_masking)
        self.menu.addSeparator()

        self.act_appearance = QAction("", self)
        self.act_appearance.triggered.connect(self._overlay.edit_appearance)
        self.menu.addAction(self.act_appearance)

        self.position_menu = self.menu.addMenu("")
        self.position_group = QActionGroup(self)
        self.position_group.setExclusive(True)
        self.position_actions: dict[str, QAction] = {}
        for position in POSITION_CHOICES:
            action = QAction("", self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, chosen=position: self._overlay.set_position(
                    chosen
                )
            )
            self.position_group.addAction(action)
            self.position_menu.addAction(action)
            self.position_actions[position] = action

        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self._overlay.state_changed.connect(self.sync_actions)

        self.retranslate()
        self.sync_actions()

    # ------------------------------------------------------------------
    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    def retranslate(self) -> None:
        """Applique la langue courante aux textes du menu."""
        toggle_hint = describe_hotkey(self._cfg, self._cfg.hotkey_toggle)
        click_hint = describe_hotkey(self._cfg, self._cfg.hotkey_click_through)
        mask_hint = describe_hotkey(self._cfg, self._cfg.hotkey_masking)
        quit_hint = describe_hotkey(self._cfg, self._cfg.hotkey_quit)

        self.act_visible.setText(
            _t("Afficher l'overlay")
            + ("   " + toggle_hint if toggle_hint else "")
        )
        self.act_click_through.setText(
            _t("Clics traversants")
            + ("   " + click_hint if click_hint else "")
        )
        self.act_masking.setText(
            _t("Masquer les frappes") + ("   " + mask_hint if mask_hint else "")
        )
        self.act_quit.setText(
            _t("Quitter") + ("   " + quit_hint if quit_hint else "")
        )
        self.act_appearance.setText(_t("Personnaliser l'overlay…"))
        self.position_menu.setTitle(_t("Position de l'overlay"))
        for position, action in self.position_actions.items():
            action.setText(_t(POSITION_LABELS[position]))
        self.tray.setToolTip(self._tooltip())

    def _tooltip(self) -> str:
        hints = []
        for label, spec in (
            (_t("Afficher/masquer"), self._cfg.hotkey_toggle),
            (_t("Clics traversants"), self._cfg.hotkey_click_through),
            (_t("Masquer les frappes"), self._cfg.hotkey_masking),
            (_t("Quitter"), self._cfg.hotkey_quit),
        ):
            description = describe_hotkey(self._cfg, spec)
            if description:
                hints.append(
                    _t("{label} : {shortcut}").format(
                        label=label, shortcut=description
                    )
                )
        return f"{APP_NAME}\n" + "\n".join(hints)

    def sync_actions(self) -> None:
        self.act_visible.setChecked(self._overlay.capture_enabled)
        self.act_click_through.setChecked(self._overlay.click_through)
        self.act_masking.setChecked(self._overlay.masked)
        for position, action in self.position_actions.items():
            action.setChecked(position == self._overlay.position_name)

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._overlay.toggle_visible()


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------


def _default_config_path() -> Path:
    """``config.json`` à côté du script ou de l'exécutable PyInstaller."""
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        # macOS : PressVisual.app/Contents/MacOS/PressVisual -> dossier contenant le .app
        if sys.platform == "darwin" and executable.parent.name == "MacOS":
            return executable.parents[3] / "config.json"
        return executable.parent / "config.json"
    return Path(__file__).resolve().parent / "config.json"


def _language_argument(arguments: Iterable[str]) -> str:
    """Lit ``--lang`` sans construire le parseur (pour traduire l'aide)."""
    options = list(arguments)
    for index, argument in enumerate(options):
        if argument == "--lang" and index + 1 < len(options):
            return options[index + 1]
        if argument.startswith("--lang="):
            return argument.split("=", 1)[1]
    return LANGUAGE_AUTO


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pressvisual",
        description=_t(
            "Overlay de visualisation des frappes clavier et des clics souris, "
            "pour les captures d'écran et tutoriels."
        ),
    )
    parser.add_argument(
        "--config",
        metavar=_t("FICHIER"),
        help=_t("fichier JSON de configuration"),
    )
    parser.add_argument(
        "--lang",
        choices=(LANGUAGE_AUTO, *SUPPORTED_LANGUAGES),
        help=_t("langue de l'interface : auto (système), fr ou en"),
    )
    parser.add_argument(
        "--duration",
        type=float,
        help=_t("durée affichée après la dernière entrée (s)"),
    )
    parser.add_argument(
        "--opacity", type=float, help=_t("opacité du fond (0.15 - 1.0)")
    )
    parser.add_argument("--font-size", type=int, help=_t("taille de police (pt)"))
    parser.add_argument(
        "--max-rows", type=int, help=_t("nombre de lignes conservées")
    )
    parser.add_argument(
        "--max-width", type=int, help=_t("largeur maximale du contenu (px)")
    )
    parser.add_argument(
        "--margin", type=int, help=_t("marge avec le bord de l'écran (px)")
    )
    parser.add_argument(
        "--position",
        choices=POSITION_CHOICES,
        help=_t(
            "position initiale : top-left, top-right, bottom-left, bottom-right "
            "ou bottom-center"
        ),
    )
    parser.add_argument(
        "--no-keyboard",
        action="store_true",
        help=_t("ne pas afficher les frappes (les raccourcis globaux restent actifs)"),
    )
    parser.add_argument(
        "--no-mouse",
        action="store_true",
        help=_t("ne pas capturer la souris"),
    )
    parser.add_argument(
        "--group-text",
        action="store_true",
        help=_t(
            "regrouper les caractères saisis en texte continu au lieu d'une "
            "touche par ligne"
        ),
    )
    parser.add_argument(
        "--start-hidden",
        action="store_true",
        help=_t("démarrer sans capture (Ctrl+F12 pour l'activer)"),
    )
    parser.add_argument(
        "--click-through",
        action="store_true",
        help=_t("démarrer en mode clics traversants"),
    )
    parser.add_argument(
        "--toggle-hotkey",
        metavar=_t("RACCOURCI"),
        help=_t(
            "raccourci afficher/masquer (ex. ctrl+f12, chaîne vide pour désactiver)"
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    existing = QApplication.instance()
    app = (
        existing
        if isinstance(existing, QApplication)
        else QApplication(sys.argv[:1])
    )
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(build_app_icon())

    # La langue est choisie avant de construire le parseur : l'aide de
    # --help s'affiche ainsi dans la langue demandée (--lang ou système).
    language = resolve_language(_language_argument(arguments))
    translator = install_translator(app, language)

    parser = build_arg_parser()
    args = parser.parse_args(arguments)

    def warn(message: str) -> None:
        sys.stderr.write(f"[{APP_NAME}] {message}\n")

    config_path = (
        Path(args.config).expanduser().resolve()
        if args.config
        else _default_config_path()
    )
    config = Config.load(config_path, warn)

    if args.duration is not None:
        config.display_duration = args.duration
    if args.opacity is not None:
        config.opacity = args.opacity
    if args.font_size is not None:
        config.font_size = args.font_size
    if args.max_rows is not None:
        config.max_rows = args.max_rows
    if args.max_width is not None:
        config.max_width = args.max_width
    if args.margin is not None:
        config.margin = args.margin
    if args.position is not None:
        config.position = args.position
    if args.no_keyboard:
        config.capture_keyboard = False
    if args.no_mouse:
        config.capture_mouse = False
    if args.group_text:
        config.concat_text = True
    if args.start_hidden:
        config.start_hidden = True
    if args.click_through:
        config.click_through_on_start = True
    if args.toggle_hotkey is not None:
        config.hotkey_toggle = args.toggle_hotkey
    if args.lang is not None:
        config.language = args.lang

    # Le fichier de configuration peut imposer une autre langue que --lang.
    wanted = resolve_language(config.language)
    if wanted != language:
        translator = install_translator(app, wanted, translator)
        language = wanted

    for note in config.validate():
        warn(note)

    if not config.capture_keyboard and not config.capture_mouse:
        warn(_t("Clavier et souris sont désactivés : l'overlay ne montrera rien."))

    overlay = Overlay(config)

    bridge = InputBridge()
    hotkeys: dict[tuple[frozenset[str], str], str] = {}
    for action, spec in (
        ("toggle", config.hotkey_toggle),
        ("click_through", config.hotkey_click_through),
        ("masking", config.hotkey_masking),
        ("quit", config.hotkey_quit),
    ):
        parsed = parse_hotkey(spec)
        if parsed is None:
            if spec:
                warn(
                    _t("Raccourci global invalide ignoré : {spec}").format(
                        spec=repr(spec)
                    )
                )
            continue
        hotkeys[parsed] = action

    listener = InputListener(bridge, config, hotkeys)

    def dispatch_hotkey(action: str) -> None:
        if action == "quit":
            app.quit()
            return
        overlay.cancel_live_combo()
        if action == "toggle":
            overlay.toggle_visible()
        elif action == "click_through":
            overlay.toggle_click_through()
        elif action == "masking":
            overlay.toggle_masking()

    bridge.key_event.connect(overlay._on_key)
    bridge.mouse_event.connect(overlay._on_mouse)
    bridge.modifiers_changed.connect(overlay._on_modifiers)
    bridge.hotkey.connect(dispatch_hotkey)

    def show_error(message: str) -> None:
        warn(message)
        QMessageBox.critical(
            None, f"{APP_NAME} — {_t('erreur de capture')}", message
        )

    bridge.error.connect(show_error)

    tray = TrayController(app, overlay, config)

    def change_language(chosen: str) -> None:
        """Applique le choix de langue de la fenêtre d'apparence."""
        nonlocal translator
        translator = apply_language_change(app, tray, translator, chosen)

    overlay.language_changed.connect(change_language)

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
    else:
        warn(
            _t(
                "Aucune zone de notification disponible : utilisez les raccourcis "
                "globaux ou Ctrl+C dans le terminal pour quitter."
            )
        )

    def shutdown() -> None:
        listener.stop()
        tray.hide()

    app.aboutToQuit.connect(shutdown)

    # Permet à Ctrl+C (terminal) de fermer proprement l'application.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    keep_alive = QTimer()
    keep_alive.start(250)
    keep_alive.timeout.connect(lambda: None)

    listener.start()

    try:
        return app.exec()
    finally:
        listener.stop()


if __name__ == "__main__":
    raise SystemExit(main())
