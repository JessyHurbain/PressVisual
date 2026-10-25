"""Raccourcis globaux, libellés et combinaison de touches."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .i18n import _t

if TYPE_CHECKING:
    from .config import Config

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

#: Libellé des clics multiples.
MULTI_CLICK_LABELS: dict[int, str] = {2: "Double clic", 3: "Triple clic"}
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
