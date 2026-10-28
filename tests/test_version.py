"""Tests de la porte qui compare le tag publié à la version affichée.

Le script tourne sur un runner nu, sans PyQt6 : il lit la constante dans le
fichier source au lieu d'importer le paquet. Ces tests vérifient donc aussi
qu'il reste indépendant de l'application.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools import check_version

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = PROJECT_ROOT / "pressvisual_app" / "constants.py"
RELEASE_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "release.yml"


def test_tag_sans_prefixe_est_accepte():
    assert check_version.check("0.1.5", "0.1.5") is None


def test_prefixe_v_est_accepte():
    assert check_version.check("v0.1.5", "0.1.5") is None


def test_espaces_et_retour_ligne_ignores():
    # La variable d'environnement du workflow peut porter un saut de ligne.
    assert check_version.check("  v0.1.5\n", "0.1.5") is None


def test_prefixe_majuscule_est_accepte():
    assert check_version.check("V0.1.5", "0.1.5") is None


def test_versions_differentes_signalent_les_deux_numeros():
    problem = check_version.check("v0.1.6", "0.1.5")

    assert problem is not None
    assert "0.1.6" in problem
    assert "0.1.5" in problem
    assert "APP_VERSION" in problem


def test_versions_voisines_ne_sont_pas_confondues():
    # 0.1.5 et 0.1.50 sont deux versions différentes : la comparaison est
    # textuelle, pas numérique.
    assert check_version.check("v0.1.50", "0.1.5") is not None


def test_version_lue_dans_le_fichier_reel():
    version = check_version.app_version()

    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version


def test_constante_absente_est_signalee(tmp_path):
    path = tmp_path / "constants.py"
    path.write_text("APP_NAME = 'PressVisual'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="APP_VERSION"):
        check_version.app_version(path)


def test_fichier_illisible_est_signale(tmp_path):
    with pytest.raises(ValueError, match="illisible"):
        check_version.app_version(tmp_path / "absent.py")


def test_main_reussit_quand_les_versions_concordent(capsys):
    code = check_version.main(["v0.1.5", "--constants", str(CONSTANTS)])

    assert code == 0
    assert "cohérente" in capsys.readouterr().out


def test_main_echoue_et_explique_quand_les_versions_different(capsys):
    code = check_version.main(["v9.9.9", "--constants", str(CONSTANTS)])

    assert code == 1
    assert "9.9.9" in capsys.readouterr().err


def test_main_echoue_si_la_constante_est_illisible(tmp_path, capsys):
    path = tmp_path / "constants.py"
    path.write_text("APP_VERSION = 1\n", encoding="utf-8")

    assert check_version.main(["v0.1.5", "--constants", str(path)]) == 1
    assert capsys.readouterr().err.strip()


# ---------------------------------------------------------------------------
# Branchement dans la release
# ---------------------------------------------------------------------------


def test_la_release_appelle_le_controle_avant_de_construire():
    """La porte ne sert que si le workflow l'appelle avant les constructions.

    Un simple retrait de ligne suffirait à rendre la vérification décorative :
    les trois constructions doivent en dépendre explicitement.
    """
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "tools/check_version.py" in workflow
    assert workflow.count("needs: [tests-verts, version-du-tag]") == 3
