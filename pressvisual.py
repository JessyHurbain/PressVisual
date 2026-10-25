#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PressVisual — overlay de visualisation des frappes clavier et des clics souris.

Point d'entrée de l'application : le code est réparti dans le paquet
``pressvisual_app`` (configuration, capture, overlay, apparence, menu,
traductions). Ce module conserve l'API historique — ``import pressvisual``
expose les mêmes noms qu'auparavant.

Exécution :
    python pressvisual.py
    python -m pressvisual_app
    python pressvisual.py --help

Licence : libre d'utilisation et de modification.
"""

from __future__ import annotations

from pressvisual_app import *  # noqa: F401,F403 - API historique du module
from pressvisual_app import main  # noqa: F401 - explicite pour la lecture

if __name__ == "__main__":
    raise SystemExit(main())
