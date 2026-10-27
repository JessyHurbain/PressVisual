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
from pressvisual_app import diagnostics, i18n, rows  # noqa: E402 - idem

#: Chaîne témoin dont la traduction anglaise diffère du français : sa valeur
#: dit quelle langue est active dans l'application.
LANGUAGE_SENTINEL = "Espace"


@pytest.fixture(autouse=True)
def _journal_temporaire(tmp_path, monkeypatch):
    """Détourne le journal vers un dossier temporaire.

    Sans cela, chaque test qui signale un message écrirait dans le dossier de
    données du vrai utilisateur.
    """
    monkeypatch.setattr(diagnostics, "_log_path", tmp_path / "pressvisual.log")


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


@pytest.fixture(scope="session", autouse=True)
def _langue_du_systeme_figee():
    """Fige la langue du système, comme sur les runners d'intégration continue.

    Laissée au poste, la langue « auto » vaut le français ici et l'anglais
    ailleurs : la suite ne serait verte que sur l'une des deux machines, et un
    test qui oublie ``--lang fr`` ne se verrait qu'en CI — c'est précisément
    l'écueil qui a rendu la CI rouge sans que rien ne bouge en local. Figée à
    l'anglais, elle rend le comportement identique partout, et l'oubli installe
    alors un traducteur anglais sur *toutes* les machines, ce que le garde-fou
    suivant intercepte.
    """
    original = i18n.QLocale.system
    try:
        i18n.QLocale.system = staticmethod(lambda: i18n.QLocale("en_US"))
        yield
    finally:
        i18n.QLocale.system = original


@pytest.fixture(scope="session")
def _langue_de_depart(qapp):
    """Langue de l'application avant le premier test.

    Aucun traducteur n'est installé : les chaînes françaises, langue source,
    s'affichent telles quelles, quelle que soit la machine.
    """
    return pressvisual._t(LANGUAGE_SENTINEL)


@pytest.fixture(autouse=True)
def _pas_de_traducteur_oublie(_langue_de_depart):
    """Un traducteur installé par un test ne doit pas survivre à ce test.

    ``main()`` installe la langue du système : appelé sans ``--lang fr``, un
    test laissait l'anglais en place pour toute la session, et les tests
    suivants — ceux qui attendent « Clic droit » ou « Quitter » — échouaient
    loin de leur cause. La langue du système étant figée à l'anglais, cet oubli
    produit maintenant le même échec ici et sur la CI, au plus près du test
    fautif.
    """
    yield
    assert pressvisual._t(LANGUAGE_SENTINEL) == _langue_de_depart, (
        f"{LANGUAGE_SENTINEL!r} est traduit après ce test : un traducteur "
        "reste installé pour toute la session. Passe --lang fr à main(), ou "
        "retire le traducteur à la fin du test."
    )


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
    rows.clear(widget)
    widget.hide()
    widget.deleteLater()
    qapp.processEvents()


def row_items(overlay) -> list[list[tuple[str, str]]]:
    """Contenu affiché, une liste de ``(libellé, type)`` par ligne."""
    return [list(row._items) for row in overlay._rows]
