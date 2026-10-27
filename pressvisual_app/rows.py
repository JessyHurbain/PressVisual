"""Modèle des lignes de la bulle : création, comptage et apparition.

Ce module réunit tout ce qui concerne **les lignes de l'overlay standard** et
leur animation d'apparition, autrefois noyées dans la fenêtre : création d'une
ligne, absorption d'un appui répété en « ×N », texte continu, ligne de
combinaison, élagage, niveaux d'opacité et avancement des apparitions.

Chaque fonction reçoit la fenêtre en premier argument. Aucun état n'est
conservé ici : il reste sur la fenêtre, là où Qt l'attend (les minuteurs et la
disposition sont ses enfants) et là où le reste du code le lit déjà. Le module
est ainsi une simple couche de logique, sans objet intermédiaire à maintenir en
phase avec la fenêtre.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Iterable, Optional

from .keymap import (
    MODIFIER_ORDER,
    ROW_ANIMATIONS,
    key_label,
    key_shape_for,
    modifier_label,
)
from .widgets import KeyRow

if TYPE_CHECKING:
    from .events import KeyEvent
    from .overlay import Overlay

#: Longueur maximale du tampon de texte affiché.
MAX_TEXT_LENGTH = 200
#: Durée de l'apparition d'une ligne de l'overlay standard (ms).
ROW_ANIMATION_MS = 180
#: Cadence de rafraîchissement des apparitions (ms), soit ~60 images/s.
ROW_ANIMATION_TICK_MS = 16
#: Course des animations « glisser » et « chute », en pixels.
ROW_SHIFT_PX = 14.0
#: Hauteur maximale d'un widget Qt (valeur « sans limite »).
ROW_MAX_HEIGHT = 16777215


def ease_out_back(progress: float) -> float:
    """Sortie qui dépasse sa cible avant de se poser (rebond)."""
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (progress - 1.0) ** 3 + c1 * (progress - 1.0) ** 2


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------


def combo_items(
    host: Overlay,
    mods: Iterable[str],
    key: Optional[str] = None,
    key_kind: str = "key",
) -> list[tuple[str, str]]:
    """Badges d'une combinaison : modificateurs, « + », puis la touche."""
    parts: list[tuple[str, str]] = [
        (modifier_label(host._cfg, mod), "mod")
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


def mouse_items(
    host: Overlay, mods: Iterable[str], label: str
) -> list[tuple[str, str]]:
    """Badges d'un clic ou d'un cran de molette, modificateurs compris."""
    return combo_items(host, mods, label, key_kind="mouse")


def event_key_label(host: Overlay, event: KeyEvent) -> str:
    """Libellé d'une touche telle qu'elle doit s'afficher."""
    if event.char:
        return event.char.upper() if len(event.char) == 1 else event.char
    return key_label(host._cfg, event.token)


def fit_text(host: Overlay, text: str) -> str:
    """Tronque le début du texte pour tenir dans la largeur maximale."""
    if not text:
        return ""
    limit = max(140, host._cfg.max_width - 40)
    if host._text_metrics.horizontalAdvance(text) <= limit:
        return text
    trimmed = text
    while trimmed and host._text_metrics.horizontalAdvance("… " + trimmed) > limit:
        trimmed = trimmed[1:]
    return "… " + trimmed if trimmed else "…"


# ---------------------------------------------------------------------------
# Cycle de vie des lignes
# ---------------------------------------------------------------------------


def animation_style(host: Overlay) -> str:
    """Animation d'apparition des lignes, relue dans la configuration."""
    style = str(host._cfg.row_animation or "fade").strip().lower()
    return style if style in ROW_ANIMATIONS else "fade"


def new_row(host: Overlay, items: Iterable[tuple[str, str]]) -> KeyRow:
    """Ajoute une ligne à la bulle et lance son apparition."""
    row = KeyRow(
        host._badge_font,
        host._palette,
        host,
        # La bulle suit les formes de l'éditeur de touches ; la règle est
        # relue à chaque badge pour qu'un réglage s'applique sans
        # reconstruire les lignes.
        shape_for=lambda label: key_shape_for(host._cfg, label),
    )
    row.set_items(items)
    host._rows.append(row)
    host._layout.addWidget(row)
    trim(host)
    update_levels(host)
    host._relayout()
    host._bump()
    animate(host, row)
    return row


def animate(host: Overlay, row: KeyRow) -> None:
    """Fait apparaître une nouvelle ligne avec l'animation choisie.

    Un seul minuteur pilote toutes les apparitions : les lignes retirées
    avant la fin sont simplement oubliées au passage suivant, sans objet
    Qt à détruire en cours de route.
    """
    style = animation_style(host)
    if style == "none":
        return

    height = 0
    row.set_appear(0.0)
    if style == "grow":
        # La ligne s'ouvre en hauteur : la bulle grandit pour lui faire
        # place, comme un volet qui se déroule.
        height = max(1, row.sizeHint().height())
        row.setMaximumHeight(0)
    elif style in ("zoom", "bounce"):
        # Les pastilles grossissent depuis leur centre, à place constante.
        row.set_zoom(0.7)
    elif style == "slide":
        row.set_offset(-ROW_SHIFT_PX, 0.0)
    elif style == "drop":
        row.set_offset(0.0, -ROW_SHIFT_PX)

    host._row_appearances.append((row, time.monotonic(), style, height))
    if not host._row_animation_timer.isActive():
        host._row_animation_timer.start()


def step_animations(host: Overlay) -> None:
    """Avance les apparitions en cours et arrête le minuteur à la fin."""
    now = time.monotonic()
    duration = max(1, ROW_ANIMATION_MS)
    remaining: list[tuple[KeyRow, float, str, int]] = []
    grew = False

    for row, start, style, height in host._row_appearances:
        if row not in host._rows:
            # Ligne retirée entre-temps : plus rien à animer.
            continue
        progress = min(1.0, (now - start) * 1000.0 / duration)
        # Sortie douce : rapide au début, posée à l'arrivée.
        eased = 1.0 - (1.0 - progress) ** 3
        if style == "bounce":
            # L'opacité monte vite pour que le rebond se voie.
            row.set_appear(min(1.0, progress * 2.5))
            row.set_zoom(0.7 + 0.3 * ease_out_back(progress))
        else:
            row.set_appear(eased)
        if style == "grow":
            row.setMaximumHeight(max(1, int(round(height * eased))))
            grew = True
        elif style == "zoom":
            row.set_zoom(0.7 + 0.3 * eased)
        elif style == "slide":
            row.set_offset(-ROW_SHIFT_PX * (1.0 - eased), 0.0)
        elif style == "drop":
            row.set_offset(0.0, -ROW_SHIFT_PX * (1.0 - eased))

        if progress < 1.0:
            remaining.append((row, start, style, height))
            continue
        # Arrivée : la ligne reprend exactement sa place et sa taille.
        row.set_appear(1.0)
        row.set_zoom(1.0)
        row.set_offset(0.0, 0.0)
        if style == "grow":
            row.setMaximumHeight(ROW_MAX_HEIGHT)

    host._row_appearances = remaining
    if grew:
        host._relayout()
    if not host._row_appearances:
        host._row_animation_timer.stop()


def merge_repeat(host: Overlay, row: KeyRow) -> None:
    """Absorbe une ligne identique à la précédente en « ×N ».

    Deux appuis de suite sur la même touche ne doivent pas empiler deux
    pastilles identiques : la première compte les appuis. Une touche
    intercalée, un texte, une ligne de souris ou un passage masqué
    interrompt le compte.
    """
    previous = repeat_target(host, row)
    if previous is None:
        host._repeat_row = row
        return
    remove(host, row)
    # Le premier compteur vaut « ×2 » : la pastille gardée est le premier
    # appui, la ligne absorbée est le second.
    previous.set_count(max(2, previous.count + 1))
    host._repeat_row = previous
    update_levels(host)
    host._relayout()
    host._bump()


def repeat_target(host: Overlay, row: KeyRow) -> Optional[KeyRow]:
    """Ligne qui peut compter l'appui, si c'est bien le même."""
    if not host._cfg.count_repeats or row not in host._rows:
        return None
    items = row.items
    if not items or any(kind == "text" for _, kind in items):
        return None
    index = host._rows.index(row)
    if index == 0:
        return None
    previous = host._rows[index - 1]
    # Seule la ligne de l'appui précédent compte : après une autre touche
    # ou un passage masqué, l'appui repart de un.
    if previous is not host._repeat_row or previous.items != items:
        return None
    return previous


def remove(host: Overlay, row: Optional[KeyRow]) -> None:
    """Retire une ligne de la bulle, en oubliant ce qu'elle représentait."""
    if row is None or row not in host._rows:
        return
    host._rows.remove(row)
    host._layout.removeWidget(row)
    row.setParent(None)
    row.deleteLater()
    if row is host._text_row:
        host._text_row = None
        host._text = ""
    if row is host._combo_row:
        host._combo_row = None
    if row is host._scroll_row:
        host._scroll_row = None
    if row is host._last_left_row:
        host._last_left_row = None
    if row is host._repeat_row:
        host._repeat_row = None
    update_levels(host)
    host._relayout()


def trim(host: Overlay) -> None:
    """Ne garde que ``max_rows`` lignes, en retirant les plus anciennes."""
    while len(host._rows) > host._cfg.max_rows:
        old = host._rows.pop(0)
        host._layout.removeWidget(old)
        old.setParent(None)
        old.deleteLater()
        if old is host._text_row:
            host._text_row = None
            host._text = ""
        if old is host._combo_row:
            host._combo_row = None
        if old is host._scroll_row:
            host._scroll_row = None
        if old is host._last_left_row:
            host._last_left_row = None
        if old is host._repeat_row:
            host._repeat_row = None


def update_levels(host: Overlay) -> None:
    """Estompe les lignes anciennes, la plus récente restant nette."""
    levels = (1.0, 0.62, 0.34)
    count = len(host._rows)
    for index, row in enumerate(host._rows):
        depth = count - 1 - index
        row.set_alpha(levels[min(depth, len(levels) - 1)])


def clear(host: Overlay) -> None:
    """Vide la bulle : lignes, texte en cours et apparitions."""
    for row in host._rows:
        host._layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
    host._rows.clear()
    host._text_row = None
    host._text = ""
    host._combo_row = None
    host._scroll_row = None
    host._last_left_row = None
    host._repeat_row = None
    # Les lignes animées viennent de disparaître : plus rien à faire
    # avancer.
    host._row_appearances.clear()
    host._row_animation_timer.stop()
    host._typing_timer.stop()
    host._relayout()


# ---------------------------------------------------------------------------
# Texte continu
# ---------------------------------------------------------------------------


def add_text_char(host: Overlay, char: str) -> None:
    """Ajoute un caractère au texte continu, en ouvrant sa ligne au besoin."""
    if host._masked:
        char = "•"

    if host._text_row is None and not host._text:
        if char.isspace():
            return
        host._text_row = new_row(host, [])
        host._text = char
    else:
        host._text += char
        if len(host._text) > MAX_TEXT_LENGTH:
            host._text = host._text[-MAX_TEXT_LENGTH:]

    render_text(host)
    host._typing_timer.start(int(host._cfg.typing_join_delay * 1000))
    host._bump()


def render_text(host: Overlay) -> None:
    """Rafraîchit la ligne de texte continu avec le tampon courant."""
    if host._text_row is None:
        return
    display = fit_text(host, host._text.rstrip())
    host._text_row.set_items([(display, "text")] if display else [])
    host._relayout()


def finish_text(host: Overlay) -> None:
    """Referme le texte continu : la ligne garde le texte saisi."""
    host._typing_timer.stop()
    if host._text_row is None:
        return
    text = host._text.rstrip()
    if text:
        host._text_row.set_items([(fit_text(host, text), "text")])
    else:
        remove(host, host._text_row)
    host._text_row = None
    host._text = ""
    host._relayout()


def flush_typing(host: Overlay) -> None:
    """Termine le texte en cours avant qu'autre chose ne prenne la bulle."""
    if host._text_row is not None or host._text:
        finish_text(host)


# ---------------------------------------------------------------------------
# Combinaisons
# ---------------------------------------------------------------------------


def close_combo(host: Overlay, remove_row: bool = False) -> None:
    """Oublie la ligne de combinaison en cours, en la retirant si demandé."""
    row = host._combo_row
    host._combo_row = None
    if row is not None and remove_row:
        remove(host, row)
