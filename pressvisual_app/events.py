"""Événements échangés entre la capture et l'interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

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
    button: Optional[str] = None    # "left" | "right" | "middle" | "back" | "forward"
    count: int = 1
    direction: int = 0              # +1 haut/droite, -1 bas/gauche (molette)
    axis: str = "vertical"          # "vertical" | "horizontal" (molette inclinable)
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
    key_release = pyqtSignal(str)         # jeton de la touche relâchée
    mouse_event = pyqtSignal(object)      # MouseEvent
    mouse_release = pyqtSignal(str)       # bouton de souris relâché
    modifiers_changed = pyqtSignal(object)  # tuple[str, ...]
    hotkey = pyqtSignal(str)              # "toggle" | "masking" | ...
    error = pyqtSignal(str)

