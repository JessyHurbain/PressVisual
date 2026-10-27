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

#: Modes d'affichage : pastilles de frappes ou clavier complet.
DISPLAY_MODES: tuple[str, ...] = ("overlay", "keyboard")

#: Dispositions de clavier proposées pour le mode « clavier complet ».
KEYBOARD_LAYOUTS: tuple[str, ...] = ("azerty", "qwerty")

#: Dessins proposés pour la souris du mode clavier.
MOUSE_STYLES: tuple[str, ...] = ("classic", "outline", "minimal")

MOUSE_STYLE_LABELS: dict[str, str] = {
    "classic": "Classique",
    "outline": "Contour",
    "minimal": "Minimal",
}

#: Dessins de la pastille affichée près du curseur (clic et molette).
CURSOR_STYLES: tuple[str, ...] = ("classic", "outline", "keycap")

CURSOR_STYLE_LABELS: dict[str, str] = {
    "classic": "Classique",
    "outline": "Contour",
    "keycap": "Touche",
}

#: Formes proposées pour les touches du clavier complet.
KEY_SHAPES: tuple[str, ...] = (
    "rounded",
    "square",
    "circle",
    "pill",
    "hexagon",
    "diamond",
    "flower",
    "star",
)

KEY_SHAPE_LABELS: dict[str, str] = {
    "rounded": "Arrondie",
    "square": "Carrée",
    "circle": "Ronde",
    "pill": "Pilule",
    "hexagon": "Hexagone",
    "diamond": "Losange",
    "flower": "Fleur",
    "star": "Étoile",
}

#: Transitions de la bulle, utilisées à l'apparition comme à la disparition.
TRANSITIONS: tuple[str, ...] = (
    "fade",
    "slide",
    "slide-up",
    "slide-left",
    "slide-right",
    "zoom",
    "none",
)

TRANSITION_LABELS: dict[str, str] = {
    "fade": "Fondu",
    "slide": "Glissement vers le bas",
    "slide-up": "Glissement vers le haut",
    "slide-left": "Glissement vers la gauche",
    "slide-right": "Glissement vers la droite",
    "zoom": "Zoom",
    "none": "Aucune",
}

#: Animations d'apparition des lignes de l'overlay standard.
ROW_ANIMATIONS: tuple[str, ...] = ("fade", "zoom", "grow", "none")

ROW_ANIMATION_LABELS: dict[str, str] = {
    "fade": "Fondu",
    "zoom": "Zoom",
    "grow": "Dérouler",
    "none": "Aucune",
}

#: Sens de sortie des transitions glissées, en fraction de la taille de la
#: bulle : (dx, dy). L'apparition repart du même bord.
SLIDE_DIRECTIONS: dict[str, tuple[float, float]] = {
    "slide": (0.0, 1.0),        # sort par le bas
    "slide-up": (0.0, -1.0),    # sort par le haut
    "slide-left": (-1.0, 0.0),  # sort par la gauche
    "slide-right": (1.0, 0.0),  # sort par la droite
}

#: Échelle atteinte par la transition « zoom » (la bulle rétrécit en sortant).
ZOOM_SCALE = 0.9


def transition_geometry(
    style: str, width: float, height: float, progress: float
) -> tuple[float, float, float, float]:
    """Décale, réduit et estompe une bulle selon sa transition.

    ``progress`` vaut 0 pour la bulle en place et 1 pour la bulle sortie.
    Renvoie ``(dx, dy, échelle, opacité)``.

    L'overlay et l'aperçu des réglages appellent tous deux cette fonction :
    ajouter une transition ne demande donc qu'une entrée dans
    ``TRANSITIONS``, un libellé et, si elle glisse, une direction.
    """
    fx, fy = SLIDE_DIRECTIONS.get(style, (0.0, 0.0))
    if style == "zoom":
        return (
            0.0,
            0.0,
            1.0 + (ZOOM_SCALE - 1.0) * progress,
            1.0 - progress,
        )
    if style == "fade":
        return 0.0, 0.0, 1.0, 1.0 - progress
    return fx * width * progress, fy * height * progress, 1.0, 1.0

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

#: Préfixe pynput de chaque modificateur, pour nommer le côté enfoncé.
MODIFIER_SIDE_PREFIXES: dict[str, str] = {
    "ctrl": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "win": "cmd",
}


def modifier_side_token(modifier: str, side: str) -> str:
    """Jeton du côté enfoncé d'un modificateur (``ctrl_l``, ``shift_r``...).

    ``pynput`` nomme les deux touches d'un même modificateur ; c'est ce qui
    permet de n'allumer que celle qui est tenue sur le clavier affiché.
    """
    prefix = MODIFIER_SIDE_PREFIXES.get(modifier, modifier)
    return f"{prefix}_{'l' if side == 'left' else 'r'}"


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


def shape_label(config: Config, label: str) -> str:
    """Étiquette d'une touche ramenée à celle de la disposition.

    La bulle affiche les modificateurs traduits (« Shift » en anglais) alors
    que l'éditeur les nomme comme le clavier (« Maj ») : la forme choisie
    pour l'un doit suivre l'autre.
    """
    for field_name in ("ctrl_label", "alt_label", "shift_label", "win_label"):
        raw = str(getattr(config, field_name, "") or "")
        if raw and label != raw and label == _t(raw):
            return raw
    return label


def key_shape_for(config: Config, label: str) -> str:
    """Forme d'une touche d'après son étiquette affichée."""
    return config.shape_for(shape_label(config, label))


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
