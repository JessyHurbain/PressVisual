"""Configuration commune de la suite de tests.

Les tests s'exécutent avec le greffon Qt « offscreen » : aucune fenêtre ne
s'ouvre, même sur une machine sans écran. Il faut toutefois que l'affichage
soit défini sous Linux, car l'import de ``pynput`` ouvre une connexion X11 ;
en intégration continue, les tests sont donc lancés via ``xvfb-run``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Doit être fait avant toute création de QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402 - après le réglage de QT_QPA_PLATFORM
from PyQt6.QtWidgets import QApplication  # noqa: E402

import pressvisual  # noqa: E402 - dépend du réglage ci-dessus


@pytest.fixture(scope="session")
def qapp():
    """Instance unique de QApplication pour toute la session."""
    app = QApplication.instance()
    created = app is None
    if created:
        app = QApplication([])
    app.setApplicationName("PressVisual tests")
    yield app
    if created:
        app.quit()


@pytest.fixture
def config():
    """Configuration par défaut validée (indépendante pour chaque test)."""
    value = pressvisual.Config()
    assert value.validate() == []
    return value


@pytest.fixture
def overlay(qapp, config):
    """Overlay prêt à recevoir des événements, nettoyé après le test."""
    widget = pressvisual.Overlay(config)
    yield widget
    widget._hide_now()
    widget._clear_rows()
    widget.hide()
    widget.deleteLater()
    qapp.processEvents()


def row_items(overlay) -> list[list[tuple[str, str]]]:
    """Contenu affiché, une liste de ``(libellé, type)`` par ligne."""
    return [list(row._items) for row in overlay._rows]
