#!/usr/bin/env bash
# Vérifie le dépôt comme le fait l'intégration continue, avant de pousser.
#
# Les trois étapes du workflow .github/workflows/tests.yml sont rejouées dans
# l'ordre : vérification de la compilation, analyse statique (ruff), puis tests
# avec mesure de couverture et le seuil défini dans pyproject.toml (85 %).
#
# Les conditions des runners sont reproduites exprès, car c'est là que se
# cachent les échecs invisibles en local : locale neutre (LC_ALL=C) et sortie
# UTF-8 forcée, comme sur un runner anglophone, et xvfb-run sous Linux pour les
# tests, qui n'ouvrent pas de fenêtre mais dont l'import de pynput a besoin d'un
# affichage.
#
# Ce que ce script ne reproduit pas : Windows, macOS ni les autres versions de
# Python de la matrice (3.9 à 3.12). Il annonce l'interpréteur qu'il a utilisé.
#
# Variables d'environnement facultatives :
#   PYTHON=/chemin/vers/python   interpréteur à utiliser (défaut : .venv, sinon python3)
#   SKIP_COVERAGE=1              tests sans mesure de couverture (plus rapide)
#   ROOT_DIR=/chemin/vers/dossier  dossier à vérifier (défaut : la racine du dépôt) ;
#                                  le crochet pre-push s'en sert pour vérifier une
#                                  copie de travail d'une autre révision
#
# Utilisation :
#   bash tools/check_ci.sh
#
# Prérequis : les dépendances de requirements-dev.txt et, sous Linux sans
# session graphique, le paquet xvfb.

set -euo pipefail

ROOT_DIR=${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
cd "$ROOT_DIR"

step() { printf '\n[vérification] %s\n' "$1"; }
note() { printf '[vérification] %s\n' "$1"; }
die() {
    printf '[vérification] erreur : %s\n' "$1" >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Interpréteur et dépendances
# ---------------------------------------------------------------------------

if [[ -n ${PYTHON:-} ]]; then
    command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON introuvable."
elif [[ -x $ROOT_DIR/.venv/bin/python ]]; then
    PYTHON=$ROOT_DIR/.venv/bin/python
else
    PYTHON=python3
    command -v "$PYTHON" >/dev/null 2>&1 \
        || die "python3 introuvable ; définissez PYTHON=/chemin/vers/python."
fi

"$PYTHON" -c 'import pytest, pytest_cov' 2>/dev/null \
    || die "pytest ou pytest-cov manquant : $PYTHON -m pip install -r requirements-dev.txt"
"$PYTHON" -m ruff --version >/dev/null 2>&1 \
    || die "ruff manquant : $PYTHON -m pip install -r requirements-dev.txt"

note "interpréteur : $("$PYTHON" -c 'import sys; print(sys.version.split()[0], sys.executable)')"

# ---------------------------------------------------------------------------
# Conditions des runners
# ---------------------------------------------------------------------------

# La locale neutre vaut anglais : sans elle, un test qui dépend de la langue du
# poste passerait ici et échouerait en CI.
export LC_ALL=C LANG=C LANGUAGE=
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

TESTS_PREFIX=()
if [[ $(uname -s) == Linux ]]; then
    if command -v xvfb-run >/dev/null 2>&1; then
        TESTS_PREFIX=(xvfb-run -a)
        note "affichage : xvfb-run (comme la tâche Linux)"
    elif [[ -z ${DISPLAY:-} ]]; then
        note "ni xvfb-run ni DISPLAY : l'import de pynput peut échouer."
    fi
fi

# ---------------------------------------------------------------------------
# Étapes
# ---------------------------------------------------------------------------

step "1/4 · compilation"
"$PYTHON" -m compileall -q pressvisual.py pressvisual_app tools

step "2/4 · analyse statique (ruff)"
"$PYTHON" -m ruff check --output-format=concise .

step "3/4 · tests"
LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

TESTS=("$PYTHON" -m pytest -q)
if [[ -z ${SKIP_COVERAGE:-} ]]; then
    TESTS+=(--cov --cov-report=term-missing)
fi
if ((${#TESTS_PREFIX[@]})); then
    TESTS=("${TESTS_PREFIX[@]}" "${TESTS[@]}")
fi

status=0
"${TESTS[@]}" 2>&1 | tee "$LOG" || status=$?

step "4/4 · verdict"
if [[ $status -ne 0 ]]; then
    note "échec : le dépôt n'est pas dans l'état attendu par la CI."
    exit "$status"
fi

if [[ -n ${SKIP_COVERAGE:-} ]]; then
    note "couverture non mesurée (SKIP_COVERAGE)."
fi
note "tout est vert : $(tail -n 1 "$LOG")"
note "non reproduit : Windows, macOS et les autres versions de Python de la matrice."
