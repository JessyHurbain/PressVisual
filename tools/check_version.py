#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vérifie que le tag publié porte la version affichée par l'application.

Deux numéros de version coexistent : le tag ``v1.2.3`` donne le nom des
binaires (``PressVisual-1.2.3-x86_64.AppImage``), tandis que le menu de la
notification et ``--version`` affichent ``APP_VERSION``, écrit à la main dans
``pressvisual_app/constants.py``. Rien ne liait les deux : un oubli de mise à
jour livrait une release dont le fichier annonce une version et le logiciel une
autre, sans que la CI bronche. Ce script fait échouer la release dans ce cas.

Il n'importe pas ``pressvisual_app`` — ce paquet charge PyQt6, absent d'un
runner qui n'a que Python — et se contente de lire la constante.

Utilisation :
    python tools/check_version.py v0.1.5
    python tools/check_version.py v0.1.5 --constants pressvisual_app/constants.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

#: Fichier qui définit la version affichée (voir pressvisual_app/constants.py).
DEFAULT_CONSTANTS = (
    Path(__file__).resolve().parents[1] / "pressvisual_app" / "constants.py"
)

#: Ligne d'affectation de la constante, avec ses guillemets doubles.
APP_VERSION_PATTERN = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def app_version(path: Path = DEFAULT_CONSTANTS) -> str:
    """Version affichée par l'application, lue dans ``constants.py``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{path} illisible : {exc}") from exc
    match = APP_VERSION_PATTERN.search(text)
    if match is None:
        raise ValueError(f"{path} : aucune ligne « APP_VERSION = \"…\" ».")
    return match.group(1)


def tag_version(tag: str) -> str:
    """Version portée par un tag, sans le préfixe ``v`` ni les espaces."""
    value = tag.strip()
    return value[1:] if value[:1] in ("v", "V") else value


def check(tag: str, version: Optional[str] = None) -> Optional[str]:
    """Problème détecté entre ``tag`` et ``version``, ou ``None`` si cohérents.

    ``version`` par défaut est celle de ``constants.py`` ; elle peut être
    fournie pour tester la comparaison sans toucher au fichier.
    """
    expected = app_version() if version is None else version
    published = tag_version(tag)
    if published == expected:
        return None
    return (
        f"Le tag « {tag} » annonce la version « {published} », mais "
        f"l'application affiche « {expected} » : mettez APP_VERSION à jour "
        f"dans pressvisual_app/constants.py, ou corrigez le tag."
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Échoue si le tag publié ne porte pas la version affichée par "
            "l'application (APP_VERSION)."
        )
    )
    parser.add_argument(
        "tag",
        help="tag publié, par exemple v0.1.5 (le préfixe v est facultatif)",
    )
    parser.add_argument(
        "--constants",
        type=Path,
        default=DEFAULT_CONSTANTS,
        help="fichier contenant APP_VERSION (par défaut : pressvisual_app/constants.py)",
    )
    args = parser.parse_args(argv)

    try:
        problem = check(args.tag, app_version(args.constants))
    except ValueError as exc:
        sys.stderr.write(f"{exc}\n")
        return 1

    if problem is not None:
        sys.stderr.write(f"{problem}\n")
        return 1

    sys.stdout.write(f"Version cohérente : {tag_version(args.tag)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
