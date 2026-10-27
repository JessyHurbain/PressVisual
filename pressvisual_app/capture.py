"""Capture globale des entrées et conversion en événements."""

from __future__ import annotations

import contextlib
import sys
import threading
import time
from typing import TYPE_CHECKING, Optional

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

from .events import InputBridge, KeyEvent, MouseEvent
from .i18n import _t
from .keymap import MODIFIER_KEYS, MODIFIER_ORDER, modifier_side_token

if TYPE_CHECKING:
    from .config import Config

#: Fenêtre de temps (s) pendant laquelle deux clics forment un double-clic.
DOUBLE_CLICK_WINDOW = 0.45

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

def _side_button_names() -> dict[object, str]:
    """Boutons latéraux exposés par pynput sur la plateforme courante.

    Windows nomme ces boutons ``Button.x1`` et ``Button.x2``, X11 les numérote
    ``Button.button8`` et ``Button.button9``. macOS ne les transmet pas.
    """
    names: dict[object, str] = {}
    for attributes, canonical in (
        (("x1", "button8"), "back"),
        (("x2", "button9"), "forward"),
    ):
        for attribute in attributes:
            button = getattr(mouse.Button, attribute, None)
            if button is not None:
                names[button] = canonical
                break
    return names


#: Noms des boutons de souris (``back``/``forward`` = boutons latéraux).
MOUSE_BUTTON_NAMES: dict[object, str] = {
    mouse.Button.left: "left",
    mouse.Button.right: "right",
    mouse.Button.middle: "middle",
    **_side_button_names(),
}

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
        #: Côtés physiques enfoncés (``ctrl_l``, ``shift_r``...), pour
        #: n'allumer que la touche réellement tenue sur le clavier affiché.
        self._mod_sides: set[str] = set()
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
                # L'arrêt d'un écouteur ne doit jamais empêcher l'arrêt de
                # l'autre, ni celui de l'application.
                with contextlib.suppress(Exception):
                    listener.stop()
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                with contextlib.suppress(Exception):
                    listener.join(timeout=1.0)

    # ------------------------------------------------------------------
    # Clavier
    # ------------------------------------------------------------------
    def _mods_snapshot(self) -> tuple[str, ...]:
        return tuple(m for m in MODIFIER_ORDER if m in self._mods)

    def _mod_sides_snapshot(self) -> tuple[str, ...]:
        return tuple(sorted(self._mod_sides))

    def _emit_modifiers(self) -> None:
        """Signale les modificateurs tenus : côtés d'abord, noms ensuite.

        L'interface reçoit ainsi le côté avant le nom et n'allume que la
        touche enfoncée, sans passer par un état où les deux s'allument.
        """
        if not self._config.capture_keyboard or self._altgr:
            return
        self._bridge.modifier_sides_changed.emit(self._mod_sides_snapshot())
        self._bridge.modifiers_changed.emit(self._mods_snapshot())

    def _on_press(self, key) -> None:
        try:
            if _is_altgr(key):
                self._altgr = True
                return

            token, char, is_modifier = _classify_key(key)
            if is_modifier:
                self._mods.add(token)
                self._mod_sides.add(_modifier_side(key, token))
                self._emit_modifiers()
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
                self._mod_sides.discard(_modifier_side(key, token))
                if token == "alt":
                    self._altgr = False
                self._emit_modifiers()
                return
            if token:
                self._held.discard(token.lower())
                # L'interface éteint la touche dès qu'elle est relâchée.
                self._bridge.key_release.emit(token.lower())
        except Exception as exc:
            self._report_error(
                _t("Erreur pendant la lecture du clavier : {error}").format(error=exc)
            )

    # ------------------------------------------------------------------
    # Souris
    # ------------------------------------------------------------------
    def _on_click(self, x, y, button, pressed) -> None:
        try:
            name = MOUSE_BUTTON_NAMES.get(button)
            if name is None:
                return
            if not pressed:
                # L'interface éteint le bouton dès qu'il est relâché.
                self._bridge.mouse_release.emit(name)
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
            # Un événement peut porter les deux axes (molette diagonale) : le
            # défilement vertical reste prioritaire, comme auparavant.
            if dy:
                axis, direction = "vertical", 1 if dy > 0 else -1
            elif dx:
                axis, direction = "horizontal", 1 if dx > 0 else -1
            else:
                return
            self._bridge.mouse_event.emit(
                MouseEvent(
                    kind="scroll",
                    axis=axis,
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


def _modifier_side(key, token: str) -> str:
    """Côté enfoncé d'un modificateur (``ctrl_l``, ``shift_r``...).

    Sous X11 et macOS, ``pynput`` construit son jeton générique (``ctrl``,
    ``shift``) sur la touche de gauche : un nom sans suffixe désigne donc la
    touche gauche. Windows distingue les deux côtés.
    """
    name = getattr(key, "name", None)
    side = "right" if isinstance(name, str) and name.endswith("_r") else "left"
    return modifier_side_token(token, side)


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

